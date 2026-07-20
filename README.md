📌 Project Overview

Managing maintenance requests in student residences can be challenging when using paper forms or manual communication. This application digitizes the entire maintenance workflow by allowing residents to submit maintenance requests online while enabling maintenance teams to manage, assign, update, and resolve issues efficiently.

The system improves communication, reduces response times, and provides administrators with real-time reporting and analytics.


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


 👷 Maintenance Staff Portal

- Staff Login
- View Assigned Requests
- Accept Jobs
- Update Repair Progress
- Upload Repair Images
- Mark Requests as Completed
- View Work History


👨‍💼 Administrator Portal

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


📊 Analytics Dashboard

- Total Maintenance Requests
- Pending Requests
- In Progress Requests
- Completed Requests
- High Priority Requests
- Monthly Reports
- Maintenance Performance Metrics



🔔 Notification System

- Email Notifications
- Status Change Notifications
- Assignment Notifications
- Completion Notifications
- Password Reset Emails

📁 Image Upload

Supports image uploads for:

- Broken Furniture
- Plumbing Issues
- Electrical Problems
- Building Damage
- Other Maintenance Issues

Images are stored securely using:

- ImgBB
- Local Storage (optional)


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


📂 Project Structure

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

🔐 User Roles

| Role | Permissions |
|------|-------------|
| Student | Submit maintenance requests |
| Staff | Resolve assigned requests |
| Admin | Full system management |
| Manager | Reports & Analytics |


 🔒 Security Features

- Password Hashing
- Secure Authentication
- Role-Based Access Control (RBAC)
- Session Management
- CSRF Protection
- Input Validation
- SQL Injection Protection
- XSS Protection
- Secure Password Reset


📈 Future Improvements

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


📦 Deployment

The application can be deployed on:

- Render


⭐ Project Highlights

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

🌟 Why This Project?

The Residence Management System was developed to modernize maintenance operations within student accommodations by replacing manual processes with a secure, centralized web application. It demonstrates practical software engineering principles, including authentication, database design, CRUD operations, role-based authorization, file uploads, email integration, and responsive UI development.

This project serves as a strong portfolio piece showcasing full-stack development skills using Python and Flask.
