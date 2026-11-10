import os
from datetime import datetime
import secrets
import re

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    session
)

from flask_sqlalchemy import SQLAlchemy
app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "RELIEFNET_SECRET_KEY",
    "reliefnet-local-demo-secret-change-before-deployment"
)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///reliefnet.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["DEMO_USERNAME"] = "admin"
app.config["DEMO_PASSWORD"] = os.environ.get(
    "RELIEFNET_DEMO_PASSWORD",
    "ReliefNetDemo@2026"
)

db = SQLAlchemy(app)

PUBLIC_ENDPOINTS = {
    "landing",
    "login",
    "public_relief",
    "volunteer_apply",
    "application_status",
    "static"
}


@app.before_request
def protect_admin_pages():
    if request.endpoint is None:
        return

    if request.endpoint in PUBLIC_ENDPOINTS:
        return

    if not session.get("admin_logged_in"):
        flash("Please log in to access the administration platform.", "error")
        return redirect(url_for("login"))


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin_logged_in"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if (
            username == app.config["DEMO_USERNAME"]
            and secrets.compare_digest(
                password, app.config["DEMO_PASSWORD"]
            )
        ):
            session.clear()
            session["admin_logged_in"] = True
            session.permanent = True
            flash("Welcome to ReliefNet AI Command Platform.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("landing"))







# =========================================================
# APPLICATION CONFIGURATION
# =========================================================



# =========================================================
# DATABASE MODELS
# =========================================================

class ReliefRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(40), default="")
    need = db.Column(db.String(40), nullable=False)
    details = db.Column(db.String(500), default="")
    location = db.Column(db.String(150), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    people = db.Column(db.Integer, default=1)
    status = db.Column(db.String(30), default="Pending")
    priority = db.Column(db.String(20), default="Medium")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    flood_simulation_id = db.Column(
        db.Integer,
        db.ForeignKey("flood_simulation.id"),
        nullable=True
    )


class Volunteer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    skill = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(150), default="Multan")
    phone = db.Column(db.String(40), default="")
    status = db.Column(db.String(30), default="Available")

    assigned_request_id = db.Column(
        db.Integer,
        db.ForeignKey("relief_request.id"),
        nullable=True
    )


class VolunteerApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    skills = db.Column(db.String(250), nullable=False)
    availability = db.Column(db.String(100), default="Flexible")
    experience = db.Column(db.String(500), default="")

    status = db.Column(db.String(40), default="Pending")

    rejection_reason = db.Column(db.String(250), default="")
    reviewer_comments = db.Column(db.String(1000), default="")
    applicant_message = db.Column(db.String(1000), default="")
    reviewed_at = db.Column(db.DateTime, nullable=True)

    tracking_token = db.Column(
        db.String(64),
        unique=True,
        nullable=True,
        default=lambda: secrets.token_urlsafe(32)
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    location = db.Column(db.String(150), default="Multan")
    status = db.Column(db.String(30), default="Available")


class FloodSimulation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    severity = db.Column(db.String(30), default="Medium")
    affected_people = db.Column(db.Integer, default=0)
    status = db.Column(db.String(30), default="Active")
    generated_request_ids = db.Column(db.Text, default="[]")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================================================
# PHONE NORMALIZATION AND VOLUNTEER SYNCHRONIZATION
# =========================================================

def normalize_phone(phone):
    """
    Remove spaces, brackets, hyphens and other
    non-numeric characters from a phone number.

    This helps recognize common formatting differences.
    """

    return re.sub(r"\D", "", phone or "")


def sync_approved_application(application):
    """
    Ensure an approved application has a corresponding
    Volunteer record.

    Existing volunteer assignments and availability
    are preserved.
    """

    if application.status != "Approved":
        return None

    application_phone = normalize_phone(application.phone)

    if not application_phone:
        raise ValueError(
            "The approved application has no valid phone number."
        )

    # Find an existing volunteer with the same normalized phone.
    existing_volunteers = Volunteer.query.order_by(
        Volunteer.id.asc()
    ).all()

    volunteer = next(
        (
            item for item in existing_volunteers
            if normalize_phone(item.phone) == application_phone
        ),
        None
    )

    if volunteer is None:

        volunteer = Volunteer(
            name=application.name,
            skill=application.skills,
            location=application.location,
            phone=application.phone,
            status="Available"
        )

        db.session.add(volunteer)

    else:
        # Keep the existing assignment and status.
        # Refresh the profile information from the approved application.
        volunteer.name = application.name
        volunteer.skill = application.skills
        volunteer.location = application.location

        # Preserve the existing phone formatting unless it is empty.
        if not volunteer.phone:
            volunteer.phone = application.phone

    return volunteer


def sync_all_approved_applications():
    """
    Reconcile all previously approved applications
    with the Volunteer table.

    This does not delete existing volunteer records.
    """

    applications = VolunteerApplication.query.filter_by(
        status="Approved"
    ).order_by(
        VolunteerApplication.id.asc()
    ).all()

    try:

        for application in applications:
            sync_approved_application(application)

        db.session.commit()

        print(
            "Volunteer synchronization completed. "
            f"Checked {len(applications)} approved applications."
        )

    except Exception as error:

        db.session.rollback()

        print(
            "Volunteer synchronization failed:",
            str(error)
        )


# =========================================================
# PRIORITY ASSESSMENT
# DEMONSTRATION RULES - NOT VALIDATED EMERGENCY TRIAGE
# =========================================================

def assess_priority(need, people, details):

    urgent_terms = (
        "trapped",
        "injured",
        "medical",
        "no water",
        "stranded",
        "unconscious",
        "severe bleeding",
        "breathing difficulty"
    )

    text = (details or "").lower()
    need = (need or "").strip()
    people = max(0, people or 0)

    if need in ("Medical help", "Rescue") or any(
        term in text for term in urgent_terms
    ):
        return "High"

    if people >= 5 or need in ("Shelter", "Clean water"):
        return "Medium"

    return "Low"


def explain_priority(item):

    details = (item.details or "").lower()
    need = (item.need or "").strip()
    people = max(0, item.people or 0)

    urgent_terms = (
        "trapped",
        "injured",
        "medical",
        "no water",
        "stranded",
        "unconscious",
        "severe bleeding",
        "breathing difficulty"
    )

    if need in ("Medical help", "Rescue"):
        return (
            "High priority suggested: medical or rescue "
            "assistance requested."
        )

    matched_terms = [
        term for term in urgent_terms if term in details
    ]

    if matched_terms:
        return (
            "High priority suggested: urgent indicator detected - "
            + ", ".join(matched_terms) + "."
        )

    if people >= 5:
        return (
            "Medium priority suggested: five or more "
            "people are affected."
        )

    if need in ("Shelter", "Clean water"):
        return (
            "Medium priority suggested: essential shelter "
            "or clean-water support requested."
        )

    return (
        "Low priority suggested: no urgent indicators "
        "detected by demonstration rules."
    )


# =========================================================
# GENERAL HELPER FUNCTIONS
# =========================================================

def release_volunteers_for_request(request_id):

    volunteers = Volunteer.query.filter_by(
        assigned_request_id=request_id
    ).all()

    for volunteer in volunteers:
        volunteer.assigned_request_id = None
        volunteer.status = "Available"


def get_valid_people():

    try:
        return max(1, int(request.form.get("people", "1")))

    except (ValueError, TypeError):
        return 1


def get_coordinate(field, minimum, maximum):

    try:
        value = float(request.form.get(field, "").strip())

        if minimum <= value <= maximum:
            return value

    except (ValueError, TypeError, AttributeError):
        pass

    return None


# =========================================================
# MAIN DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    items = ReliefRequest.query.order_by(
        ReliefRequest.created_at.desc()
    ).all()

    total = len(items)

    pending = sum(
        item.status == "Pending" for item in items
    )

    high = sum(
        item.priority == "High" and item.status != "Resolved"
        for item in items
    )

    resolved = sum(
        item.status == "Resolved" for item in items
    )

    status_counts = {
        "Pending": sum(
            item.status == "Pending" for item in items
        ),
        "Assigned": sum(
            item.status == "Assigned" for item in items
        ),
        "Resolved": sum(
            item.status == "Resolved" for item in items
        )
    }

    priority_counts = {
        "High": sum(
            item.priority == "High" for item in items
        ),
        "Medium": sum(
            item.priority == "Medium" for item in items
        ),
        "Low": sum(
            item.priority == "Low" for item in items
        )
    }

    category_counts = {}

    for item in items:

        category = item.need or "Other"

        category_counts[category] = (
            category_counts.get(category, 0) + 1
        )

    # The chart counts actual Volunteer records.
    volunteers = Volunteer.query.all()

    volunteer_counts = {
        "Available": sum(
            volunteer.status == "Available"
            for volunteer in volunteers
        ),
        "Assigned": sum(
            volunteer.status == "Assigned"
            for volunteer in volunteers
        )
    }

    resolved_percentage = (
        round((resolved / total) * 100)
        if total > 0 else 0
    )

    top_category = (
        max(category_counts, key=category_counts.get)
        if category_counts else "No requests yet"
    )

    smart_insights = {
        "top_category": top_category,
        "pending": pending,
        "resolved_percentage": resolved_percentage,
        "available_volunteers": volunteer_counts["Available"],
        "assigned_volunteers": volunteer_counts["Assigned"]
    }

    map_items = [
        {
            "id": item.id,
            "name": item.name,
            "need": item.need,
            "location": item.location,
            "lat": item.latitude,
            "lng": item.longitude,
            "priority": item.priority,
            "status": item.status
        }
        for item in items
        if item.latitude is not None
        and item.longitude is not None
    ]

    return render_template(
        "dashboard.html",
        items=items,
        total=total,
        pending=pending,
        high=high,
        resolved=resolved,
        map_items=map_items,
        status_counts=status_counts,
        priority_counts=priority_counts,
        category_counts=category_counts,
        volunteer_counts=volunteer_counts,
        smart_insights=smart_insights
    )


# =========================================================
# EMERGENCY COMMAND CENTRE
# =========================================================

@app.route("/command-centre")
def command_centre():

    items = ReliefRequest.query.order_by(
        ReliefRequest.created_at.desc()
    ).all()

    total = len(items)

    pending = sum(
        item.status == "Pending" for item in items
    )

    high = sum(
        item.priority == "High" and item.status != "Resolved"
        for item in items
    )

    assigned = sum(
        item.status == "Assigned" for item in items
    )

    resolved = sum(
        item.status == "Resolved" for item in items
    )

    analyses = [
        {
            "item": item,
            "reason": explain_priority(item)
        }
        for item in items
    ]

    available_volunteers = Volunteer.query.filter_by(
        status="Available"
    ).all()

    return render_template(
        "command_centre.html",
        analyses=analyses,
        total=total,
        pending=pending,
        high=high,
        assigned=assigned,
        available_volunteers=available_volunteers,
        resolved=resolved
    )


# =========================================================
# FLOOD SIMULATION
# FICTIONAL HACKATHON DEMONSTRATION DATA
# =========================================================

@app.post("/simulate-flood")
def simulate_flood():

    if ReliefRequest.query.filter_by(
        name="Flood Simulation Alpha"
    ).first():

        flash(
            "The flood simulation has already been added.",
            "error"
        )

        return redirect(url_for("command_centre"))

    samples = [
        (
            "Flood Simulation Alpha",
            "Rescue",
            "Fictional report: people stranded after flooding.",
            "Bosan Road, Multan",
            30.2650,
            71.4900,
            6
        ),
        (
            "Flood Simulation Beta",
            "Medical help",
            "Fictional report: medical assistance requested.",
            "Gulgasht, Multan",
            30.2550,
            71.5100,
            3
        ),
        (
            "Flood Simulation Gamma",
            "Clean water",
            "Fictional report: drinking water required.",
            "Shah Rukn-e-Alam, Multan",
            30.1978,
            71.4697,
            12
        )
    ]

    for name, need, details, location, lat, lng, people in samples:

        priority = assess_priority(
            need,
            people,
            details
        )

        db.session.add(
            ReliefRequest(
                name=name,
                need=need,
                details=details,
                location=location,
                latitude=lat,
                longitude=lng,
                people=people,
                priority=priority,
                status="Pending"
            )
        )

    db.session.commit()

    flash(
        "Flood simulation started! Three fictional requests added.",
        "success"
    )

    return redirect(url_for("command_centre"))


# =========================================================
# NEW RELIEF REQUEST
# =========================================================

@app.route("/requests/new", methods=["GET", "POST"])
def new_request():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        need = request.form.get("need", "").strip()
        location = request.form.get("location", "").strip()

        if not name or not need or not location:

            flash(
                "Please complete the name, need and location fields.",
                "error"
            )

            return redirect(url_for("new_request"))

        people = get_valid_people()

        details = request.form.get("details", "").strip()

        priority = assess_priority(
            need,
            people,
            details
        )

        latitude = get_coordinate("latitude", -90, 90)
        longitude = get_coordinate("longitude", -180, 180)

        item = ReliefRequest(
            name=name,
            contact=request.form.get("contact", "").strip(),
            need=need,
            details=details,
            location=location,
            people=people,
            latitude=latitude,
            longitude=longitude,
            priority=priority
        )

        db.session.add(item)
        db.session.commit()

        flash(
            f"Request #{item.id} submitted. "
            f"Demo priority: {priority}.",
            "success"
        )

        return redirect(url_for("dashboard"))

    return render_template("new_request.html")


# =========================================================
# PUBLIC RELIEF PORTAL
# =========================================================

@app.route("/public-relief", methods=["GET", "POST"])
def public_relief():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        need = request.form.get("need", "").strip()
        location = request.form.get("location", "").strip()

        if not name or not need or not location:

            flash(
                "Please complete all required fields.",
                "error"
            )

            return redirect(url_for("public_relief"))

        people = get_valid_people()
        details = request.form.get("details", "").strip()

        priority = assess_priority(
            need,
            people,
            details
        )

        item = ReliefRequest(
            name=name,
            contact=request.form.get("contact", "").strip(),
            need=need,
            details=details,
            location=location,
            people=people,
            priority=priority
        )

        db.session.add(item)
        db.session.commit()

        flash(
            f"Your relief request #{item.id} has been submitted.",
            "success"
        )

        return redirect(url_for("public_relief"))

    return render_template("public_request.html")


# =========================================================
# VOLUNTEER APPLICATION FORM
# =========================================================

@app.route("/volunteer-apply", methods=["GET", "POST"])
def volunteer_apply():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        location = request.form.get("location", "").strip()
        skills = request.form.get("skills", "").strip()

        availability = request.form.get(
            "availability", "Flexible"
        ).strip()

        experience = request.form.get(
            "experience", ""
        ).strip()

        if not all([name, phone, location, skills]):

            flash(
                "Please complete all required fields.",
                "error"
            )

            return redirect(url_for("volunteer_apply"))

        application = VolunteerApplication(
            name=name,
            phone=phone,
            location=location,
            skills=skills,
            availability=availability,
            experience=experience
        )

        try:

            db.session.add(application)
            db.session.commit()

        except Exception:

            db.session.rollback()

            flash(
                "Your application could not be submitted. Please try again.",
                "error"
            )

            return redirect(url_for("volunteer_apply"))

        return render_template(
            "volunteer_application_submitted.html",
            application=application
        )

    return render_template("volunteer_apply.html")


# =========================================================
# APPLICATION STATUS AND ADDITIONAL INFORMATION
# =========================================================

@app.route("/application-status", methods=["GET", "POST"])
def application_status():

    application = None
    searched = False

    if request.method == "POST":

        token = request.form.get(
            "tracking_token", ""
        ).strip()

        additional_info = request.form.get(
            "additional_information", ""
        ).strip()

        searched = True

        if token:

            application = VolunteerApplication.query.filter_by(
                tracking_token=token
            ).first()

        if (
            application
            and additional_info
            and application.status == "More Information Required"
        ):

            if len(additional_info) > 500:

                flash(
                    "Please keep your response under 500 characters.",
                    "error"
                )

            else:

                existing_experience = application.experience or ""

                application.experience = (
                    existing_experience
                    + "\n\nAdditional information from applicant:\n"
                    + additional_info
                ).strip()

                application.status = "Pending"

                application.applicant_message = (
                    "Thank you. Your additional information "
                    "has been received and is awaiting review."
                )

                try:

                    db.session.commit()

                    flash(
                        "Your additional information was submitted successfully.",
                        "success"
                    )

                except Exception:

                    db.session.rollback()

                    flash(
                        "Your information could not be submitted. Please try again.",
                        "error"
                    )

                return render_template(
                    "volunteer_application_status.html",
                    application=application,
                    searched=True
                )

    return render_template(
        "volunteer_application_status.html",
        application=application,
        searched=searched
    )


# =========================================================
# VOLUNTEER APPLICATION REVIEW LIST
# =========================================================

@app.route("/volunteer-applications")
def volunteer_applications():

    applications = VolunteerApplication.query.order_by(
        VolunteerApplication.created_at.desc()
    ).all()

    return render_template(
        "volunteer_applications.html",
        applications=applications
    )


# =========================================================
# APPROVE / REJECT / REQUEST MORE INFORMATION
# =========================================================

@app.post("/volunteer-applications/<int:application_id>/review")
def review_volunteer_application(application_id):

    application = db.get_or_404(
        VolunteerApplication,
        application_id
    )

    action = request.form.get(
        "action", ""
    ).strip()

    rejection_reason = request.form.get(
        "rejection_reason", ""
    ).strip()

    reviewer_comments = request.form.get(
        "reviewer_comments", ""
    ).strip()

    applicant_message = request.form.get(
        "applicant_message", ""
    ).strip()

    if action not in (
        "approve",
        "reject",
        "request_information"
    ):

        flash("Invalid review action.", "error")

        return redirect(url_for("volunteer_applications"))

    if application.status not in (
        "Pending",
        "More Information Required"
    ):

        flash(
            "This application has already received a final decision.",
            "error"
        )

        return redirect(url_for("volunteer_applications"))

    if action == "reject" and not rejection_reason:

        flash(
            "Please provide a reason before rejecting an application.",
            "error"
        )

        return redirect(url_for("volunteer_applications"))

    try:

        if action == "approve":

            application.status = "Approved"
            application.rejection_reason = ""

            volunteer = sync_approved_application(application)

            if volunteer is None:

                raise ValueError(
                    "Could not create or locate the volunteer record."
                )

        elif action == "reject":

            application.status = "Rejected"
            application.rejection_reason = rejection_reason

        elif action == "request_information":

            application.status = "More Information Required"
            application.rejection_reason = ""

        application.reviewer_comments = reviewer_comments
        application.applicant_message = applicant_message
        application.reviewed_at = datetime.utcnow()

        db.session.commit()

        if action == "approve":

            flash(
                f"{application.name} approved and synchronized "
                "with the Volunteer Network.",
                "success"
            )

        elif action == "reject":

            flash(
                f"{application.name}'s application has been rejected.",
                "success"
            )

        else:

            flash(
                "Additional information has been requested.",
                "success"
            )

    except Exception as error:

        db.session.rollback()

        app.logger.exception(
            "Volunteer application review failed: %s",
            error
        )

        flash(
            "The review could not be saved. Please try again.",
            "error"
        )

    return redirect(url_for("volunteer_applications"))


# =========================================================
# UPDATE RELIEF REQUEST STATUS
# =========================================================

@app.post("/requests/<int:request_id>/status")
def update_status(request_id):

    item = db.get_or_404(
        ReliefRequest,
        request_id
    )

    status = request.form.get("status", "")

    if status not in ("Pending", "Assigned", "Resolved"):

        flash("Invalid request status.", "error")

        return redirect(url_for("dashboard"))

    if status == "Assigned":

        assigned_volunteer = Volunteer.query.filter_by(
            assigned_request_id=item.id,
            status="Assigned"
        ).first()

        if assigned_volunteer is None:

            flash(
                "Assign a volunteer before marking this request as Assigned.",
                "error"
            )

            return redirect(url_for("dashboard"))

    if status in ("Pending", "Resolved"):

        release_volunteers_for_request(item.id)

    item.status = status

    db.session.commit()

    flash(
        f"Request #{item.id} updated to {status}.",
        "success"
    )

    return redirect(url_for("dashboard"))


# =========================================================
# REQUESTS API
# =========================================================

@app.get("/api/requests")
def api_requests():

    items = ReliefRequest.query.order_by(
        ReliefRequest.created_at.desc()
    ).all()

    return jsonify([
        {
            "id": item.id,
            "name": item.name,
            "need": item.need,
            "location": item.location,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "priority": item.priority,
            "status": item.status
        }
        for item in items
    ])


# =========================================================
# VOLUNTEER NETWORK
# =========================================================

@app.route("/volunteers", methods=["GET", "POST"])
def volunteers():

    if request.method == "POST":

        name = request.form.get(
            "name", ""
        ).strip()

        skill = request.form.get(
            "skill", ""
        ).strip()

        location = request.form.get(
            "location", "Multan"
        ).strip()

        if not name or not skill:

            flash(
                "Please enter a volunteer name and skill.",
                "error"
            )

            return redirect(url_for("volunteers"))

        volunteer = Volunteer(
            name=name,
            skill=skill,
            location=location or "Multan"
        )

        db.session.add(volunteer)

        try:

            db.session.commit()

            flash(
                "Volunteer registered successfully!",
                "success"
            )

        except Exception:

            db.session.rollback()

            flash(
                "Volunteer could not be registered. Please try again.",
                "error"
            )

        return redirect(url_for("volunteers"))

    all_volunteers = Volunteer.query.order_by(
        Volunteer.id.desc()
    ).all()

    open_requests = ReliefRequest.query.filter(
        ReliefRequest.status != "Resolved"
    ).order_by(
        ReliefRequest.created_at.desc()
    ).all()

    return render_template(
        "volunteers.html",
        volunteers=all_volunteers,
        requests=open_requests
    )


# =========================================================
# ASSIGN VOLUNTEER
# =========================================================

@app.post("/volunteers/<int:volunteer_id>/assign")
def assign_volunteer(volunteer_id):

    volunteer = db.get_or_404(
        Volunteer,
        volunteer_id
    )

    request_id = request.form.get(
        "request_id",
        type=int
    )

    if request_id is None:

        flash(
            "Please select a valid relief request.",
            "error"
        )

        return redirect(url_for("volunteers"))

    relief_request = db.get_or_404(
        ReliefRequest,
        request_id
    )

    if volunteer.status != "Available":

        flash(
            "This volunteer is not available.",
            "error"
        )

    elif relief_request.status == "Resolved":

        flash(
            "This request has already been resolved.",
            "error"
        )

    elif Volunteer.query.filter_by(
        assigned_request_id=relief_request.id,
        status="Assigned"
    ).first():

        flash(
            "A volunteer is already assigned to this request.",
            "error"
        )

    else:

        volunteer.assigned_request_id = relief_request.id
        volunteer.status = "Assigned"

        relief_request.status = "Assigned"

        try:

            db.session.commit()

            flash(
                "Volunteer assigned successfully!",
                "success"
            )

        except Exception:

            db.session.rollback()

            flash(
                "The assignment could not be saved.",
                "error"
            )

    return redirect(url_for("volunteers"))


# =========================================================
# RELEASE VOLUNTEER
# =========================================================

@app.post("/volunteers/<int:volunteer_id>/release")
def release_volunteer(volunteer_id):

    volunteer = db.get_or_404(
        Volunteer,
        volunteer_id
    )

    assigned_request_id = volunteer.assigned_request_id

    volunteer.assigned_request_id = None
    volunteer.status = "Available"

    if assigned_request_id is not None:

        relief_request = db.session.get(
            ReliefRequest,
            assigned_request_id
        )

        if (
            relief_request is not None
            and relief_request.status == "Assigned"
        ):

            other_assigned = Volunteer.query.filter(
                Volunteer.assigned_request_id == assigned_request_id,
                Volunteer.id != volunteer.id,
                Volunteer.status == "Assigned"
            ).first()

            if other_assigned is None:
                relief_request.status = "Pending"

    try:

        db.session.commit()

        flash(
            "Volunteer is now available.",
            "success"
        )

    except Exception:

        db.session.rollback()

        flash(
            "Volunteer could not be released. Please try again.",
            "error"
        )

    return redirect(url_for("volunteers"))


# =========================================================
# RESOURCE INVENTORY
# =========================================================

@app.route("/resources", methods=["GET", "POST"])
def resources():

    if request.method == "POST":

        name = request.form.get(
            "name", ""
        ).strip()

        category = request.form.get(
            "category", ""
        ).strip()

        location = request.form.get(
            "location", "Multan"
        ).strip()

        quantity = request.form.get(
            "quantity",
            type=int
        )

        if (
            not name
            or not category
            or quantity is None
            or quantity < 0
        ):

            flash(
                "Please enter valid resource information.",
                "error"
            )

            return redirect(url_for("resources"))

        resource = Resource(
            name=name,
            category=category,
            quantity=quantity,
            location=location or "Multan"
        )

        db.session.add(resource)

        try:

            db.session.commit()

            flash(
                "Resource added successfully!",
                "success"
            )

        except Exception:

            db.session.rollback()

            flash(
                "Resource could not be added.",
                "error"
            )

        return redirect(url_for("resources"))

    all_resources = Resource.query.order_by(
        Resource.id.desc()
    ).all()

    return render_template(
        "resources.html",
        resources=all_resources
    )


# =========================================================
# RESOURCE RESTOCK / USE
# =========================================================

@app.route(
    "/resources/<int:resource_id>/update",
    methods=["POST"]
)
def update_resource_quantity(resource_id):

    resource = db.get_or_404(
        Resource,
        resource_id
    )

    action = request.form.get("action")

    amount = request.form.get(
        "amount",
        type=int
    )

    if amount is None or amount <= 0:

        flash(
            "Please enter a quantity greater than zero.",
            "error"
        )

        return redirect(url_for("resources"))

    if action == "restock":

        resource.quantity += amount

        message = f"{amount} units added to {resource.name}."

    elif action == "use":

        if amount > resource.quantity:

            flash(
                "Not enough stock available.",
                "error"
            )

            return redirect(url_for("resources"))

        resource.quantity -= amount

        message = f"{amount} units used from {resource.name}."

    else:

        flash("Invalid stock action.", "error")

        return redirect(url_for("resources"))

    try:

        db.session.commit()

        flash(message, "success")

    except Exception:

        db.session.rollback()

        flash(
            "The inventory update could not be saved.",
            "error"
        )

    return redirect(url_for("resources"))


# =========================================================
# DEMONSTRATION DATA COMMAND
# =========================================================

@app.cli.command("seed-demo")
def seed_demo():

    if ReliefRequest.query.count():

        print(
            "Database already has requests; "
            "no demo records added."
        )

        return

    samples = [
        (
            "Ayesha",
            "Food",
            "Food needed for a family",
            "Shah Rukn-e-Alam, Multan",
            30.1978,
            71.4697,
            4,
            "Medium"
        ),
        (
            "Usman",
            "Medical help",
            "Elderly person needs medical assistance",
            "Gulgasht, Multan",
            30.2550,
            71.5100,
            2,
            "High"
        ),
        (
            "Community contact",
            "Clean water",
            "Drinking water required",
            "Bosan Road, Multan",
            30.2650,
            71.4900,
            8,
            "Medium"
        ),
        (
            "Volunteer desk",
            "Shelter",
            "Temporary shelter requested",
            "Cantt, Multan",
            30.1900,
            71.4550,
            3,
            "Medium"
        )
    ]

    for (
        name,
        need,
        details,
        location,
        lat,
        lng,
        people,
        priority
    ) in samples:

        db.session.add(
            ReliefRequest(
                name=name,
                need=need,
                details=details,
                location=location,
                latitude=lat,
                longitude=lng,
                people=people,
                priority=priority
            )
        )

    db.session.commit()

    print(
        "Added 4 clearly simulated Multan demo requests."
    )


# =========================================================
# SAFE DATABASE SCHEMA UPDATE
# =========================================================

def update_database_schema():

    with db.engine.begin() as connection:

        # Relief request migration
        relief_columns = [
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(relief_request)"
            ).fetchall()
        ]

        if "flood_simulation_id" not in relief_columns:

            connection.exec_driver_sql(
                "ALTER TABLE relief_request "
                "ADD COLUMN flood_simulation_id INTEGER "
                "REFERENCES flood_simulation(id)"
            )

        # Volunteer application migration
        application_columns = [
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(volunteer_application)"
            ).fetchall()
        ]

        new_columns = {
            "rejection_reason": "VARCHAR(250) DEFAULT ''",
            "reviewer_comments": "VARCHAR(1000) DEFAULT ''",
            "applicant_message": "VARCHAR(1000) DEFAULT ''",
            "reviewed_at": "DATETIME",
            "tracking_token": "VARCHAR(64)"
        }

        for column_name, column_type in new_columns.items():

            if column_name not in application_columns:

                connection.exec_driver_sql(
                    f"ALTER TABLE volunteer_application "
                    f"ADD COLUMN {column_name} {column_type}"
                )

        # Populate tracking tokens for older applications.
        existing_applications = connection.exec_driver_sql(
            "SELECT id FROM volunteer_application "
            "WHERE tracking_token IS NULL OR tracking_token = ''"
        ).fetchall()

        for application in existing_applications:

            token = secrets.token_urlsafe(32)

            connection.exec_driver_sql(
                "UPDATE volunteer_application "
                "SET tracking_token = ? WHERE id = ?",
                (token, application[0])
            )

        # Ensure tracking tokens are unique.
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "ix_volunteer_application_tracking_token "
            "ON volunteer_application (tracking_token)"
        )


# =========================================================
# APPLICATION STARTUP
# =========================================================

if __name__ == "__main__":

    with app.app_context():

        db.create_all()

        update_database_schema()

        # Reconcile approved applications on startup.
        sync_all_approved_applications()

    app.run(debug=True)
