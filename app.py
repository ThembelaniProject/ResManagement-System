from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from datetime import datetime
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo
from werkzeug.security import generate_password_hash
from functools import wraps

class AddUserForm(FlaskForm):
    full_name = StringField(
        'Full Name',
        validators=[DataRequired(), Length(min=2, max=100)]
    )
    email = StringField(
        'Email',
        validators=[DataRequired(), Email()]
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired(), Length(min=8)]
    )
    role = SelectField(
        'Role',
        choices=[('Admin', 'Admin'), ('Technician', 'Technician'), ('User', 'User')],
        validators=[DataRequired()]
    )
    submit = SubmitField('Create User')
app = Flask(__name__)

app.config['SECRET_KEY'] = 'secretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///maintenance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email configuration (Use your Gmail credentials)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your_app_password'

db = SQLAlchemy(app)
mail = Mail(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ================= MODELS =================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(200))
    role = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Request(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)               # ← should link to logged-in user
    technician_id = db.Column(db.Integer, nullable=True)
    room_number = db.Column(db.String(20), nullable=False)
    category    = db.Column(db.String(50))        # ← added
    description = db.Column(db.Text, nullable=False)
    priority    = db.Column(db.String(20), nullable=False)
    status      = db.Column(db.String(20), default="Pending")
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Request {self.id} - {self.room_number}>"



def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))  # ← change 'login' to your actual login route name

        # Adjust this condition to match how your User model stores roles
        if current_user.role.lower() not in ['admin', 'administrator']:
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for('dashboard'))  # ← or wherever you want to send non-admins

        return f(*args, **kwargs)
    return decorated_function

# Custom filter
@app.template_filter('format_datetime')
def format_datetime(value, format='%Y-%m-%d %H:%M'):
    if value is None:
        value = datetime.now()
    return value.strftime(format)

# ================= LOGIN =================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and check_password_hash(user.password_hash, request.form["password"]):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route('/admin/register', methods=['GET', 'POST'])
@login_required
def register():
    # Normalize role comparison (safer)
    if current_user.role.lower() != 'admin':
        flash('Only admins can create new users.', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email     = request.form.get('email', '').strip().lower()
        password  = request.form.get('password', '')
        role      = request.form.get('role', 'user').strip().lower()  # normalize to lowercase

        if not full_name or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))
            
        password_hash = generate_password_hash(password)
        
        new_user = User(
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            role=role,                    # stored as lowercase
            created_at=datetime.utcnow()
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('User created successfully!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')
            return redirect(url_for('register'))
    
    # GET request → show form
    return render_template('register.html')

# ================= DASHBOARD =================
@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "Admin":
        requests = Request.query.all()
        total = Request.query.count()
        pending = Request.query.filter_by(status="Pending").count()
        completed = Request.query.filter_by(status="Completed").count()

        return render_template("admin/dashboard.html",
                               requests=requests,
                               total=total,
                               pending=pending,
                               completed=completed)

    elif current_user.role == "Student":
        requests = Request.query.filter_by(user_id=current_user.id).all()
        return render_template("student_dashboard.html",
                               requests=requests)
    elif current_user.role == "Technician":
        requests = Request.query.filter_by(technician_id=current_user.id)\
                                .order_by(Request.created_at.desc()).all()
        
        assigned_count    = Request.query.filter_by(technician_id=current_user.id, status="Assigned").count()
        in_progress_count = Request.query.filter_by(technician_id=current_user.id, status="In Progress").count()
        completed_count   = Request.query.filter_by(technician_id=current_user.id, status="Completed").count()

        return render_template("technician_dashboard.html",
                               requests=requests,
                               active_page="dashboard",
                               current_user=current_user,
                               assigned_count=assigned_count,
                               in_progress_count=in_progress_count,
                               completed_count=completed_count)

    else:
        flash("Unknown role", "danger")
        return redirect(url_for("login"))



# ================= ASSIGN TECHNICIAN =================

@app.route("/assign/<int:req_id>", methods=["POST"])
@login_required
def assign(req_id):
    req = Request.query.get_or_404(req_id)
    req.technician_id = request.form["technician_id"]
    req.status = "Assigned"
    db.session.commit()
    flash("Technician assigned")
    return redirect(url_for("dashboard"))

# ================= UPDATE STATUS =================

app.route("/update_status/<int:req_id>", methods=["POST"])
@login_required
def update_status(req_id):
    if current_user.role != "Technician":
        flash("Only technicians can update status", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(req_id)

    if req.technician_id != current_user.id:
        flash("This task is not assigned to you", "danger")
        return redirect(url_for("dashboard"))

    new_status = request.form.get("status")
    allowed = ["Assigned", "In Progress", "Completed"]

    if new_status in allowed:
        if req.status == "Completed" and new_status != "Completed":
            flash("Completed tasks cannot be changed back", "warning")
        else:
            req.status = new_status
            db.session.commit()
            flash(f"Status updated to {new_status}", "success")
    else:
        flash("Invalid status", "danger")

    return redirect(url_for("technician_assigned_work"))

# ================= NEW REQUEST =================

@app.route('/new-request', methods=['GET', 'POST'])
@login_required
def new_request():
    if current_user.role != "Student":
        flash("Only students can submit requests.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == 'POST':
        room_number = request.form.get('room_number')
        category    = request.form.get('category')
        priority    = request.form.get('priority')
        description = request.form.get('description')

        if not all([room_number, category, priority, description]):
            flash("Please fill in all fields", "danger")
            return redirect(url_for('new_request'))

        new_req = Request(
            user_id=current_user.id,
            room_number=room_number.strip(),
            category=category,
            priority=priority,
            description=description.strip()
        )

        try:
            db.session.add(new_req)
            db.session.commit()
            flash("Maintenance request submitted successfully!", "success")
            return redirect(url_for('my_requests'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error saving request: {str(e)}", "danger")

    return render_template('student/new_request.html')

# ================= MY REQUESTS =================

@app.route('/my-requests')
@login_required
def my_requests():
    if current_user.role != "Student":
        flash("Unauthorized access.", "danger")
        return redirect(url_for("dashboard"))

    requests = Request.query.filter_by(user_id=current_user.id).order_by(Request.created_at.desc()).all()
    return render_template('student/my_requests.html', requests=requests)

# Make sure this route exists (from previous messages):
@app.route("/requests")
@login_required
def requests():
    if current_user.role.lower() != "admin":
        flash("Only admins can view all requests.", "danger")
        return redirect(url_for("dashboard"))
    
    requests = Request.query.order_by(Request.created_at.desc()).all()
    technicians = User.query.filter_by(role="Technician").all()

    # ← Add this block
    for req in requests:
        student = User.query.get(req.user_id)
        req.student_name = student.full_name if student else "Unknown Student"

        # Bonus: also add technician name (optional but useful)
        if req.technician_id:
            tech = User.query.get(req.technician_id)
            req.technician_name = tech.full_name if tech else "Unknown Technician"
        else:
            req.technician_name = "Not assigned"

    return render_template("admin/requests.html", 
                           requests=requests, 
                           technicians=technicians,
                           User=User)

@app.route("/users")
@login_required
def users():
    if current_user.role.lower() != "admin":
        flash("Only admins can view the users list.", "danger")
        return redirect(url_for("dashboard"))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)

# ================= EDIT REQUEST =================

@app.route('/requests/<int:request_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_request(request_id):
    if current_user.role != "Student":
        flash("Only students can edit their requests.", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(request_id)

    # Ownership check
    if req.user_id != current_user.id:
        flash("You can only edit your own requests.", "danger")
        return redirect(url_for("my_requests"))

    # Status protection
    if req.status in ["Assigned", "Completed"]:
        flash("This request can no longer be edited.", "warning")
        return redirect(url_for("my_requests"))

    if request.method == "POST":
        room_number = request.form.get("room_number", "").strip()
        category    = request.form.get("category", "").strip()
        priority    = request.form.get("priority", "").strip()
        description = request.form.get("description", "").strip()

        if not all([room_number, category, priority, description]):
            flash("All fields are required.", "danger")
            return redirect(url_for("edit_request", request_id=request_id))

        # Update fields
        req.room_number  = room_number
        req.category     = category
        req.priority     = priority
        req.description  = description
        # Note: status, technician_id, created_at are NOT changed here

        try:
            db.session.commit()
            flash("Request updated successfully!", "success")
            return redirect(url_for("my_requests"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating request: {str(e)}", "danger")

    # GET → show form with current values
    return render_template(
        "student/edit_request.html",
        request=req,           # passing the object so fields can be pre-filled
        current_user=current_user
    )


# ================= DELETE REQUEST =================

@app.route('/requests/<int:request_id>/delete', methods=['POST'])
@login_required
def delete_request(request_id):
    if current_user.role != "Student":
        flash("Only students can delete their requests.", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(request_id)

    # Ownership check
    if req.user_id != current_user.id:
        flash("You can only delete your own requests.", "danger")
        return redirect(url_for("my_requests"))

    # Status protection (same rule as edit)
    if req.status in ["Assigned", "Completed"]:
        flash("Cannot delete a request that has been assigned or completed.", "warning")
        return redirect(url_for("my_requests"))

    try:
        db.session.delete(req)
        db.session.commit()
        flash("Request deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting request: {str(e)}", "danger")

    return redirect(url_for("my_requests"))


# ================= EDIT REQUEST =================
@app.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.role.lower() != 'admin':
        flash("Only admins can edit users.", "danger")
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash("You cannot edit your own account from here.", "warning")
        return redirect(url_for('users'))
    
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        role = request.form.get('role', '').strip().title()  # Admin, Student, Technician
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not full_name or not role:
            flash("Full name and role are required.", "danger")
            return redirect(url_for('edit_user', user_id=user_id))

        user.full_name = full_name
        user.role = role

        # Optional password change
        if new_password and confirm_password:
            if new_password == confirm_password:
                user.password_hash = generate_password_hash(new_password)
            else:
                flash("Passwords do not match.", "danger")
                return redirect(url_for('edit_user', user_id=user_id))

        db.session.commit()
        flash(f"User {user.full_name} updated successfully.", "success")
        return redirect(url_for('users'))

    return render_template('admin/edit_user.html', user=user)

# ================= DELETE REQUEST =================
@app.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role.lower() != 'admin':
        flash("Only admins can delete users.", "danger")
        return redirect(url_for('users'))
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for('users'))
    
    # Optional: prevent deleting last admin
    if user.role.lower() == 'admin' and User.query.filter_by(role='Admin').count() <= 1:
        flash("Cannot delete the last admin account.", "danger")
        return redirect(url_for('users'))
    
    db.session.delete(user)
    db.session.commit()
    
    flash(f"User {user.full_name} deleted.", "success")
    return redirect(url_for('users'))

# ================= Technician =================
    
# 2. Technician assigned work page
@app.route("/technician/assigned-work")
@login_required
def technician_assigned_work():
    if current_user.role != "Technician":
        flash("Access denied", "danger")
        return redirect(url_for("dashboard"))

    requests = Request.query.filter_by(technician_id=current_user.id)\
                            .order_by(Request.created_at.desc()).all()

    return render_template("technician_dashboard.html",
                           requests=requests,
                           active_page="assigned",
                           current_user=current_user)


# ================= adding a user =================
# routes.py
@app.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    form = AddUserForm()
    if form.validate_on_submit():
        # Check if email already exists
        existing = User.query.filter_by(email=form.email.data.lower()).first()
        if existing:
            flash('This email is already registered.', 'danger')
            return render_template('add_user.html', form=form)

        hashed_pw = generate_password_hash(form.password.data)

        user = User(
            full_name = form.full_name.data.strip(),
            email     = form.email.data.lower().strip(),
            password_hash = hashed_pw,               # ← hashed!
            role      = form.role.data
        )
        db.session.add(user)
        db.session.commit()

        flash('User created successfully!', 'success')
        return redirect(url_for('users'))

    return render_template('add_user.html', form=form)
# ================= EMAIL NOTIFICATION =================

def send_email(to, subject, body):
    msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[to])
    msg.body = body
    mail.send(msg)

@app.route("/notify/<int:req_id>")
@login_required
def notify(req_id):
    req = Request.query.get_or_404(req_id)
    user = User.query.get(req.user_id)
    send_email(user.email, "Maintenance Update",
               f"Your request #{req.id} status is {req.status}")
    flash("Email sent")
    return redirect(url_for("dashboard"))

# ================= CREATE REQUEST (Legacy - Redirect to New) =================

@app.route("/create_request", methods=["POST"])
@login_required
def create_request():
    if current_user.role != "Student":
        return "Unauthorized"
    # Redirect to new_request for consistency
    return redirect(url_for("new_request"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        users = [
            ("Admin User", "admin@gmail.com", "admin123", "Admin"),
            ("Student User", "student@gmail.com", "student123", "Student"),
            ("Technician User", "tech@gmail.com", "tech123", "Technician")
        ]

        for name, email, password, role in users:
            if not User.query.filter_by(email=email).first():
                user = User(
                    full_name=name,
                    email=email,
                    password_hash=generate_password_hash(password),
                    role=role
                )
                db.session.add(user)

        db.session.commit()

    app.run(debug=True)