````markdown
# 🏠 Residence Management System

A modern, secure, and user-friendly **Residence Maintenance Management System** built with **Python**, **Flask**, **SQLite**, **Bootstrap**, and **SQLAlchemy**. The system streamlines the process of reporting, tracking, and resolving maintenance issues within student residences while providing role-based access for students, maintenance staff, administrators, and managers.

---

## 📌 Project Overview

Managing maintenance requests in student residences can be challenging when using paper forms or manual communication. This application digitizes the entire maintenance workflow by allowing residents to submit maintenance requests online while enabling maintenance teams to manage, assign, update, and resolve issues efficiently.

The system improves communication, reduces response times, and provides administrators with real-time reporting and analytics.

---

# 🚀 Features

## 👨‍🎓 Student Portal

- Student Registration & Login
- Secure Authentication
- Dashboard
- Submit Maintenance Requests
- Upload Images of Maintenance Issues
- View Request History
- Track Request Status
- Receive Email Notifications
- Edit User Profile
- Password Reset

---

## 👷 Maintenance Staff Portal

- Staff Login
- View Assigned Requests
- Accept Jobs
- Update Repair Progress
- Upload Repair Images
- Mark Requests as Completed
- View Work History

---

## 👨‍💼 Administrator Portal

- Admin Dashboard
- Manage Students
- Manage Maintenance Staff
- Manage Residences
- Manage Buildings
- Manage Rooms
- Assign Maintenance Requests
- Update Request Status
- View Reports
- View System Statistics
- Manage User Accounts

---

## 📊 Analytics Dashboard

- Total Maintenance Requests
- Pending Requests
- In Progress Requests
- Completed Requests
- High Priority Requests
- Monthly Reports
- Maintenance Performance Metrics

---

## 🔔 Notification System

- Email Notifications
- Status Change Notifications
- Assignment Notifications
- Completion Notifications
- Password Reset Emails

---

## 📁 Image Upload

Supports image uploads for:

- Broken Furniture
- Plumbing Issues
- Electrical Problems
- Building Damage
- Other Maintenance Issues

Images are stored securely using:

- ImgBB
- Local Storage (optional)

---

# 🛠 Technology Stack

| Technology | Purpose |
|------------|---------|
| Python | Backend |
| Flask | Web Framework |
| SQLite | Database |
| SQLAlchemy | ORM |
| Flask-Login | Authentication |
| Bootstrap 5 | Frontend |
| HTML5 | Markup |
| CSS3 | Styling |
| JavaScript | Client-side Logic |
| Jinja2 | Templating |
| Flask-Mail | Email Service |
| Brevo SMTP | Email Notifications |
| ImgBB API | Image Hosting |

---

# 📂 Project Structure

```
ResidenceManagement/
│
├── app.py
├── config.py
├── requirements.txt
├── README.md
├── instance/
│   └── maintenance.db
│
├── static/
│   ├── css/
│   ├── js/
│   ├── images/
│   └── uploads/
│
├── templates/
│   ├── admin/
│   ├── staff/
│   ├── student/
│   └── auth/
│
├── models/
├── routes/
├── services/
├── utils/
└── migrations/
```

---

# ⚙ Installation

## 1. Clone Repository

```bash
git clone https://github.com/yourusername/residence-management-system.git
```

```bash
cd residence-management-system
```

---

## 2. Create Virtual Environment

Windows

```bash
python -m venv venv
```

Activate

```bash
venv\Scripts\activate
```

Linux / macOS

```bash
python3 -m venv venv
```

```bash
source venv/bin/activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Configure Environment Variables

Create a `.env` file.

Example:

```env
SECRET_KEY=your_secret_key

MAIL_SERVER=smtp-relay.brevo.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your_email@example.com
MAIL_PASSWORD=your_password

IMGBB_API_KEY=your_imgbb_api_key
```

---

## 5. Initialize Database

```bash
python app.py
```

The database will be created automatically if it does not exist.

---

## 6. Run the Application

```bash
python app.py
```

Open your browser:

```
http://127.0.0.1:5000
```

---

# 🔐 User Roles

| Role | Permissions |
|------|-------------|
| Student | Submit maintenance requests |
| Staff | Resolve assigned requests |
| Admin | Full system management |
| Manager | Reports & Analytics |

---

# 📋 Maintenance Workflow

```
Student

      │

      ▼

Submit Request

      │

      ▼

Admin Reviews

      │

      ▼

Assign Staff

      │

      ▼

Staff Repairs Issue

      │

      ▼

Update Status

      │

      ▼

Completed

      │

      ▼

Student Receives Notification
```

---

# 📸 Screenshots

Add screenshots here.

Example:

```
screenshots/

login.png

dashboard.png

admin-dashboard.png

maintenance-request.png

reports.png
```

---

# 🔒 Security Features

- Password Hashing
- Secure Authentication
- Role-Based Access Control (RBAC)
- Session Management
- CSRF Protection
- Input Validation
- SQL Injection Protection
- XSS Protection
- Secure Password Reset

---

# 📈 Future Improvements

- Mobile Application
- QR Code Room Reporting
- AI-powered Issue Classification
- Predictive Maintenance
- SMS Notifications
- Push Notifications
- PDF Report Generation
- Cloud Database Support
- REST API
- Docker Deployment
- Multi-Residence Support

---

# 🧪 Testing

Run tests using:

```bash
pytest
```

---

# 📦 Deployment

The application can be deployed on:

- Render
- Railway
- PythonAnywhere
- DigitalOcean
- Azure App Service
- AWS Elastic Beanstalk

---

# 🤝 Contributing

Contributions are welcome.

1. Fork the repository
2. Create a feature branch

```bash
git checkout -b feature/new-feature
```

3. Commit your changes

```bash
git commit -m "Added new feature"
```

4. Push your branch

```bash
git push origin feature/new-feature
```

5. Open a Pull Request

---

# 📄 License

This project is licensed under the MIT License.

---

# 👨‍💻 Developer

**Thembelani Sikhona Buthelezi**

Full Stack Software Developer

- Python
- Flask
- ASP.NET
- SQL Server
- SQLite
- JavaScript
- Bootstrap
- AI Applications
- Machine Learning

📧 Email: your-email@example.com

🌍 South Africa

---

# ⭐ Project Highlights

✅ Role-Based Authentication

✅ Maintenance Ticket Management

✅ Email Notifications

✅ Image Upload Support

✅ Admin Dashboard

✅ Analytics Dashboard

✅ Secure Login System

✅ Responsive UI

✅ Database Integration

✅ Clean Flask Architecture

---

# 📊 System Architecture

```
                +----------------------+
                |      Web Browser     |
                +----------+-----------+
                           |
                           |
                    HTTP Requests
                           |
                           ▼
                +----------------------+
                |     Flask Server     |
                +----------+-----------+
                           |
        +------------------+------------------+
        |                  |                  |
        ▼                  ▼                  ▼
 Authentication     Business Logic      Email Service
        |                  |                  |
        +------------------+------------------+
                           |
                           ▼
                  SQLAlchemy ORM
                           |
                           ▼
                    SQLite Database
                           |
                           ▼
                   Maintenance Records
```

---

# 🌟 Why This Project?

The Residence Management System was developed to modernize maintenance operations within student accommodations by replacing manual processes with a secure, centralized web application. It demonstrates practical software engineering principles, including authentication, database design, CRUD operations, role-based authorization, file uploads, email integration, and responsive UI development.

This project serves as a strong portfolio piece showcasing full-stack development skills using Python and Flask.

---

## ⭐ If you found this project useful, consider giving it a star!
```
````
