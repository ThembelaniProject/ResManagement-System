from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from datetime import datetime, timedelta, timezone
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
import os
from werkzeug.utils import secure_filename

# ────────────────────────────────────────────────
# CONFIGURATION
# ────────────────────────────────────────────────

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///maintenance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload config
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Email config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'thembelanibuthelezi64@gmail.com'
app.config['MAIL_PASSWORD'] = 'iuuocjnhsocusnrz'

db = SQLAlchemy(app)
mail = Mail(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

scheduler = BackgroundScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ────────────────────────────────────────────────
# MODELS
# ────────────────────────────────────────────────

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(200))
    role = db.Column(db.String(30))  # admin, student, plumber, cleaner, electrician, technician, pest_controller
    room_number = db.Column(db.String(20), nullable=True)  # Only for students
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic', cascade="all, delete-orphan"))
    request = db.relationship('Request', backref='notifications', lazy=True)

# ────────────────────────────────────────────────
# DECORATORS
# ────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in.", "warning")
            return redirect(url_for('login'))
        if current_user.role != 'admin':
            flash("Admin access only.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in.", "warning")
            return redirect(url_for('login'))
        if current_user.role == 'admin' or current_user.role == 'student':
            flash("Staff access only.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ────────────────────────────────────────────────
# HELPER FUNCTIONS
# ────────────────────────────────────────────────

def create_notification(user_id, message, notif_type='request', related_request_id=None):
    notif = Notification(
        user_id=user_id,
        message=message,
        type=notif_type,
        related_request_id=related_request_id
    )
    db.session.add(notif)


def check_and_create_reminder_notifications():
    try:
        with app.app_context():
            overdue = Request.query.filter(
                Request.status == "Pending",
                Request.created_at <= datetime.now(timezone.utc) - timedelta(hours=48)
            ).all()

            for req in overdue:
                student = User.query.get(req.user_id)
                if not student:
                    continue

                recent_reminder = Notification.query.filter(
                    Notification.user_id == student.id,
                    Notification.type == 'reminder',
                    Notification.related_request_id == req.id,
                    Notification.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)
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
    except Exception as e:
        print(f"Reminder check failed: {e}")


# Schedule reminders (every 15 minutes - changed from 1 for production)
scheduler.add_job(
    func=check_and_create_reminder_notifications,
    trigger=IntervalTrigger(minutes=15),
    id='maintenance_reminders',
    replace_existing=True
)

# ────────────────────────────────────────────────
# LOGIN / LOGOUT
# ────────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and check_password_hash(user.password_hash, request.form["password"]):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ────────────────────────────────────────────────
# DASHBOARD
# ────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    notifications = current_user.get_notifications(limit=12)
    unread_count = current_user.unread_notifications_count()

    if current_user.role == "admin":
        total_requests = Request.query.count()
        pending = Request.query.filter_by(status="Pending").count()
        in_progress = Request.query.filter_by(status="In Progress").count()
        completed = Request.query.filter_by(status="Completed").count()
        recent_requests = Request.query.order_by(Request.created_at.desc()).limit(10).all()

        categories = {}
        for cat in ['plumber', 'cleaner', 'electrician', 'technician', 'pest_controller']:
            categories[cat] = Request.query.filter_by(category=cat).count()

        return render_template("admin/dashboard.html",
                               total_requests=total_requests,
                               pending=pending,
                               in_progress=in_progress,
                               completed=completed,
                               recent_requests=recent_requests,
                               categories=categories,
                               notifications=notifications,
                               unread_count=unread_count)

    elif current_user.role == "student":
        requests = Request.query.filter_by(user_id=current_user.id).order_by(Request.created_at.desc()).all()
        pending = Request.query.filter_by(user_id=current_user.id, status="Pending").count()
        in_progress = Request.query.filter_by(user_id=current_user.id, status="In Progress").count()
        completed = Request.query.filter_by(user_id=current_user.id, status="Completed").count()

        return render_template("student/dashboard.html",
                               requests=requests,
                               pending=pending,
                               in_progress=in_progress,
                               completed=completed,
                               notifications=notifications,
                               unread_count=unread_count)

    elif current_user.role in ['plumber', 'cleaner', 'electrician', 'technician', 'pest_controller']:
        requests = Request.query.filter_by(staff_id=current_user.id).order_by(Request.created_at.desc()).all()
        pending = Request.query.filter_by(staff_id=current_user.id, status="Pending").count()
        in_progress = Request.query.filter_by(staff_id=current_user.id, status="In Progress").count()
        completed = Request.query.filter_by(staff_id=current_user.id, status="Completed").count()

        return render_template("staff/dashboard.html",
                               requests=requests,
                               pending=pending,
                               in_progress=in_progress,
                               completed=completed,
                               role_display=current_user.role.replace('_', ' ').title(),
                               notifications=notifications,
                               unread_count=unread_count)

    flash("Unknown role", "danger")
    return redirect(url_for("login"))

# ────────────────────────────────────────────────
# OTHER ROUTES (only key ones shown – add your remaining routes here)
# ────────────────────────────────────────────────

# New request with photo upload
@app.route('/new_request', methods=['GET', 'POST'])
@login_required
def new_request():
    if current_user.role != "student":
        flash("Only students can submit requests.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == 'POST':
        room_number = request.form.get('room_number') or current_user.room_number
        category = request.form.get('category')
        priority = request.form.get('priority')
        description = request.form.get('description')

        photo_path = None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                photo_path = f"uploads/{filename}"

        if not all([room_number, category, priority, description]):
            flash("All fields are required", "danger")
            return redirect(url_for('new_request'))

        new_req = Request(
            user_id=current_user.id,
            room_number=room_number.strip(),
            category=category,
            priority=priority,
            description=description.strip(),
            photo_path=photo_path
        )
        db.session.add(new_req)
        db.session.commit()
        flash("Request submitted successfully!", "success")
        return redirect(url_for('my_requests'))

    return render_template('student/new_request.html', default_room=current_user.room_number)

# Serve uploaded files
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ────────────────────────────────────────────────
# RUN APP + SEED DATA
# ────────────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        default_users = [
            ("Admin", "admin@gmail.com", "admin123", "admin", None),
            ("Student", "student@gmail.com", "student123", "student", "101A"),
            ("Plumber", "plumber@gmail.com", "plumber123", "plumber", None),
            ("Cleaner", "cleaner@gmail.com", "cleaner123", "cleaner", None),
            ("Electrician", "electrician@gmail.com", "electrician123", "electrician", None),
            ("Technician", "tech@gmail.com", "tech123", "technician", None),
            ("Pest Controller", "pest@gmail.com", "pest123", "pest_controller", None),
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