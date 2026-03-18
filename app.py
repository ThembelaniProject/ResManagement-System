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
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    role = SelectField(
        'Role',
        choices=[('admin', 'Admin'), ('student', 'Student'),
                 ('plumber', 'Plumber'), ('cleaner', 'Cleaner'),
                 ('electrician', 'Electrician'), ('technician', 'Technician'),
                 ('pest_controller', 'Pest Controller')],
        validators=[DataRequired()]
    )
    room_number = StringField('Room Number', validators=[Optional(), Length(max=20)])
    submit = SubmitField('Create User')

# ────────────────────────────────────────────────
# App setup
# ────────────────────────────────────────────────
app = Flask(__name__)

# ──── Base directory & production-friendly paths ────
basedir = os.path.abspath(os.path.dirname(__file__))

# Create necessary folders
instance_dir = os.path.join(basedir, 'instance')
upload_dir   = os.path.join(basedir, 'static', 'uploads')
os.makedirs(instance_dir, exist_ok=True)
os.makedirs(upload_dir,   exist_ok=True)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-me-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_dir, 'maintenance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = upload_dir
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# Email configuration (use environment variables in production!)
app.config['MAIL_SERVER']   = 'smtp.gmail.com'
app.config['MAIL_PORT']     = 587
app.config['MAIL_USE_TLS']  = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME') or 'thembelanibuthelezi64@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD') or 'iuuocjnhsocusnrz'

db   = SQLAlchemy(app)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# ================= SCHEDULER SETUP =================
scheduler = BackgroundScheduler()
scheduler.start()

# ────────────────────────────────────────────────
# Background scheduler
# ────────────────────────────────────────────────
scheduler = BackgroundScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# ────────────────────────────────────────────────
# Notifications context processor
# ────────────────────────────────────────────────
@app.context_processor
def inject_notifications():
    if not current_user.is_authenticated:
        return {'unread_count': 0, 'has_unread': False}
    unread_count = current_user.unread_notifications_count()
    return {'unread_count': unread_count, 'has_unread': unread_count > 0}

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
    return jsonify({'unread': current_user.unread_notifications_count()})

@app.route('/notifications')
@login_required
def notifications_all():
    notifs = current_user.notifications.order_by(Notification.created_at.desc()).all()
    return render_template('notifications_all.html', notifications=notifs)


@app.route('/requests/<int:request_id>/rate', methods=['GET', 'POST'])
@login_required
def rate_request(request_id):
    if current_user.role != "student":
        flash("Only students can rate requests.", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(request_id)

    # Security: only allow rating your own requests
    if req.user_id != current_user.id:
        flash("You can only rate your own requests.", "danger")
        return redirect(url_for("my_requests"))

    if req.status != "Completed":
        flash("You can only rate completed requests.", "warning")
        return redirect(url_for("my_requests"))

    if req.rating is not None:
        flash("You have already rated this request.", "info")
        return redirect(url_for("my_requests"))

    if request.method == "POST":
        try:
            rating_str = request.form.get("rating")
            comment = request.form.get("comment", "").strip()

            if not rating_str or not rating_str.isdigit():
                flash("Please select a valid rating.", "danger")
                return redirect(url_for("rate_request", request_id=request_id))

            rating = int(rating_str)

            if not 1 <= rating <= 5:
                flash("Rating must be between 1 and 5 stars.", "danger")
                return redirect(url_for("rate_request", request_id=request_id))

            # Save rating
            req.rating = rating
            req.rating_comment = comment if comment else None
            req.rated_at = datetime.utcnow()

            # ────────────────────────────────────────────────
            # Update staff average rating
            # ────────────────────────────────────────────────
            if req.staff_id:
                staff = User.query.get(req.staff_id)
                if staff:
                    # Get all rated requests for this staff member
                    rated_requests = Request.query.filter(
                        Request.staff_id == staff.id,
                        Request.rating.isnot(None)
                    ).all()

                    if rated_requests:
                        total = sum(r.rating for r in rated_requests)
                        count = len(rated_requests)
                        staff.average_rating = round(total / count, 2)
                        staff.rating_count = count
                    else:
                        staff.average_rating = 0.0
                        staff.rating_count = 0

                    db.session.add(staff)

            db.session.commit()
            flash("Thank you for your feedback!", "success")

            # Optional: email notification to staff
            if req.staff_id:
                staff = User.query.get(req.staff_id)  # already queried earlier, but safe
                if staff and staff.email:
                    try:
                        msg = Message(
                            subject="New Rating Received",
                            sender=app.config['MAIL_USERNAME'],
                            recipients=[staff.email]
                        )
                        msg.body = (
                            f"Your work on request #{req.id} was rated {rating}/5 "
                            f"by the student."
                        )
                        if comment:
                            msg.body += f"\nComment: {comment}"
                        mail.send(msg)
                    except Exception as email_err:
                        app.logger.warning(f"Failed to send rating email: {email_err}")
                        # silent fail - user doesn't need to know

            return redirect(url_for("my_requests"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error saving rating: {str(e)}", "danger")
            # In production: log the error properly
            app.logger.error(f"Rating save failed for request {request_id}: {str(e)}")

    # GET: show rating form
    return render_template("student/rate_request.html", request=req)
# ────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    password_hash = db.Column(db.String(200))
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    role = db.Column(db.String(20))
    room_number = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # ─── NEW ──────────── (only meaningful for staff)
    average_rating = db.Column(db.Float, default=0.0, nullable=False)
    rating_count = db.Column(db.Integer, default=0, nullable=False)
    # ───────────────────────────────────────────────
    def update_average_rating(self):
        if self.rating_count == 0:
            self.average_rating = 0.0
        else:
            # We'll calculate from requests when needed, but store cached value
            pass  # see route below for actual logic

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
    # ─── NEW ───────────────────────────────────────
    rating = db.Column(db.Integer, nullable=True)             # 1–5
    rating_comment = db.Column(db.Text, nullable=True)
    rated_at = db.Column(db.DateTime, nullable=True)
    # ───────────────────────────────────────────────
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
            if not student: continue

            recent_reminder = Notification.query.filter(
                Notification.user_id == student.id,
                Notification.type == 'reminder',
                Notification.related_request_id == req.id,
                Notification.created_at >= datetime.utcnow() - timedelta(hours=24)
            ).first()

            if recent_reminder: continue

            message = f"Reminder: Your maintenance request #{req.id} (Room {req.room_number}) is still pending for over 2 days."
            notif = Notification(
                user_id=student.id,
                message=message,
                type='reminder',
                related_request_id=req.id
            )
            db.session.add(notif)
            db.session.commit()

scheduler.add_job(
    func=check_and_create_reminder_notifications,
    trigger=IntervalTrigger(minutes=15),
    id='maintenance_reminders',
    replace_existing=True
)

# ────────────────────────────────────────────────
# Decorators
# ────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in.", "warning")
            return redirect(url_for('login'))
        if current_user.role != 'admin':
            flash("Admin access only.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in.", "warning")
            return redirect(url_for('login'))
        if current_user.role in ['admin', 'student']:
            flash("Staff access only.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

# ────────────────────────────────────────────────
# Template filters
# ────────────────────────────────────────────────
@app.template_filter('format_datetime')
def format_datetime(value, format='%Y-%m-%d %H:%M'):
    if value is None:
        value = datetime.now()
    return value.strftime(format)

# ────────────────────────────────────────────────
# Email helpers (unchanged)
# ────────────────────────────────────────────────
def get_admin_emails():
    admins = User.query.filter(User.role.ilike('%admin%')).all()
    return [a.email for a in admins if a.email]

def notify_admins_new_request(new_request):
    admin_emails = get_admin_emails()
    if not admin_emails: return

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
        msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=admin_emails,
                      body="New maintenance request submitted.", html=html_content)

        if new_request.photo_path:
            full_path = os.path.join('static', new_request.photo_path)
            if os.path.exists(full_path):
                with open(full_path, 'rb') as f:
                    data = f.read()
                ext = new_request.photo_path.rsplit('.', 1)[-1].lower()
                mime = f"image/{'jpeg' if ext in ('jpg','jpeg') else ext}"
                msg.attach(filename=f"photo.{ext}", content_type=mime, data=data)

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

def notify_user_email(user, subject, html_template, **kwargs):
    try:
        html = render_template(html_template, **kwargs)
        msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[user.email],
                      body="Automated update.", html=html)
        mail.send(msg)
    except Exception as e:
        print(f"→ Email failed for {user.email}: {e}")

# ────────────────────────────────────────────────
# Login / Logout
# ────────────────────────────────────────────────
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Email or password incorrect.", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ────────────────────────────────────────────────
# Admin – Register user
# ────────────────────────────────────────────────
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

        if not all([full_name, email, password, role]):
            flash('Required fields missing.', 'danger')
            return redirect(url_for('register'))

        if role == 'student' and not room_number:
            flash('Room number required for students.', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))

        new_user = User(
            full_name=full_name,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            room_number=room_number if role == 'student' else None
        )
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('User created successfully!', 'success')
            return redirect(url_for('users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

    return render_template('admin/register.html')

# ────────────────────────────────────────────────
# Dashboard (already good – kept as is)
# ────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    notifications = current_user.get_notifications(limit=12)
    unread_count = current_user.unread_notifications_count()
    role = current_user.role.lower()

    if role == "admin":
        total_requests = Request.query.count()
        pending_requests = Request.query.filter_by(status="Pending").count()
        in_progress = Request.query.filter_by(status="In Progress").count()
        completed = Request.query.filter_by(status="Completed").count()
        recent_requests = Request.query.order_by(Request.created_at.desc()).limit(10).all()
        categories = {cat: Request.query.filter_by(category=cat).count()
                      for cat in ['plumber', 'cleaner', 'electrician', 'technician', 'pest_controller']}
        return render_template("admin/dashboard.html", **locals())

    elif role == "student":
        requests = Request.query.filter_by(user_id=current_user.id)\
                               .order_by(Request.created_at.desc()).all()
        pending_count = Request.query.filter_by(user_id=current_user.id, status="Pending").count()
        in_progress_count = Request.query.filter_by(user_id=current_user.id, status="In Progress").count()
        completed_count = Request.query.filter_by(user_id=current_user.id, status="Completed").count()
        return render_template("student/dashboard.html", **locals())

    elif role in ['technician', 'plumber', 'cleaner', 'electrician', 'pest_controller']:
        requests = Request.query.filter_by(staff_id=current_user.id)\
                               .order_by(Request.created_at.desc()).all()
        pending_count = Request.query.filter_by(staff_id=current_user.id, status="Pending").count()
        in_progress_count = Request.query.filter_by(staff_id=current_user.id, status="In Progress").count()
        completed_count = Request.query.filter_by(staff_id=current_user.id, status="Completed").count()
        role_display = current_user.role.replace('_', ' ').title()
        return render_template("staff/dashboard.html", **locals())

    else:
        flash("Unknown or invalid user role", "danger")
        return redirect(url_for("login"))

# ────────────────────────────────────────────────
# FIXED: Assignment (now works for all categories)
# ────────────────────────────────────────────────
@app.route("/assign/<int:req_id>", methods=["POST"])
@login_required
@admin_required
def assign(req_id):
    req = Request.query.get_or_404(req_id)

    if req.status == "Completed":
        flash("Cannot assign to completed request.", "warning")
        return redirect(url_for("requests"))

    staff_id_str = request.form.get("staff_id")
    if not staff_id_str:
        flash("No staff member selected.", "danger")
        return redirect(url_for("requests"))

    try:
        staff_id = int(staff_id_str)
    except ValueError:
        flash("Invalid staff selection.", "danger")
        return redirect(url_for("requests"))

    staff = User.query.get(staff_id)
    if not staff:
        flash("Selected user not found.", "danger")
        return redirect(url_for("requests"))

    if staff.role.lower() != req.category.lower():
        flash(f"Cannot assign: user is {staff.role}, request requires {req.category}", "danger")
        return redirect(url_for("requests"))

    old_staff_id = req.staff_id
    req.staff_id = staff.id
    req.status = "Assigned"

    student = User.query.get(req.user_id)
    if student:
        create_notification(
            student.id,
            f"Your request #{req.id} ({req.room_number}) assigned to {staff.full_name} ({staff.role}).",
            'assignment', req.id
        )

    create_notification(
        staff.id,
        f"Assigned request #{req.id} – {req.room_number} – {req.category} – Priority: {req.priority}",
        'assignment', req.id
    )

    db.session.commit()

    action = "Re-assigned" if old_staff_id else "Assigned"
    flash(f"{action} to {staff.full_name} ({staff.role})", "success")
    return redirect(url_for("requests"))

# ────────────────────────────────────────────────
# FIXED: Status update – supports all staff roles
# ────────────────────────────────────────────────
@app.route("/update_status/<int:req_id>", methods=["POST"])
@login_required
def update_status(req_id):
    allowed_roles = {'technician', 'plumber', 'cleaner', 'electrician', 'pest_controller'}
    if current_user.role.lower() not in allowed_roles:
        flash("Only maintenance staff can update status", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(req_id)

    if req.staff_id != current_user.id:
        flash("This task is not assigned to you", "danger")
        return redirect(url_for("dashboard"))

    new_status = request.form.get("status")
    allowed = {"Assigned", "In Progress", "Completed"}

    if new_status in allowed:
        if req.status == "Completed" and new_status != "Completed":
            flash("Completed tasks cannot be changed back", "warning")
        else:
            req.status = new_status
            db.session.commit()
            flash(f"Status updated to {new_status}", "success")
    else:
        flash("Invalid status", "danger")

    return redirect(url_for("staff_assigned_work"))

# ────────────────────────────────────────────────
# The rest of your application (unchanged routes)
# ────────────────────────────────────────────────

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
            if file and file.filename and allowed_file(file.filename):
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

    paginated_requests = Request.query.order_by(Request.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    staff_by_category = {}
    staff_roles = ['plumber', 'cleaner', 'electrician', 'technician', 'pest_controller']
    for role in staff_roles:
        staff_by_category[role] = User.query.filter_by(role=role).all()

    for req in paginated_requests.items:
        student = User.query.get(req.user_id)
        req.student_name = student.full_name if student else "Unknown Student"
        req.student_room = student.room_number if student else "Unknown"

        if req.staff_id:
            staff = User.query.get(req.staff_id)
            req.staff_name = staff.full_name if staff else "Unknown"
        else:
            req.staff_name = "Not assigned"

    return render_template("admin/requests.html",
                          requests=paginated_requests,
                          staff_by_category=staff_by_category,
                          User=User)

@app.route("/users")
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    users = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    return render_template("admin/users.html", users=users)

@app.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Cannot edit your own account here.", "warning")
        return redirect(url_for('users'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        role = request.form.get('role', '').strip().lower()
        room_number = request.form.get('room_number', '').strip()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not full_name or not role:
            flash("Full name and role required.", "danger")
            return redirect(url_for('edit_user', user_id=user_id))

        if role == 'student' and not room_number:
            flash("Room number required for students.", "danger")
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
        flash(f"User {user.full_name} updated.", "success")
        return redirect(url_for('users'))

    return render_template('admin/edit_user.html', user=user)

@app.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Cannot delete your own account.", "danger")
        return redirect(url_for('users'))

    if user.role == 'admin' and User.query.filter_by(role='admin').count() <= 1:
        flash("Cannot delete the last admin.", "danger")
        return redirect(url_for('users'))

    db.session.delete(user)
    db.session.commit()
    flash(f"User {user.full_name} deleted.", "success")
    return redirect(url_for('users'))

@app.route("/staff/assigned-work")
@login_required
def staff_assigned_work():
    if current_user.role in ['admin', 'student']:
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

@app.route('/requests/<int:request_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_request(request_id):
    if current_user.role != "student":
        flash("Only students can edit requests.", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(request_id)
    if req.user_id != current_user.id:
        flash("You can only edit your own requests.", "danger")
        return redirect(url_for("my_requests"))

    if req.status in ["Assigned", "In Progress", "Completed"]:
        flash("Cannot edit assigned/in-progress/completed requests.", "warning")
        return redirect(url_for("my_requests"))

    if request.method == "POST":
        room_number = request.form.get("room_number", "").strip()
        category = request.form.get("category", "").strip()
        priority = request.form.get("priority", "").strip()
        description = request.form.get("description", "").strip()

        if not all([room_number, category, priority, description]):
            flash("All fields required.", "danger")
            return redirect(url_for("edit_request", request_id=request_id))

        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename and allowed_file(file.filename):
                if req.photo_path:
                    old_path = os.path.join('static', req.photo_path)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                req.photo_path = f"uploads/{filename}"

        req.room_number = room_number
        req.category = category
        req.priority = priority
        req.description = description

        try:
            db.session.commit()
            flash("Request updated.", "success")
            return redirect(url_for("my_requests"))
        except Exception as e:
            db.session.rollback()
            flash(f"Update failed: {str(e)}", "danger")

    return render_template("student/edit_request.html", request=req)

@app.route('/requests/<int:request_id>/delete', methods=['POST'])
@login_required
def delete_request(request_id):
    if current_user.role != "student":
        flash("Only students can delete requests.", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(request_id)
    if req.user_id != current_user.id:
        flash("Can only delete own requests.", "danger")
        return redirect(url_for("my_requests"))

    if req.status in ["Assigned", "In Progress", "Completed"]:
        flash("Cannot delete assigned/in-progress/completed requests.", "warning")
        return redirect(url_for("my_requests"))

    if req.photo_path:
        photo_file = os.path.join('static', req.photo_path)
        if os.path.exists(photo_file):
            os.remove(photo_file)

    try:
        db.session.delete(req)
        db.session.commit()
        flash("Request deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Delete failed: {str(e)}", "danger")

    return redirect(url_for("my_requests"))

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    form = AddUserForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash('Email already registered.', 'danger')
            return render_template('admin/add_user.html', form=form)

        if form.role.data == 'student' and not form.room_number.data:
            flash('Room number required for students.', 'danger')
            return render_template('admin/add_user.html', form=form)

        user = User(
            full_name=form.full_name.data.strip(),
            email=form.email.data.lower().strip(),
            password_hash=generate_password_hash(form.password.data),
            role=form.role.data,
            room_number=form.room_number.data if form.role.data == 'student' else None
        )
        db.session.add(user)
        db.session.commit()
        flash('User created successfully!', 'success')
        return redirect(url_for('users'))

    return render_template('admin/add_user.html', form=form)

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
    flash("Email notification sent")
    return redirect(url_for("dashboard"))

@app.route('/view-photo/<int:request_id>')
@login_required
def view_photo(request_id):
    req = Request.query.get_or_404(request_id)
    if current_user.role == 'student' and req.user_id != current_user.id:
        flash("Access denied", "danger")
        return redirect(url_for('dashboard'))

    if current_user.role not in ['admin', 'student'] and req.staff_id != current_user.id:
        flash("Access denied", "danger")
        return redirect(url_for('dashboard'))

    if not req.photo_path:
        flash("No photo available", "warning")
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
# ================= PASSWORD RESET ROUTES =================

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Please enter your email address.', 'warning')
            return render_template('forgot_password.html')

        user = User.query.filter_by(email=email).first()
        
        if not user:
            # Still show success message for security (don't reveal if email exists)
            flash('If an account with that email exists, you will receive a password reset link.', 'info')
            return redirect(url_for('login'))

        token = generate_reset_token(user.email)
        reset_url = url_for('reset_password', token=token, _external=True)

        success = send_reset_email(user.email, reset_url, user.full_name)
        
        if success:
            flash('Password reset instructions have been sent to your email.', 'success')
        else:
            flash('Failed to send reset email. Please try again later or contact support.', 'danger')

        return redirect(url_for('login'))

    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    email = verify_reset_token(token)
    
    if not email:
        flash('Invalid or expired reset link. Please request a new one.', 'danger')
        return redirect(url_for('forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Invalid reset link.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not password or not confirm_password:
            flash('Please fill in both password fields.', 'warning')
            return render_template('reset_password.html', token=token)

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'warning')
            return render_template('reset_password.html', token=token)

        user.password_hash = generate_password_hash(password)
        db.session.commit()

        flash('Your password has been updated successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)
# ────────────────────────────────────────────────
# Run application
# ────────────────────────────────────────────────
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

        for name, email, pw, role, room in default_users:
            if not User.query.filter_by(email=email).first():
                user = User(
                    full_name=name,
                    email=email,
                    password_hash=generate_password_hash(pw),
                    role=role,
                    room_number=room
                )
                db.session.add(user)

        db.session.commit()
        app.run(debug=True)