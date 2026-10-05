import os
import json
from datetime import datetime
from functools import wraps
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.security import check_password_hash, generate_password_hash


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "dev-only-change-this-secret-key"
)


# ============================================================
# FIREBASE / FIRESTORE SETUP
# ============================================================

FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON")

if not firebase_admin._apps:

    if FIREBASE_CREDENTIALS_JSON:
        # Render: Firebase credentials are stored
        # securely in an environment variable.
        firebase_credential = credentials.Certificate(
            json.loads(FIREBASE_CREDENTIALS_JSON)
        )

    else:
        # Local computer:
        # Use your Firebase service-account JSON file.
        FIREBASE_KEY_FILE = os.environ.get(
            "GOOGLE_APPLICATION_CREDENTIALS",
            "college-complaint-box-1bc7b-firebase-adminsdk-fbsvc-f5fe6ca889.json"
        )

        firebase_credential = credentials.Certificate(
            FIREBASE_KEY_FILE
        )

    firebase_admin.initialize_app(firebase_credential)


db = firestore.client()


# ============================================================
# ADMIN SETTINGS
# ============================================================

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "admin123"
)


# ============================================================
# FIRESTORE COLLECTIONS
# ============================================================

STUDENTS_COLLECTION = "students"
COMPLAINTS_COLLECTION = "complaints"


# ============================================================
# ID GENERATOR
# ============================================================

def get_next_id(collection_name, id_field):
    """
    Generates the next integer ID.

    We keep integer IDs because the existing HTML pages
    display complaints as CMP0001, CMP0002, etc.
    """

    documents = (
        db.collection(collection_name)
        .order_by(
            id_field,
            direction=firestore.Query.DESCENDING
        )
        .limit(1)
        .stream()
    )

    highest_id = 0

    for document in documents:
        data = document.to_dict()
        highest_id = data.get(id_field, 0)
        break

    return highest_id + 1


# ============================================================
# LOGIN DECORATORS
# ============================================================

def student_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "student_id" not in session:
            flash("Please login first.")
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("admin"):
            flash("Admin login required.")
            return redirect(url_for("admin_login"))

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():
    return {"status": "ok"}, 200


# ============================================================
# STUDENT REGISTRATION
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()
        roll_no = request.form["roll_no"].strip()
        department = request.form["department"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not all([
            name,
            roll_no,
            department,
            email,
            password
        ]):
            flash("All fields are required.")
            return redirect(url_for("register"))

        # Check whether roll number already exists
        roll_query = (
            db.collection(STUDENTS_COLLECTION)
            .where("roll_no", "==", roll_no)
            .limit(1)
            .stream()
        )

        if any(True for _ in roll_query):
            flash("Roll number already exists.")
            return redirect(url_for("register"))

        # Check whether email already exists
        email_query = (
            db.collection(STUDENTS_COLLECTION)
            .where("email", "==", email)
            .limit(1)
            .stream()
        )

        if any(True for _ in email_query):
            flash("Email already exists.")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        student_id = get_next_id(
            STUDENTS_COLLECTION,
            "student_id"
        )

        student_data = {
            "student_id": student_id,
            "name": name,
            "roll_no": roll_no,
            "department": department,
            "email": email,
            "password": hashed_password,
            "created_at": datetime.now().isoformat()
        }

        # Use student_id as Firestore document ID
        (
            db.collection(STUDENTS_COLLECTION)
            .document(str(student_id))
            .set(student_data)
        )

        flash("Registration successful. Please login.")
        return redirect(url_for("login"))

    return render_template("register.html")


# ============================================================
# STUDENT LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        student_query = (
            db.collection(STUDENTS_COLLECTION)
            .where("email", "==", email)
            .limit(1)
            .stream()
        )

        student = None

        for document in student_query:
            student = document.to_dict()
            break

        if student and check_password_hash(
            student["password"],
            password
        ):

            session["student_id"] = student["student_id"]
            session["student_name"] = student["name"]

            return redirect(url_for("student_dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route("/student/dashboard")
@student_required
def student_dashboard():

    student_id = session["student_id"]

    complaint_documents = (
        db.collection(COMPLAINTS_COLLECTION)
        .where("student_id", "==", student_id)
        .stream()
    )

    complaints = []

    for document in complaint_documents:

        complaint = document.to_dict()
        complaints.append(complaint)

    # Newest complaint first
    complaints.sort(
        key=lambda x: x.get("complaint_id", 0),
        reverse=True
    )

    total = len(complaints)

    pending = sum(
        c.get("status") == "Pending"
        for c in complaints
    )

    progress = sum(
        c.get("status") == "In Progress"
        for c in complaints
    )

    resolved = sum(
        c.get("status") == "Resolved"
        for c in complaints
    )

    return render_template(
        "student_dashboard.html",
        complaints=complaints,
        total=total,
        pending=pending,
        progress=progress,
        resolved=resolved
    )


# ============================================================
# SUBMIT COMPLAINT
# ============================================================

@app.route("/complaint", methods=["GET", "POST"])
@student_required
def complaint():

    if request.method == "POST":

        title = request.form["title"].strip()
        category = request.form["category"].strip()
        description = request.form["description"].strip()
        location = request.form["location"].strip()

        if not all([
            title,
            category,
            description,
            location
        ]):
            flash("All complaint fields are required.")
            return redirect(url_for("complaint"))

        # Priority calculation
        if (
            category == "Internet/Wi-Fi"
            and "entire" in location.lower()
        ):
            priority = "HIGH"

        elif category in [
            "Computer",
            "Electrical",
            "Equipment"
        ]:
            priority = "MEDIUM"

        else:
            priority = "LOW"

        date = datetime.now().strftime(
            "%d-%m-%Y %H:%M"
        )

        complaint_id = get_next_id(
            COMPLAINTS_COLLECTION,
            "complaint_id"
        )

        complaint_data = {
            "complaint_id": complaint_id,
            "student_id": session["student_id"],
            "title": title,
            "category": category,
            "description": description,
            "location": location,
            "date": date,
            "priority": priority,
            "status": "Pending",
            "admin_response": "",
            "created_at": datetime.now().isoformat()
        }

        (
            db.collection(COMPLAINTS_COLLECTION)
            .document(str(complaint_id))
            .set(complaint_data)
        )

        flash("Complaint submitted successfully.")

        return redirect(
            url_for("my_complaints")
        )

    return render_template("complaint.html")


# ============================================================
# MY COMPLAINTS
# ============================================================

@app.route("/my-complaints")
@student_required
def my_complaints():

    student_id = session["student_id"]

    complaint_documents = (
        db.collection(COMPLAINTS_COLLECTION)
        .where("student_id", "==", student_id)
        .stream()
    )

    complaints = []

    for document in complaint_documents:

        complaint = document.to_dict()
        complaints.append(complaint)

    complaints.sort(
        key=lambda x: x.get("complaint_id", 0),
        reverse=True
    )

    return render_template(
        "my_complaints.html",
        complaints=complaints
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):

            session["admin"] = True

            return redirect(
                url_for("admin_dashboard")
            )

        flash("Invalid admin username or password.")

    return render_template("admin_login.html")


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():

    search = request.args.get(
        "search",
        ""
    ).strip().lower()

    status_filter = request.args.get(
        "status",
        ""
    ).strip()

    # Get all complaints
    complaint_documents = (
        db.collection(COMPLAINTS_COLLECTION)
        .stream()
    )

    complaints = []

    for document in complaint_documents:

        complaint = document.to_dict()

        # Get associated student
        student_id = complaint.get("student_id")

        student_document = (
            db.collection(STUDENTS_COLLECTION)
            .document(str(student_id))
            .get()
        )

        if student_document.exists:

            student = student_document.to_dict()

            complaint["name"] = student.get(
                "name",
                ""
            )

            complaint["roll_no"] = student.get(
                "roll_no",
                ""
            )

            complaint["department"] = student.get(
                "department",
                ""
            )

            complaint["email"] = student.get(
                "email",
                ""
            )

        else:

            complaint["name"] = ""
            complaint["roll_no"] = ""
            complaint["department"] = ""
            complaint["email"] = ""

        complaints.append(complaint)

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    if search:

        filtered_complaints = []

        for complaint in complaints:

            searchable_text = " ".join([
                str(complaint.get("title", "")),
                str(complaint.get("category", "")),
                str(complaint.get("name", "")),
                str(complaint.get("roll_no", "")),
            ]).lower()

            if search in searchable_text:
                filtered_complaints.append(
                    complaint
                )

        complaints = filtered_complaints

    # --------------------------------------------------------
    # STATUS FILTER
    # --------------------------------------------------------

    if status_filter:

        complaints = [
            complaint
            for complaint in complaints
            if complaint.get("status")
            == status_filter
        ]

    # Newest first
    complaints.sort(
        key=lambda x: x.get("complaint_id", 0),
        reverse=True
    )

    # --------------------------------------------------------
    # DASHBOARD COUNTS
    # --------------------------------------------------------

    all_complaint_documents = (
        db.collection(COMPLAINTS_COLLECTION)
        .stream()
    )

    all_complaints = [
        document.to_dict()
        for document in all_complaint_documents
    ]

    total = len(all_complaints)

    pending = sum(
        c.get("status") == "Pending"
        for c in all_complaints
    )

    progress = sum(
        c.get("status") == "In Progress"
        for c in all_complaints
    )

    resolved = sum(
        c.get("status") == "Resolved"
        for c in all_complaints
    )

    return render_template(
        "admin_dashboard.html",
        complaints=complaints,
        total=total,
        pending=pending,
        progress=progress,
        resolved=resolved,
        search=search,
        status_filter=status_filter
    )


# ============================================================
# ADMIN UPDATE COMPLAINT
# ============================================================

@app.route(
    "/admin/update/<int:complaint_id>",
    methods=["POST"]
)
@admin_required
def update_complaint(complaint_id):

    status = request.form["status"]

    response = request.form[
        "admin_response"
    ]

    complaint_reference = (
        db.collection(COMPLAINTS_COLLECTION)
        .document(str(complaint_id))
    )

    complaint_document = complaint_reference.get()

    if not complaint_document.exists:

        flash("Complaint not found.")

        return redirect(
            url_for("admin_dashboard")
        )

    complaint_reference.update({
        "status": status,
        "admin_response": response,
        "updated_at": datetime.now().isoformat()
    })

    flash("Complaint updated successfully.")

    return redirect(
        url_for("admin_dashboard")
    )


# ============================================================
# ADMIN DELETE COMPLAINT
# ============================================================

@app.route(
    "/admin/delete/<int:complaint_id>",
    methods=["POST"]
)
@admin_required
def delete_complaint(complaint_id):

    complaint_reference = (
        db.collection(COMPLAINTS_COLLECTION)
        .document(str(complaint_id))
    )

    complaint_document = complaint_reference.get()

    if complaint_document.exists:

        complaint_reference.delete()

        flash("Complaint deleted.")

    else:

        flash("Complaint not found.")

    return redirect(
        url_for("admin_dashboard")
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash("Logged out successfully.")

    return redirect(
        url_for("index")
    )


# ============================================================
# RUN APP
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True,
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )
    )