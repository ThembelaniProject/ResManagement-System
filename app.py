from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from datetime import datetime, timedelta
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField 
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
import os
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

# ================= FORM CLASSES =================
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

# ================= APP CONFIGURATION =================
app = Flask(__name__)

# Basic config
app.config['SECRET_KEY'] = 'secretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///maintenance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Upload config
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'thembelanibuthelezi64@gmail.com'
app.config['MAIL_PASSWORD'] = 'iuuocjnhsocusnrz'

# Password reset config
app.config['SECURITY_PASSWORD_SALT'] = 'your-password-salt-change-this-in-production'
app.config['RESET_TOKEN_EXPIRES'] = 3600  # Token valid for 1 hour

# ================= INITIALIZE EXTENSIONS =================
db = SQLAlchemy(app)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ================= SCHEDULER SETUP =================
scheduler = BackgroundScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# ================= ALLOWED FILE EXTENSIONS =================
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ================= MODELS =================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(200))
    role = db.Column(db.String(20))
    room_number = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def unread_notifications_count(self):
        return self.notifications.filter_by(is_read=False).count()

    def get_notifications(self, limit=12):
        return self.notifications.order_by(Notification.created_at.desc()).limit(limit).all()


class Request(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    staff_id = db.Column(db.Integer, nullable=True)
    room_number = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50))
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default="Pending")
    photo_path = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Request {self.id} - {self.room_number}>"
    
    
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(30), default='request', nullable=False)
    related_request_id = db.Column(db.Integer, db.ForeignKey('request.id'), nullable=True)
    related_object_id = db.Column(db.Integer, nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic', cascade="all, delete-orphan"))
    request = db.relationship('Request', backref='notifications', lazy=True)

    def __repr__(self):
        return f"<Notif {self.id} {self.type} for user {self.user_id}>"

# ================= PASSWORD RESET FUNCTIONS =================
def generate_reset_token(email):
    """Generate a password reset token"""
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    token = serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])
    print(f"🔑 Generated token for {email}: {token[:20]}...")
    return token

def verify_reset_token(token, expiration=3600):
    """Verify reset token and return email"""
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = serializer.loads(
            token,
            salt=app.config['SECURITY_PASSWORD_SALT'],
            max_age=expiration
        )
        print(f"✅ Token verified for email: {email}")
        return email
    except SignatureExpired:
        print("❌ Token expired")
        return None
    except BadSignature:
        print("❌ Invalid token signature")
        return None
    except Exception as e:
        print(f"❌ Token verification error: {str(e)}")
        return None

def send_reset_email(to_email, reset_url, user_name):
    """Send password reset email"""
    subject = "Password Reset Request - Residence Maintenance System"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 5px;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                text-align: center;
                border-radius: 5px 5px 0 0;
            }}
            .content {{
                padding: 20px;
            }}
            .button {{
                display: inline-block;
                padding: 12px 30px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 20px 0;
                font-weight: bold;
            }}
            .button:hover {{
                background: linear-gradient(135deg, #5a6fd6 0%, #6a43a0 100%);
            }}
            .footer {{
                text-align: center;
                padding: 20px;
                color: #777;
                font-size: 12px;
                border-top: 1px solid #ddd;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Password Reset Request</h2>
            </div>
            <div class="content">
                <p>Dear {user_name},</p>
                <p>We received a request to reset your password for the Residence Maintenance System.</p>
                <p>Click the button below to reset your password:</p>
                <div style="text-align: center;">
                    <a href="{reset_url}" class="button" style="color: white;">Reset Password</a>
                </div>
                <p>If the button doesn't work, copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #667eea; background: #f0f0f0; padding: 10px; border-radius: 5px;">{reset_url}</p>
                <p><strong>This link is valid for 1 hour.</strong></p>
                <p>If you didn't request a password reset, please ignore this email.</p>
            </div>
            <div class="footer">
                <p>This is an automated message, please do not reply.</p>
                <p>&copy; 2024 Residence Maintenance System</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_body = f"""
Dear {user_name},

We received a request to reset your password for the Residence Maintenance System.

Click the link below to reset your password:
{reset_url}

This link is valid for 1 hour.

If you didn't request a password reset, please ignore this email.

This is an automated message, please do not reply.
    """
    
    msg = Message(
        subject=subject,
        sender=app.config['MAIL_USERNAME'],
        recipients=[to_email],
        body=text_body,
        html=html_body
    )
    
    try:
        print(f"📧 Sending reset email to {to_email}")
        print(f"📧 Reset URL: {reset_url}")
        mail.send(msg)
        print(f"✅ Email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
# ================= NOTIFICATION FUNCTIONS =================
def check_and_create_reminder_notifications():
    with app.app_context():
        overdue = Request.query.filter(
            Request.status == "Pending",
            Request.created_at <= datetime.utcnow() - timedelta(hours=48)
        ).all()

        for req in overdue:
            student = User.query.get(req.user_id)
            if not student:
                continue

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

# Schedule reminder job
scheduler.add_job(
    func=check_and_create_reminder_notifications,
    trigger=IntervalTrigger(minutes=15),
    id='maintenance_reminders',
    name='Check for overdue requests and create reminders',
    replace_existing=True
)

# ================= DECORATORS =================
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

# ================= TEMPLATE FILTERS =================
@app.template_filter('format_datetime')
def format_datetime(value, format='%Y-%m-%d %H:%M'):
    if value is None:
        value = datetime.now()
    return value.strftime(format)

# ================= CONTEXT PROCESSORS =================
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

# ================= USER LOADER =================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================= AUTHENTICATION ROUTES =================
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("dashboard"))
        else:
            flash("Email or password is incorrect.", "danger")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ================= PASSWORD RESET ROUTES =================
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password page"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Please enter your email address.', 'danger')
            return render_template('forgot_password.html')
        
        user = User.query.filter_by(email=email).first()
        
        if user:
            token = generate_reset_token(email)
            reset_url = url_for('reset_password', token=token, _external=True)
            
            if send_reset_email(email, reset_url, user.full_name):
                flash('Password reset instructions have been sent to your email.', 'success')
            else:
                flash('Failed to send email. Please try again later.', 'danger')
        else:
            flash('If an account exists with this email, you will receive reset instructions.', 'info')
        
        return redirect(url_for('login'))
    
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password page"""
    print(f"🔍 Reset password route accessed with token: {token[:20]}...")
    
    email = verify_reset_token(token)
    print(f"🔍 Verified email: {email}")
    
    if not email:
        print("❌ Token verification failed")
        flash('Invalid or expired reset link. Please request a new one.', 'danger')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        print(f"🔍 Password reset form submitted for email: {email}")
        
        if not password:
            flash('Password is required.', 'danger')
            return render_template('reset_password.html', token=token)
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('reset_password.html', token=token)
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
        
        user = User.query.filter_by(email=email).first()
        print(f"🔍 User found: {user is not None}")
        
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('forgot_password'))
        
        # Update password
        user.password_hash = generate_password_hash(password)
        db.session.commit()
        print(f"✅ Password updated successfully for user: {user.email}")
        
        flash('Your password has been reset successfully! You can now login with your new password.', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html', token=token)
@app.route('/debug-reset/<email>')
def debug_reset(email):
    """Debug route to generate a reset link for testing"""
    user = User.query.filter_by(email=email).first()
    if user:
        token = generate_reset_token(email)
        reset_url = url_for('reset_password', token=token, _external=True)
        return f"""
        <h2>Debug Reset Link</h2>
        <p>Email: {email}</p>
        <p>Token: {token}</p>
        <p><a href="{reset_url}">{reset_url}</a></p>
        """
    return f"User {email} not found"
# ================= NOTIFICATION ROUTES =================
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

@app.route('/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    for notif in current_user.notifications.filter_by(is_read=False).all():
        notif.is_read = True
    db.session.commit()
    return '', 204

@app.route('/notifications/unread-count')
@login_required
def unread_count():
    return jsonify({
        'unread': current_user.unread_notifications_count()
    })

@app.route('/notifications')
@login_required
def notifications_all():
    notifs = current_user.notifications.order_by(Notification.created_at.desc()).all()
    return render_template('notifications_all.html', notifications=notifs)

# ================= ADMIN ROUTES =================
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

# ================= DASHBOARD ROUTE =================
@app.route("/dashboard")
@login_required
def dashboard():
    notifications = current_user.get_notifications(limit=12)
    unread_count = current_user.unread_notifications_count()

    if current_user.role == "admin":
        total_requests = Request.query.count()
        pending_requests = Request.query.filter_by(status="Pending").count()
        in_progress = Request.query.filter_by(status="In Progress").count()
        completed = Request.query.filter_by(status="Completed").count()
        recent_requests = Request.query.order_by(Request.created_at.desc()).limit(10).all()

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
            "student/dashboard.html",
            requests=requests,
            pending_count=pending_count,
            in_progress_count=in_progress_count,
            completed_count=completed_count,
            notifications=notifications,
            unread_count=unread_count
        )

    elif current_user.role == "technician":
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
            "technician/dashboard.html",
            requests=requests,
            pending_count=pending_count,
            in_progress_count=in_progress_count,
            completed_count=completed_count,
            current_user=current_user,
            notifications=notifications,
            unread_count=unread_count
        )

    else:
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
            "staff/dashboard.html",
            requests=requests,
            pending_count=pending_count,
            in_progress_count=in_progress_count,
            completed_count=completed_count,
            notifications=notifications,
            unread_count=unread_count
        )

    flash("Unknown or invalid user role", "danger")
    return redirect(url_for("login"))

# ================= EMAIL HELPER FUNCTIONS =================
def get_admin_emails():
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
    notif = Notification(
        user_id=user_id,
        message=message,
        type=notif_type,
        related_request_id=related_request_id
    )
    db.session.add(notif)

def notify_user_email(user, subject, html_template, **template_vars):
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

# ================= REQUEST ROUTES =================
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
            notify_admins_new_request(new_req)
            flash("Maintenance request submitted successfully!", "success")
            return redirect(url_for('my_requests'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error saving request: {str(e)}", "danger")

    return render_template('student/new_request.html', default_room=current_user.room_number)

@app.route('/my-requests')
@login_required
def my_requests():
    if current_user.role != "student":
        flash("Unauthorized access.", "danger")
        return redirect(url_for("dashboard"))

    page = request.args.get('page', 1, type=int)
    per_page = 10

    pagination = Request.query.filter_by(user_id=current_user.id)\
                              .order_by(Request.created_at.desc())\
                              .paginate(page=page, per_page=per_page)

    requests = pagination.items

    for req in requests:
        if req.staff_id:
            staff = User.query.get(req.staff_id)
            req.staff_name = staff.full_name if staff else "Unknown"

    return render_template('student/my_requests.html', requests=requests, pagination=pagination)

@app.route("/requests")
@login_required
@admin_required
def requests():
    page = request.args.get('page', 1, type=int)

    requests = Request.query.order_by(Request.created_at.desc()).paginate(
        page=page,
        per_page=10,
        error_out=False
    )
    
    staff_by_category = {}
    staff_roles = ['plumber', 'cleaner', 'electrician', 'technician', 'pest_controller']
    for role in staff_roles:
        staff_by_category[role] = User.query.filter_by(role=role).all()
    
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

        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '' and allowed_file(file.filename):
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

# ================= ASSIGNMENT ROUTES =================
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

# ================= STATUS UPDATE ROUTES =================
@app.route("/update_status/<int:req_id>", methods=["POST"])
@login_required
def update_status(req_id):
    if current_user.role == 'student':
        flash("Only staff can update status", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(req_id)

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

    if current_user.role == 'admin':
        return redirect(url_for("requests"))
    else:
        return redirect(url_for("staff_assigned_work"))

@app.route("/staff/assigned-work")
@login_required
def staff_assigned_work():
    if current_user.role == 'admin' or current_user.role == 'student':
        flash("Access denied", "danger")
        return redirect(url_for("dashboard"))

    requests = Request.query.filter_by(staff_id=current_user.id)\
                           .order_by(Request.created_at.desc()).all()
    
    for req in requests:
        student = User.query.get(req.user_id)
        req.student_name = student.full_name if student else "Unknown"
        req.student_room = student.room_number if student else "Unknown"

    return render_template("staff/assigned_work.html",
                         requests=requests,
                         role_display=current_user.role.replace('_', ' ').title(),
                         current_user=current_user)

# ================= USER MANAGEMENT ROUTES =================
@app.route("/users")
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    users = User.query.order_by(User.created_at.desc()).paginate(
        page=page,
        per_page=10,
        error_out=False
    )
    return render_template("admin/users.html", users=users)

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

        if role == 'student' and not room_number:
            flash("Room number is required for students.", "danger")
            return redirect(url_for('edit_user', user_id=user_id))

        user.full_name = full_name
        user.role = role
        user.room_number = room_number if role == 'student' else None

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
    
    if user.role == 'admin' and User.query.filter_by(role='admin').count() <= 1:
        flash("Cannot delete the last admin account.", "danger")
        return redirect(url_for('users'))
    
    db.session.delete(user)
    db.session.commit()
    
    flash(f"User {user.full_name} deleted.", "success")
    return redirect(url_for('users'))

# ================= MISC ROUTES =================
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

@app.route('/view-photo/<int:request_id>')
@login_required
def view_photo(request_id):
    req = Request.query.get_or_404(request_id)
    
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
# ================= TEST EMAIL ROUTE =================
@app.route('/test-email')
def test_email():
    """Test route to verify email configuration"""
    try:
        # Try to send a test email to yourself
        msg = Message(
            subject="Test Email from Maintenance System",
            sender=app.config['MAIL_USERNAME'],
            recipients=[app.config['MAIL_USERNAME']],  # Send to yourself
            body="This is a test email to verify your email configuration is working correctly."
        )
        mail.send(msg)
        return """
        <html>
        <body style="font-family: Arial; padding: 20px;">
            <h2 style="color: green;">✅ Email Test Successful!</h2>
            <p>A test email has been sent to <strong>{}</strong>.</p>
            <p>Check your inbox (and spam folder) to confirm.</p>
            <p><a href="/">Return to Home</a></p>
        </body>
        </html>
        """.format(app.config['MAIL_USERNAME'])
    except Exception as e:
        error_msg = str(e)
        return f"""
        <html>
        <body style="font-family: Arial; padding: 20px;">
            <h2 style="color: red;">❌ Email Test Failed</h2>
            <p><strong>Error:</strong> {error_msg}</p>
            <h3>Troubleshooting Steps:</h3>
            <ol>
                <li>Make sure you're using an App Password, not your regular Gmail password</li>
                <li>Enable 2-Factor Authentication on your Google account</li>
                <li>Generate a new App Password at: https://myaccount.google.com/apppasswords</li>
                <li>Update MAIL_PASSWORD in your config with the 16-digit app password</li>
                <li>Check if Google blocked the attempt: https://myaccount.google.com/security</li>
            </ol>
            <p><a href="/">Return to Home</a></p>
        </body>
        </html>
        """

# ================= MAIN =================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

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