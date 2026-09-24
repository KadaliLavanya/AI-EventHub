from flask import Flask, render_template, request, redirect, url_for, session, Response
import sqlite3
import os
import csv
import io

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from google import genai
except ImportError:
    genai = None


# =========================================================
# LOAD ENVIRONMENT
# =========================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "AI_EventHub_Secure_Secret_2026"
)


# =========================================================
# ADMIN LOGIN SETTINGS
# =========================================================

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "admin"
).strip()

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "AIEventHub@2026"
).strip()


# =========================================================
# GEMINI AI
# =========================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

client = None

if (
    genai is not None
    and GEMINI_API_KEY
    and GEMINI_API_KEY != "YOUR_API_KEY_HERE"
):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        client = None


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db_connection():
    conn = sqlite3.connect("eventhub.db")
    conn.row_factory = sqlite3.Row
    return conn


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    conn = get_db_connection()

    # -----------------------------------------------------
    # USERS
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            branch TEXT,
            year TEXT,
            interest TEXT
        )
    """)

    # -----------------------------------------------------
    # EVENTS
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            date TEXT,
            venue TEXT,
            category TEXT,
            seats INTEGER
        )
    """)

    # -----------------------------------------------------
    # REGISTRATIONS
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_id INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(event_id) REFERENCES events(id)
        )
    """)

    # -----------------------------------------------------
    # NOTIFICATIONS
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # -----------------------------------------------------
    # SAMPLE EVENTS
    # -----------------------------------------------------

    event_count = conn.execute(
        "SELECT COUNT(*) FROM events"
    ).fetchone()[0]

    if event_count == 0:

        sample_events = [

            (
                "AI & Machine Learning Workshop",
                "Learn the basics of Artificial Intelligence and Machine Learning.",
                "2026-10-05",
                "CSE Seminar Hall",
                "AI & ML",
                100
            ),

            (
                "Web Development Bootcamp",
                "Build a modern website using HTML, CSS and JavaScript.",
                "2026-10-10",
                "Computer Lab",
                "Web Development",
                80
            ),

            (
                "College Hackathon 2026",
                "Build innovative solutions and compete with other students.",
                "2026-10-15",
                "Innovation Lab",
                "Hackathon",
                150
            ),

            (
                "Python Coding Contest",
                "Test your Python programming and problem-solving skills.",
                "2026-10-20",
                "Programming Lab",
                "Coding",
                120
            )
        ]

        conn.executemany("""
            INSERT INTO events
            (
                title,
                description,
                date,
                venue,
                category,
                seats
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, sample_events)

    conn.commit()
    conn.close()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    logged_in = "user_id" in session

    return render_template(
        "index.html",
        logged_in=logged_in
    )

# =========================================================
# STUDENT REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        branch = request.form.get("branch", "").strip()
        year = request.form.get("year", "").strip()
        interest = request.form.get("interest", "").strip()

        if not name or not email or not password:
            return render_template(
                "register.html",
                error="Please fill all required fields."
            )

        if len(password) < 6:
            return render_template(
                "register.html",
                error="Password must contain at least 6 characters."
            )

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()

        try:

            conn.execute("""
                INSERT INTO users
                (
                    name,
                    email,
                    password,
                    branch,
                    year,
                    interest
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                name,
                email,
                hashed_password,
                branch,
                year,
                interest
            ))

            conn.commit()
            conn.close()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:

            conn.close()

            return render_template(
                "register.html",
                error="Email already registered. Please login."
            )

    return render_template("register.html")


# =========================================================
# STUDENT LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    error = ""

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db_connection()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE LOWER(email) = ?
        """, (email,)).fetchone()

        conn.close()

        if user:

            try:
                password_correct = check_password_hash(
                    user["password"],
                    password
                )
            except Exception:
                password_correct = False

            if password_correct:

                session.clear()

                session["user_id"] = user["id"]

                return redirect(url_for("dashboard"))

        error = "Invalid email or password!"

    return render_template(
        "login.html",
        error=error
    )


# =========================================================
# STUDENT DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (session["user_id"],)).fetchone()

    if not user:
        conn.close()
        session.clear()
        return redirect(url_for("login"))

    recommended_events = conn.execute("""
        SELECT * FROM events
        ORDER BY date
    """).fetchall()

    registration_count = conn.execute("""
        SELECT COUNT(*)
        FROM registrations
        WHERE user_id = ?
    """, (session["user_id"],)).fetchone()[0]

    event_count = conn.execute("""
        SELECT COUNT(*)
        FROM events
    """).fetchone()[0]

    unread_count = conn.execute("""
        SELECT COUNT(*)
        FROM notifications
        WHERE user_id = ?
        AND is_read = 0
    """, (session["user_id"],)).fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        user=user,
        recommended_events=recommended_events,
        registration_count=registration_count,
        event_count=event_count,
        unread_count=unread_count
    )


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (session["user_id"],)).fetchone()

    conn.close()

    if not user:
        session.clear()
        return redirect(url_for("login"))

    return render_template(
        "profile.html",
        user=user
    )


# =========================================================
# EDIT PROFILE
# =========================================================

@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (session["user_id"],)).fetchone()

    if not user:
        conn.close()
        session.clear()
        return redirect(url_for("login"))

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        branch = request.form.get("branch", "").strip()
        year = request.form.get("year", "").strip()
        interest = request.form.get("interest", "").strip()

        conn.execute("""
            UPDATE users
            SET
                name = ?,
                branch = ?,
                year = ?,
                interest = ?
            WHERE id = ?
        """, (
            name,
            branch,
            year,
            interest,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("profile"))

    conn.close()

    return render_template(
        "edit_profile.html",
        user=user
    )


# =========================================================
# CHANGE PASSWORD
# =========================================================

@app.route("/change-password", methods=["GET", "POST"])
def change_password():

    if "user_id" not in session:
        return redirect(url_for("login"))

    message = ""
    error = ""

    if request.method == "POST":

        current_password = request.form.get(
            "current_password",
            ""
        )

        new_password = request.form.get(
            "new_password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        conn = get_db_connection()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE id = ?
        """, (session["user_id"],)).fetchone()

        if not user:
            conn.close()
            session.clear()
            return redirect(url_for("login"))

        if not check_password_hash(
            user["password"],
            current_password
        ):

            conn.close()

            return render_template(
                "change_password.html",
                message="",
                error="Current password is incorrect."
            )

        if new_password != confirm_password:

            conn.close()

            return render_template(
                "change_password.html",
                message="",
                error="New passwords do not match."
            )

        if len(new_password) < 6:

            conn.close()

            return render_template(
                "change_password.html",
                message="",
                error="New password must contain at least 6 characters."
            )

        hashed_password = generate_password_hash(
            new_password
        )

        conn.execute("""
            UPDATE users
            SET password = ?
            WHERE id = ?
        """, (
            hashed_password,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        message = "Password changed successfully!"

    return render_template(
        "change_password.html",
        message=message,
        error=error
    )


# =========================================================
# EVENTS
# =========================================================

@app.route("/events")
def events():

    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    venue = request.args.get("venue", "").strip()
    date = request.args.get("date", "").strip()
    availability = request.args.get(
        "availability",
        ""
    ).strip()

    conn = get_db_connection()

    query = """
        SELECT
            events.*,
            COUNT(registrations.id) AS registered_count
        FROM events

        LEFT JOIN registrations
        ON events.id = registrations.event_id

        WHERE 1 = 1
    """

    params = []

    if search:

        query += """
            AND (
                events.title LIKE ?
                OR events.description LIKE ?
                OR events.venue LIKE ?
            )
        """

        search_value = "%" + search + "%"

        params.extend([
            search_value,
            search_value,
            search_value
        ])

    if category:

        query += """
            AND events.category = ?
        """

        params.append(category)

    if venue:

        query += """
            AND events.venue LIKE ?
        """

        params.append("%" + venue + "%")

    if date:

        query += """
            AND events.date = ?
        """

        params.append(date)

    query += """
        GROUP BY events.id
        ORDER BY events.date
    """

    all_events = conn.execute(
        query,
        params
    ).fetchall()

    conn.close()

    filtered_events = []

    for event in all_events:

        available_seats = (
            event["seats"]
            - event["registered_count"]
        )

        if availability == "available":

            if available_seats <= 0:
                continue

        elif availability == "limited":

            if available_seats > 20 or available_seats <= 0:
                continue

        elif availability == "full":

            if available_seats > 0:
                continue

        filtered_events.append(event)

    return render_template(
        "events.html",
        events=filtered_events,
        search=search,
        category=category,
        venue=venue,
        date=date,
        availability=availability
    )


# =========================================================
# EVENT DETAILS
# =========================================================

@app.route("/event/<int:event_id>")
def event_details(event_id):

    conn = get_db_connection()

    event = conn.execute("""
        SELECT
            events.*,
            COUNT(registrations.id) AS registered_count
        FROM events

        LEFT JOIN registrations
        ON events.id = registrations.event_id

        WHERE events.id = ?

        GROUP BY events.id
    """, (event_id,)).fetchone()

    conn.close()

    if not event:
        return "Event not found!"

    available_seats = (
        event["seats"]
        - event["registered_count"]
    )

    return render_template(
        "event_details.html",
        event=event,
        available_seats=available_seats
    )


# =========================================================
# REGISTER FOR EVENT
# =========================================================

@app.route("/register-event/<int:event_id>")
def register_event(event_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db_connection()

    event = conn.execute("""
        SELECT *
        FROM events
        WHERE id = ?
    """, (event_id,)).fetchone()

    if not event:

        conn.close()

        return "Event not found!"

    existing = conn.execute("""
        SELECT *
        FROM registrations
        WHERE user_id = ?
        AND event_id = ?
    """, (
        user_id,
        event_id
    )).fetchone()

    if existing:

        conn.close()

        return "You are already registered for this event!"

    registered_count = conn.execute("""
        SELECT COUNT(*)
        FROM registrations
        WHERE event_id = ?
    """, (event_id,)).fetchone()[0]

    if registered_count >= event["seats"]:

        conn.close()

        return "Sorry! This event is full."

    conn.execute("""
        INSERT INTO registrations
        (
            user_id,
            event_id
        )
        VALUES (?, ?)
    """, (
        user_id,
        event_id
    ))

    conn.execute("""
        INSERT INTO notifications
        (
            user_id,
            message
        )
        VALUES (?, ?)
    """, (
        user_id,
        f"You successfully registered for {event['title']}."
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("my_registrations"))


# =========================================================
# MY REGISTRATIONS
# =========================================================

@app.route("/my-registrations")
def my_registrations():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    registrations = conn.execute("""
        SELECT
            events.id AS event_id,
            events.title,
            events.description,
            events.date,
            events.venue,
            events.category

        FROM registrations

        JOIN events
        ON registrations.event_id = events.id

        WHERE registrations.user_id = ?

        ORDER BY events.date
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "my_registrations.html",
        registrations=registrations
    )


# =========================================================
# CANCEL REGISTRATION
# =========================================================

@app.route("/cancel-registration/<int:event_id>")
def cancel_registration(event_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    event = conn.execute("""
        SELECT title
        FROM events
        WHERE id = ?
    """, (event_id,)).fetchone()

    existing = conn.execute("""
        SELECT *
        FROM registrations
        WHERE user_id = ?
        AND event_id = ?
    """, (
        session["user_id"],
        event_id
    )).fetchone()

    if existing:

        conn.execute("""
            DELETE FROM registrations
            WHERE user_id = ?
            AND event_id = ?
        """, (
            session["user_id"],
            event_id
        ))

        if event:

            conn.execute("""
                INSERT INTO notifications
                (
                    user_id,
                    message
                )
                VALUES (?, ?)
            """, (
                session["user_id"],
                f"Your registration for {event['title']} has been cancelled."
            ))

    conn.commit()
    conn.close()

    return redirect(url_for("my_registrations"))


# =========================================================
# NOTIFICATIONS
# =========================================================

@app.route("/notifications")
def notifications():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    notifications = conn.execute("""
        SELECT *
        FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (session["user_id"],)).fetchall()

    unread_count = conn.execute("""
        SELECT COUNT(*)
        FROM notifications
        WHERE user_id = ?
        AND is_read = 0
    """, (session["user_id"],)).fetchone()[0]

    conn.close()

    return render_template(
        "notifications.html",
        notifications=notifications,
        unread_count=unread_count
    )


# =========================================================
# MARK NOTIFICATION READ
# =========================================================

@app.route("/mark-notification-read/<int:notification_id>")
def mark_notification_read(notification_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    conn.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
        AND user_id = ?
    """, (
        notification_id,
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("notifications"))


# =========================================================
# MARK ALL NOTIFICATIONS READ
# =========================================================

@app.route("/mark-all-notifications-read")
def mark_all_notifications_read():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    conn.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE user_id = ?
    """, (session["user_id"],))

    conn.commit()
    conn.close()

    return redirect(url_for("notifications"))


# =========================================================
# AI ASSISTANT
# =========================================================

@app.route("/assistant", methods=["GET", "POST"])
def assistant():

    question = ""
    answer = ""

    if request.method == "POST":

        question = request.form.get(
            "question",
            ""
        ).strip()

        conn = get_db_connection()

        events = conn.execute("""
            SELECT *
            FROM events
            ORDER BY date
        """).fetchall()

        conn.close()

        event_text = ""

        for event in events:

            event_text += f"""
Event: {event["title"]}
Description: {event["description"]}
Date: {event["date"]}
Venue: {event["venue"]}
Category: {event["category"]}
Seats: {event["seats"]}
"""

        if client and question:

            prompt = f"""
You are the AI Event Assistant for a college event portal called AI EventHub.

Available events:

{event_text}

Student question:

{question}

Answer using only the available event information.

Keep the answer simple, friendly and useful.

Do not invent events or information.
"""

            try:

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )

                answer = response.text

            except Exception:

                answer = (
                    "Sorry, AI assistant is temporarily unavailable."
                )

        elif not client:

            answer = (
                "Gemini AI is not connected. "
                "Please check your GEMINI_API_KEY in the .env file."
            )

        else:

            answer = "Please enter your question."

    return render_template(
        "assistant.html",
        question=question,
        answer=answer
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    error = ""

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):

            session.clear()

            session["admin"] = True

            return redirect(url_for("admin"))

        error = "Invalid username or password!"

    return render_template(
        "admin_login.html",
        error=error
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db_connection()

    # -----------------------------------------------------
    # TOTAL EVENTS
    # -----------------------------------------------------

    event_count = conn.execute("""
        SELECT COUNT(*)
        FROM events
    """).fetchone()[0]

    # -----------------------------------------------------
    # TOTAL STUDENTS
    # -----------------------------------------------------

    user_count = conn.execute("""
        SELECT COUNT(*)
        FROM users
    """).fetchone()[0]

    # -----------------------------------------------------
    # TOTAL REGISTRATIONS
    # -----------------------------------------------------

    registration_count = conn.execute("""
        SELECT COUNT(*)
        FROM registrations
    """).fetchone()[0]

    # -----------------------------------------------------
    # TOTAL SEATS
    # -----------------------------------------------------

    total_seats = conn.execute("""
        SELECT COALESCE(SUM(seats), 0)
        FROM events
    """).fetchone()[0]

    # -----------------------------------------------------
    # AVAILABLE SEATS
    # -----------------------------------------------------

    available_seats = max(
        total_seats - registration_count,
        0
    )

    # -----------------------------------------------------
    # EVENT ANALYTICS
    # -----------------------------------------------------

    events = conn.execute("""
        SELECT
            events.*,
            COUNT(registrations.id) AS registered_count

        FROM events

        LEFT JOIN registrations
        ON events.id = registrations.event_id

        GROUP BY events.id

        ORDER BY events.date
    """).fetchall()

    # -----------------------------------------------------
    # CATEGORY STATS
    # -----------------------------------------------------

    category_stats = conn.execute("""
        SELECT
            events.category,
            COUNT(registrations.id) AS registration_count

        FROM events

        LEFT JOIN registrations
        ON events.id = registrations.event_id

        GROUP BY events.category

        ORDER BY registration_count DESC
    """).fetchall()

    # -----------------------------------------------------
    # RECENT REGISTRATIONS
    # -----------------------------------------------------

    recent_registrations = conn.execute("""
        SELECT
            users.name,
            users.email,
            events.title,
            events.date

        FROM registrations

        JOIN users
        ON registrations.user_id = users.id

        JOIN events
        ON registrations.event_id = events.id

        ORDER BY registrations.id DESC

        LIMIT 5
    """).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        event_count=event_count,
        user_count=user_count,
        registration_count=registration_count,
        total_seats=total_seats,
        available_seats=available_seats,
        events=events,
        category_stats=category_stats,
        recent_registrations=recent_registrations
    )


# =========================================================
# ADD EVENT
# =========================================================

@app.route("/admin/add-event", methods=["GET", "POST"])
def add_event():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        date = request.form.get(
            "date",
            ""
        ).strip()

        venue = request.form.get(
            "venue",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        seats = request.form.get(
            "seats",
            "0"
        ).strip()

        try:
            seats = int(seats)
        except ValueError:
            seats = 0

        conn = get_db_connection()

        conn.execute("""
            INSERT INTO events
            (
                title,
                description,
                date,
                venue,
                category,
                seats
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            title,
            description,
            date,
            venue,
            category,
            seats
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("admin"))

    return render_template("add_event.html")


# =========================================================
# EDIT EVENT
# =========================================================

@app.route(
    "/admin/edit-event/<int:event_id>",
    methods=["GET", "POST"]
)
def edit_event(event_id):

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db_connection()

    event = conn.execute("""
        SELECT *
        FROM events
        WHERE id = ?
    """, (event_id,)).fetchone()

    if not event:

        conn.close()

        return "Event not found!"

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        date = request.form.get(
            "date",
            ""
        ).strip()

        venue = request.form.get(
            "venue",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        seats = request.form.get(
            "seats",
            "0"
        ).strip()

        try:
            seats = int(seats)
        except ValueError:
            seats = 0

        conn.execute("""
            UPDATE events

            SET
                title = ?,
                description = ?,
                date = ?,
                venue = ?,
                category = ?,
                seats = ?

            WHERE id = ?
        """, (
            title,
            description,
            date,
            venue,
            category,
            seats,
            event_id
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("admin"))

    conn.close()

    return render_template(
        "edit_event.html",
        event=event
    )


# =========================================================
# DELETE EVENT
# =========================================================

@app.route("/admin/delete-event/<int:event_id>")
def delete_event(event_id):

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db_connection()

    conn.execute("""
        DELETE FROM registrations
        WHERE event_id = ?
    """, (event_id,))

    conn.execute("""
        DELETE FROM events
        WHERE id = ?
    """, (event_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("admin"))


# =========================================================
# PARTICIPANTS
# =========================================================

@app.route("/admin/participants")
def participants():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    search = request.args.get(
        "search",
        ""
    ).strip()

    event_filter = request.args.get(
        "event",
        ""
    ).strip()

    conn = get_db_connection()

    query = """
        SELECT
            users.name,
            users.email,
            users.branch,
            users.year,
            events.title AS event_title,
            events.date AS event_date,
            events.venue,
            events.category

        FROM registrations

        JOIN users
        ON registrations.user_id = users.id

        JOIN events
        ON registrations.event_id = events.id

        WHERE 1 = 1
    """

    params = []

    if search:

        query += """
            AND (
                users.name LIKE ?
                OR users.email LIKE ?
                OR users.branch LIKE ?
            )
        """

        value = "%" + search + "%"

        params.extend([
            value,
            value,
            value
        ])

    if event_filter:

        query += """
            AND events.id = ?
        """

        params.append(event_filter)

    query += """
        ORDER BY events.date, users.name
    """

    participants_data = conn.execute(
        query,
        params
    ).fetchall()

    event_list = conn.execute("""
        SELECT
            id,
            title
        FROM events
        ORDER BY date
    """).fetchall()

    participant_count = len(participants_data)

    conn.close()

    return render_template(
        "participants.html",
        participants=participants_data,
        events=event_list,
        search=search,
        event_filter=event_filter,
        participant_count=participant_count
    )


# =========================================================
# EXPORT PARTICIPANTS CSV
# =========================================================

@app.route("/admin/export-participants")
def export_participants():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    search = request.args.get(
        "search",
        ""
    ).strip()

    event_filter = request.args.get(
        "event",
        ""
    ).strip()

    conn = get_db_connection()

    query = """
        SELECT
            users.name,
            users.email,
            users.branch,
            users.year,
            events.title AS event_title,
            events.date AS event_date,
            events.venue,
            events.category

        FROM registrations

        JOIN users
        ON registrations.user_id = users.id

        JOIN events
        ON registrations.event_id = events.id

        WHERE 1 = 1
    """

    params = []

    if search:

        query += """
            AND (
                users.name LIKE ?
                OR users.email LIKE ?
                OR users.branch LIKE ?
            )
        """

        value = "%" + search + "%"

        params.extend([
            value,
            value,
            value
        ])

    if event_filter:

        query += """
            AND events.id = ?
        """

        params.append(event_filter)

    query += """
        ORDER BY events.date, users.name
    """

    participants_data = conn.execute(
        query,
        params
    ).fetchall()

    conn.close()

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Student Name",
        "Email",
        "Branch",
        "Year",
        "Event",
        "Event Date",
        "Venue",
        "Category"
    ])

    for participant in participants_data:

        writer.writerow([
            participant["name"],
            participant["email"],
            participant["branch"],
            participant["year"],
            participant["event_title"],
            participant["event_date"],
            participant["venue"],
            participant["category"]
        ])

    response = Response(
        output.getvalue(),
        mimetype="text/csv"
    )

    response.headers["Content-Disposition"] = (
        "attachment; filename=AI_EventHub_Participants.csv"
    )

    return response


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin-logout")
def admin_logout():

    session.pop("admin", None)

    return redirect(url_for("home"))


# =========================================================
# STUDENT LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# =========================================================
# START APPLICATION
# =========================================================
init_db()

if __name__ == "__main__":

    print()
    print("======================================")
    print("       AI EventHub Started")
    print("======================================")
    print("Student Login : http://127.0.0.1:5000/login")
    print("Admin Login   : http://127.0.0.1:5000/admin-login")
    print("--------------------------------------")
    print("Admin Username:", ADMIN_USERNAME)
    print("======================================")
    print()

    app.run(debug=True)
