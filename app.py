from flask import Flask, render_template, redirect, url_for, request, flash ,jsonify
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
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import atexit
import os
import os
from werkzeug.utils import secure_filename
from typing import Optional
from wtforms.validators import DataRequired, Length, Optional


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
        choices=[('admin', 'Admin'), ('student', 'Student'), 
                 ('plumber', 'Plumber'), ('cleaner', 'Cleaner'), 
                 ('electrician', 'Electrician'), ('technician', 'Technician'),
                 ('pest_controller', 'Pest Controller')],
        validators=[DataRequired()]
    )
    room_number = StringField(
        'Room Number',
        validators=[Optional(), Length(max=20)]
    )
    submit = SubmitField('Create User')

app = Flask(__name__)

scheduler = BackgroundScheduler()
scheduler.start()

# Make sure scheduler shuts down cleanly
atexit.register(lambda: scheduler.shutdown())

UPLOAD_FOLDER = os.path.join('static', 'uploads')   # recommended location
# or UPLOAD_FOLDER = 'uploads' if you prefer separate folder
app.config['SECRET_KEY'] = 'secretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///maintenance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Email configuration (Use your Gmail credentials)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'thembelanibuthelezi64@gmail.com'
app.config['MAIL_PASSWORD'] = 'iuuocjnhsocusnrz'

db = SQLAlchemy(app)
mail = Mail(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
# Allowed file extensions for uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}  # ← customize this list

def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# =================Notification Icon =================

@app.context_processor
def inject_notifications():
    if not current_user.is_authenticated:
        return {
            'unread_count': 0,
            'has_unread': False
        }
    
    unread_count = current_user.unread_notifications_count()
    return {
        'unread_count': unread_count,
        'has_unread': unread_count > 0
    }
    
@app.route('/notifications/mark-read/<int:notif_id>', methods=['POST'])
@login_required
def mark_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id != current_user.id:
        return jsonify({'success': False}), 403
    if not notif.is_read:
        notif.is_read = True
        db.session.commit()
    return jsonify({'success': True})


@app.route('/notifications/unread-count')
@login_required
def unread_count():
    return jsonify({
        'unread': current_user.unread_notifications_count()
    })


# Optional – full list page (for "View all")
@app.route('/notifications')
@login_required
def notifications_all():
    notifs = current_user.notifications.order_by(Notification.created_at.desc()).all()
    return render_template('notifications_all.html', notifications=notifs)
    
# ================= MODELS =================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(200))
    role = db.Column(db.String(20))  # admin, student, plumber, cleaner, electrician, technician, pest_controller
    room_number = db.Column(db.String(20), nullable=True)  # Only for students
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def unread_notifications_count(self):
        return self.notifications.filter_by(is_read=False).count()

    def get_notifications(self, limit=12):
        return self.notifications.order_by(Notification.created_at.desc()).limit(limit).all()


class Request(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)  # Student who made the request
    staff_id = db.Column(db.Integer, nullable=True)  # Assigned staff member (plumber, cleaner, etc.)
    room_number = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50))  # This will match staff roles
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default="Pending")
    photo_path = db.Column(db.String(200), nullable=True)  # Path to uploaded photo
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Request {self.id} - {self.room_number}>"
    
    
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    
    # ─── New fields ───────────────────────────────────────
    type = db.Column(db.String(30), default='request', nullable=False)   # 'request', 'reminder', 'system', etc.
    related_request_id = db.Column(db.Integer, db.ForeignKey('request.id'), nullable=True)
    related_object_id  = db.Column(db.Integer, nullable=True)            # generic — can point to reminder ID, etc.
    # ──────────────────────────────────────────────────────
    
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic', cascade="all, delete-orphan"))
    request = db.relationship('Request', backref='notifications', lazy=True)

    def __repr__(self):
        return f"<Notif {self.id} {self.type} for user {self.user_id}>"

def check_and_create_reminder_notifications():
    with app.app_context():   # very important!
        # Example logic — adjust to your real needs
        # e.g. requests that are Pending for > 48 hours
        overdue = Request.query.filter(
            Request.status == "Pending",
            Request.created_at <= datetime.utcnow() - timedelta(hours=48)
        ).all()

        for req in overdue:
            student = User.query.get(req.user_id)
            if not student:
                continue

            # Check if we already sent a reminder recently (avoid spam)
            recent_reminder = Notification.query.filter(
                Notification.user_id == student.id,
                Notification.type == 'reminder',
                Notification.related_request_id == req.id,
                Notification.created_at >= datetime.utcnow() - timedelta(hours=24)
            ).first()

            if recent_reminder:
                continue

            message = f"Reminder: Your maintenance request #{req.id} (Room {req.room_number}) is still pending for over 2 days."

            notif = Notification(
                user_id=student.id,
                message=message,
                type='reminder',
                related_request_id=req.id
            )
            db.session.add(notif)
            db.session.commit()

            # Optional: also send email
            # send_email(student.email, "Maintenance Reminder", message)

# Schedule it — every 15 minutes
scheduler.add_job(
    func=check_and_create_reminder_notifications,
    trigger=IntervalTrigger(minutes=1),
    id='maintenance_reminders',
    name='Check for overdue requests and create reminders',
    replace_existing=True
)  

@app.route('/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    # Mark all as read, or specific ones
    for notif in current_user.notifications.filter_by(is_read=False).all():
        notif.is_read = True
    db.session.commit()
    return '', 204  # no content - for AJAX

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))

        if current_user.role != 'admin':
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))

        if current_user.role == 'admin' or current_user.role == 'student':
            flash("Access denied. Staff only.", "danger")
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function

# Custom filter
@app.template_filter('format_datetime')
def format_datetime(value, format='%Y-%m-%d %H:%M'):
    if value is None:
        value = datetime.now()
    return value.strftime(format)
# ================= HELPER FUNCTIONS FOR EMAIL NOTIFICATIONS =================

def get_admin_emails():
    """Return list of emails of all admin users (case-insensitive)"""
    admins = User.query.filter(User.role.ilike('%admin%')).all()
    return [admin.email for admin in admins if admin.email]


def notify_admins_new_request(new_request):
    admin_emails = get_admin_emails()
    if not admin_emails:
        return

    student = current_user
    subject = f"New Maintenance Request #{new_request.id} — Room {new_request.room_number}"

    html_content = render_template(
        'emails/new_request_notification.html',
        request_id=new_request.id,
        submitted_by_name=student.full_name,
        submitted_by_email=student.email,
        room_number=new_request.room_number,
        category=new_request.category,
        priority=new_request.priority,
        description=new_request.description,
        status=new_request.status,
        created_at=new_request.created_at.strftime('%Y-%m-%d %H:%M UTC'),
        has_photo=bool(new_request.photo_path),
        review_url="http://127.0.0.1:5000/requests"
    )

    try:
        msg = Message(
            subject=subject,
            sender=app.config['MAIL_USERNAME'],
            recipients=admin_emails,
            body="New maintenance request submitted.",
            html=html_content
        )

        # Attach photo if it exists
        if new_request.photo_path:
            full_path = os.path.join('static', new_request.photo_path)

            if os.path.exists(full_path):
                with open(full_path, 'rb') as f:
                    data = f.read()

                ext = new_request.photo_path.rsplit('.', 1)[-1].lower()
                mime = f"image/{'jpeg' if ext in ('jpg','jpeg') else ext}"

                msg.attach(
                    filename=f"photo.{ext}",
                    content_type=mime,
                    data=data
                )

        mail.send(msg)
        print(f"Notification sent for request #{new_request.id}")

    except Exception as e:
        print(f"Email failed: {e}")
        
def create_notification(user_id, message, notif_type='request', related_request_id=None):
    """Create an in-app notification for a user"""
    notif = Notification(
        user_id=user_id,
        message=message,
        type=notif_type,
        related_request_id=related_request_id
    )
    db.session.add(notif)
    # We commit later (in the route) to allow batching


def notify_user_email(user, subject, html_template, **template_vars):
    """Send nicely formatted email to one user"""
    try:
        html_content = render_template(html_template, **template_vars)
        msg = Message(
            subject=subject,
            sender=app.config['MAIL_USERNAME'],
            recipients=[user.email],
            body="This is an automated maintenance system update.",
            html=html_content
        )
        mail.send(msg)
        print(f"→ Email sent to {user.email} — {subject}")
    except Exception as e:
        print(f"→ Email failed for {user.email}: {e}")
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
@admin_required
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        role = request.form.get('role', '').strip().lower()
        room_number = request.form.get('room_number', '').strip()

        if not full_name or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('register'))

        # Validate room number for students
        if role == 'student' and not room_number:
            flash('Room number is required for students.', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))
            
        password_hash = generate_password_hash(password)
        
        new_user = User(
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            role=role,
            room_number=room_number if role == 'student' else None,
            created_at=datetime.utcnow()
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('User created successfully!', 'success')
            return redirect(url_for('users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')
            return redirect(url_for('register'))
    
    return render_template('admin/register.html')

# ================= DASHBOARD =================

@app.route("/dashboard")
@login_required
def dashboard():
    # Common variables used across multiple roles
    notifications = current_user.get_notifications(limit=12)
    unread_count = current_user.unread_notifications_count()

    if current_user.role == "admin":
        total_requests = Request.query.count()
        pending_requests = Request.query.filter_by(status="Pending").count()
        in_progress = Request.query.filter_by(status="In Progress").count()
        completed = Request.query.filter_by(status="Completed").count()

        recent_requests = Request.query.order_by(Request.created_at.desc()).limit(10).all()

        # Category breakdown
        categories = {}
        for cat in ['plumber', 'cleaner', 'electrician', 'technician', 'pest_controller']:
            categories[cat] = Request.query.filter_by(category=cat).count()

        return render_template(
            "admin/dashboard.html",
            total_requests=total_requests,
            pending_requests=pending_requests,
            in_progress=in_progress,
            completed=completed,
            recent_requests=recent_requests,
            categories=categories,
            notifications=notifications,
            unread_count=unread_count
        )

    elif current_user.role.lower() == "student":
        # Unified student handling (ignores case difference)
        requests = Request.query.filter_by(user_id=current_user.id)\
                               .order_by(Request.created_at.desc()).all()

        pending_count = Request.query.filter_by(
            user_id=current_user.id, status="Pending"
        ).count()
        in_progress_count = Request.query.filter_by(
            user_id=current_user.id, status="In Progress"
        ).count()
        completed_count = Request.query.filter_by(
            user_id=current_user.id, status="Completed"
        ).count()

        return render_template(
            "student/dashboard.html",  # ← make sure this template exists
            requests=requests,
            pending_count=pending_count,
            in_progress_count=in_progress_count,
            completed_count=completed_count,
            notifications=notifications,
            unread_count=unread_count
        )

    elif current_user.role == "Technician":
        requests = Request.query.filter_by(technician_id=current_user.id)\
                               .order_by(Request.created_at.desc()).all()

        pending_count = Request.query.filter_by(
            technician_id=current_user.id, status="Pending"
        ).count()
        in_progress_count = Request.query.filter_by(
            technician_id=current_user.id, status="In Progress"
        ).count()
        completed_count = Request.query.filter_by(
            technician_id=current_user.id, status="Completed"
        ).count()

        return render_template(
            "technician/dashboard.html",  # ← adjust template name if needed
            requests=requests,
            pending_count=pending_count,
            in_progress_count=in_progress_count,
            completed_count=completed_count,
            current_user=current_user,
            notifications=notifications,
            unread_count=unread_count
        )

    else:
        # Other staff roles (plumber, cleaner, electrician, pest_controller, etc.)
        requests = Request.query.filter_by(staff_id=current_user.id)\
                               .order_by(Request.created_at.desc()).all()

        pending_count = Request.query.filter_by(
            staff_id=current_user.id, status="Pending"
        ).count()
        in_progress_count = Request.query.filter_by(
            staff_id=current_user.id, status="In Progress"
        ).count()
        completed_count = Request.query.filter_by(
            staff_id=current_user.id, status="Completed"
        ).count()

        return render_template(
            "staff/dashboard.html",  # ← adjust template name if needed
            requests=requests,
            pending_count=pending_count,
            in_progress_count=in_progress_count,
            completed_count=completed_count,
            notifications=notifications,
            unread_count=unread_count
        )

    # Fallback - should rarely reach here if roles are properly set
    flash("Unknown or invalid user role", "danger")
    return redirect(url_for("login"))


# ================= ASSIGN TECHNICIAN =================



@app.route("/assign/<int:req_id>", methods=["POST"], endpoint="assign_post")
@login_required
@admin_required
def assign(req_id):
    req = Request.query.get_or_404(req_id)

    if req.status == "Completed":
        flash("Cannot assign technician to already completed request.", "warning")
        return redirect(url_for("requests"))

    try:
        technician_id = int(request.form["technician_id"])
    except (KeyError, ValueError):
        flash("No technician selected.", "danger")
        return redirect(url_for("requests"))

    technician = User.query.get(technician_id)
    if not technician or technician.role.lower() != "technician":
        flash("Invalid technician selected.", "danger")
        return redirect(url_for("requests"))

    # ─── Update request ───────────────────────────────────────
    old_technician_id = req.technician_id   # for re-assignment detection

    req.technician_id = technician.id
    req.status = "Assigned"
    
    # ─── Create notifications ─────────────────────────────────
    student = User.query.get(req.user_id)
    if not student:
        print(f"Warning: Student user {req.user_id} not found for request #{req.id}")

    # Message to student
    student_msg = (
        f"Your maintenance request #{req.id} (Room {req.room_number}) "
        f"has been assigned to technician {technician.full_name}."
    )
    create_notification(
        user_id=req.user_id,
        message=student_msg,
        notif_type='assignment',
        related_request_id=req.id
    )

    # Message to technician
    tech_msg = (
        f"You have been assigned to maintenance request #{req.id} "
        f"(Room {req.room_number} – {req.category}). "
        f"Priority: {req.priority}. Please review."
    )
    create_notification(
        user_id=technician.id,
        message=tech_msg,
        notif_type='assignment',
        related_request_id=req.id
    )

    # ─── Commit all changes + notifications ───────────────────
    db.session.commit()

    # ─── Optional: send emails ────────────────────────────────
    if student:
        notify_user_email(
            user=student,
            subject=f"Request #{req.id} Assigned – {req.room_number}",
            html_template='emails/request_assigned_student.html',
            request_id=req.id,
            room_number=req.room_number,
            technician_name=technician.full_name,
            category=req.category,
            priority=req.priority,
            description=req.description,
            status=req.status
        )

    notify_user_email(
        user=technician,
        subject=f"New Assignment – Request #{req.id} ({req.room_number})",
        html_template='emails/request_assigned_technician.html',
        request_id=req.id,
        room_number=req.room_number,
        student_name=student.full_name if student else "Unknown",
        category=req.category,
        priority=req.priority,
        description=req.description,
        status=req.status
    )

    # ─── Feedback ─────────────────────────────────────────────
    action = "Re-assigned" if old_technician_id else "Assigned"
    flash(f"Request {action} to {technician.full_name}", "success")
    
    return redirect(url_for("requests"))   # or "dashboard" — your choice

# ================= UPDATE STATUS =================

@app.route("/update_status/<int:req_id>", methods=["POST"])
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

@app.route('/new_request', methods=['GET', 'POST'])
@login_required
def new_request():
    if current_user.role != "student":
        flash("Only students can submit requests.", "danger")
        return redirect(url_for("my_requests"))

    if request.method == 'POST':
        room_number = request.form.get('room_number', current_user.room_number)
        category = request.form.get('category')
        priority = request.form.get('priority')
        description = request.form.get('description')
        
        # Handle file upload
        photo_path = None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo_path = f"uploads/{filename}"

        if not all([room_number, category, priority, description]):
            flash("Please fill in all required fields", "danger")
            return redirect(url_for('new_request'))

        new_req = Request(
            user_id=current_user.id,
            room_number=room_number.strip(),
            category=category,
            priority=priority,
            description=description.strip(),
            photo_path=photo_path
        )

        try:
            db.session.add(new_req)
            db.session.commit()
            # ─────────────── NEW ───────────────
            # Notify all admins about the new request
            notify_admins_new_request(new_req)
            # ───────────────────────────────────
            flash("Maintenance request submitted successfully!", "success")
            return redirect(url_for('my_requests'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error saving request: {str(e)}", "danger")

    # Pre-populate with student's room number
    return render_template('student/new_request.html', 
                         default_room=current_user.room_number)

# ================= MY REQUESTS =================

@app.route('/my-requests')
@login_required
def my_requests():
    if current_user.role != "student":
        flash("Unauthorized access.", "danger")
        return redirect(url_for("dashboard"))

    requests = Request.query.filter_by(user_id=current_user.id)\
                           .order_by(Request.created_at.desc()).all()
    
    # Add staff names to requests
    for req in requests:
        if req.staff_id:
            staff = User.query.get(req.staff_id)
            req.staff_name = staff.full_name if staff else "Unknown"
    
    return render_template('student/my_requests.html', requests=requests)

# ================= ADMIN REQUESTS VIEW =================

@app.route("/requests")
@login_required
@admin_required
def requests():
    requests = Request.query.order_by(Request.created_at.desc()).all()
    
    # Get all staff members by category
    staff_by_category = {}
    staff_roles = ['plumber', 'cleaner', 'electrician', 'technician', 'pest_controller']
    for role in staff_roles:
        staff_by_category[role] = User.query.filter_by(role=role).all()
    
    # Add student and staff names
    for req in requests:
        student = User.query.get(req.user_id)
        req.student_name = student.full_name if student else "Unknown Student"
        req.student_room = student.room_number if student else "Unknown"
        
        if req.staff_id:
            staff = User.query.get(req.staff_id)
            req.staff_name = staff.full_name if staff else "Unknown"
        else:
            req.staff_name = "Not assigned"

    return render_template("admin/requests.html", 
                         requests=requests,
                         staff_by_category=staff_by_category,
                         User=User)

# ================= USERS MANAGEMENT =================

@app.route("/users")
@login_required
@admin_required
def users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)

@app.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash("You cannot edit your own account from here.", "warning")
        return redirect(url_for('users'))
    
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        role = request.form.get('role', '').strip().lower()
        room_number = request.form.get('room_number', '').strip()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not full_name or not role:
            flash("Full name and role are required.", "danger")
            return redirect(url_for('edit_user', user_id=user_id))

        # Validate room number for students
        if role == 'student' and not room_number:
            flash("Room number is required for students.", "danger")
            return redirect(url_for('edit_user', user_id=user_id))

        user.full_name = full_name
        user.role = role
        user.room_number = room_number if role == 'student' else None

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

@app.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for('users'))
    
    # Prevent deleting last admin
    if user.role == 'admin' and User.query.filter_by(role='admin').count() <= 1:
        flash("Cannot delete the last admin account.", "danger")
        return redirect(url_for('users'))
    
    db.session.delete(user)
    db.session.commit()
    
    flash(f"User {user.full_name} deleted.", "success")
    return redirect(url_for('users'))

# ================= ASSIGN STAFF =================

@app.route("/assign/<int:req_id>", methods=["POST"])
@login_required
@admin_required
def assign(req_id):
    req = Request.query.get_or_404(req_id)
    staff_id = request.form.get("staff_id")
    
    if staff_id:
        staff = User.query.get(staff_id)
        if staff and staff.role == req.category:
            req.staff_id = staff_id
            req.status = "Assigned"
            db.session.commit()
            flash(f"Assigned to {staff.full_name}", "success")
        else:
            flash("Invalid staff assignment", "danger")
    else:
        flash("Please select a staff member", "danger")
    
    return redirect(url_for("requests"))

# ================= UPDATE STATUS (Staff) =================

@app.route("/update_status/<int:req_id>", methods=["POST"],endpoint="update_request_status")
@login_required
def update_status(req_id):
    # Allow both staff and admin to update status
    if current_user.role == 'student':
        flash("Only staff can update status", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(req_id)

    # If staff (not admin), check if assigned to them
    if current_user.role != 'admin' and req.staff_id != current_user.id:
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

    # Redirect based on role
    if current_user.role == 'admin':
        return redirect(url_for("requests"))
    else:
        return redirect(url_for("staff_assigned_work"))

# ================= STAFF ASSIGNED WORK =================

@app.route("/staff/assigned-work")
@login_required
def staff_assigned_work():
    if current_user.role == 'admin' or current_user.role == 'student':
        flash("Access denied", "danger")
        return redirect(url_for("dashboard"))

    requests = Request.query.filter_by(staff_id=current_user.id)\
                           .order_by(Request.created_at.desc()).all()
    
    # Add student names and rooms
    for req in requests:
        student = User.query.get(req.user_id)
        req.student_name = student.full_name if student else "Unknown"
        req.student_room = student.room_number if student else "Unknown"

    return render_template("staff/assigned_work.html",
                         requests=requests,
                         role_display=current_user.role.replace('_', ' ').title(),
                         current_user=current_user)

# ================= EDIT REQUEST (Student) =================

@app.route('/requests/<int:request_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_request(request_id):
    if current_user.role != "student":
        flash("Only students can edit their requests.", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(request_id)

    if req.user_id != current_user.id:
        flash("You can only edit your own requests.", "danger")
        return redirect(url_for("my_requests"))

    if req.status in ["Assigned", "In Progress", "Completed"]:
        flash("This request can no longer be edited.", "warning")
        return redirect(url_for("my_requests"))

    if request.method == "POST":
        room_number = request.form.get("room_number", "").strip()
        category = request.form.get("category", "").strip()
        priority = request.form.get("priority", "").strip()
        description = request.form.get("description", "").strip()

        if not all([room_number, category, priority, description]):
            flash("All fields are required.", "danger")
            return redirect(url_for("edit_request", request_id=request_id))

        # Handle photo upload
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '' and allowed_file(file.filename):
                # Delete old photo if exists
                if req.photo_path:
                    old_photo = os.path.join('static', req.photo_path)
                    if os.path.exists(old_photo):
                        os.remove(old_photo)
                
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                req.photo_path = f"uploads/{filename}"

        req.room_number = room_number
        req.category = category
        req.priority = priority
        req.description = description

        try:
            db.session.commit()
            flash("Request updated successfully!", "success")
            return redirect(url_for("my_requests"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating request: {str(e)}", "danger")

    return render_template("student/edit_request.html", request=req)

# ================= DELETE REQUEST (Student) =================

@app.route('/requests/<int:request_id>/delete', methods=['POST'])
@login_required
def delete_request(request_id):
    if current_user.role != "student":
        flash("Only students can delete their requests.", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(request_id)

    if req.user_id != current_user.id:
        flash("You can only delete your own requests.", "danger")
        return redirect(url_for("my_requests"))

    if req.status in ["Assigned", "In Progress", "Completed"]:
        flash("Cannot delete a request that has been assigned or is in progress.", "warning")
        return redirect(url_for("my_requests"))

    # Delete photo if exists
    if req.photo_path:
        photo_file = os.path.join('static', req.photo_path)
        if os.path.exists(photo_file):
            os.remove(photo_file)

    try:
        db.session.delete(req)
        db.session.commit()
        flash("Request deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting request: {str(e)}", "danger")

    return redirect(url_for("my_requests"))

# ================= ADD USER FORM ROUTE =================

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    form = AddUserForm()
    if form.validate_on_submit():
        existing = User.query.filter_by(email=form.email.data.lower()).first()
        if existing:
            flash('This email is already registered.', 'danger')
            return render_template('admin/add_user.html', form=form)

        # Validate room number for students
        if form.role.data == 'student' and not form.room_number.data:
            flash('Room number is required for students.', 'danger')
            return render_template('admin/add_user.html', form=form)

        hashed_pw = generate_password_hash(form.password.data)

        user = User(
            full_name=form.full_name.data.strip(),
            email=form.email.data.lower().strip(),
            password_hash=hashed_pw,
            role=form.role.data,
            room_number=form.room_number.data if form.role.data == 'student' else None
        )
        db.session.add(user)
        db.session.commit()

        flash('User created successfully!', 'success')
        return redirect(url_for('users'))

    return render_template('admin/add_user.html', form=form)

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

# ================= VIEW PHOTO =================

@app.route('/view-photo/<int:request_id>')
@login_required
def view_photo(request_id):
    req = Request.query.get_or_404(request_id)
    
    # Check permissions
    if current_user.role == 'student' and req.user_id != current_user.id:
        flash("Access denied", "danger")
        return redirect(url_for('dashboard'))
    
    if current_user.role != 'admin' and current_user.role != 'student' and req.staff_id != current_user.id:
        flash("Access denied", "danger")
        return redirect(url_for('dashboard'))
    
    if not req.photo_path:
        flash("No photo available for this request", "warning")
        return redirect(request.referrer or url_for('dashboard'))
    
    return render_template('view_photo.html', request=req)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # Create default users if they don't exist
        default_users = [
            ("Admin User", "admin@gmail.com", "admin123", "admin", None),
            ("Student User", "student@gmail.com", "student123", "student", "101A"),
            ("Plumber User", "plumber@gmail.com", "plumber123", "plumber", None),
            ("Cleaner User", "cleaner@gmail.com", "cleaner123", "cleaner", None),
            ("Electrician User", "electrician@gmail.com", "electrician123", "electrician", None),
            ("Technician User", "tech@gmail.com", "tech123", "technician", None),
            ("Pest Controller User", "pest@gmail.com", "pest123", "pest_controller", None)
        ]

        for name, email, password, role, room in default_users:
            if not User.query.filter_by(email=email).first():
                user = User(
                    full_name=name,
                    email=email,
                    password_hash=generate_password_hash(password),
                    role=role,
                    room_number=room
                )
                db.session.add(user)

        db.session.commit()

    app.run(debug=True)