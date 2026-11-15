import urllib.request
import unicodedata
from difflib import SequenceMatcher
from math import radians, sin, cos, sqrt, atan2
import sqlite3
import os
import uuid
import re
import subprocess
import tempfile
import imageio_ffmpeg
import json
import time
import urllib.parse
import urllib.request

from datetime import datetime
from functools import wraps
import secrets
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify, session, Response
)
import csv
import io
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from gnani.stt import GnaniSTTClient
from gnani.tts import GnaniTTSClient
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv()

app = Flask(__name__)
# Register Nirmala UI font for multilingual PDF reports
pdf_font_path = os.path.join(
    app.root_path, "fonts", "NirmalaText-Regular.ttf"
)

pdfmetrics.registerFont(
    TTFont("Nirmala", pdf_font_path, shapable=True)
)

pdfmetrics.registerFontFamily(
    "Nirmala",
    normal="Nirmala",
    bold="Nirmala",
    italic="Nirmala",
    boldItalic="Nirmala"
)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is missing from your .env file."
    )

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
UPLOAD_FOLDER = os.path.join("static", "uploads")
AUDIO_FOLDER = os.path.join("static", "audio")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
DB = "nammavoice.db"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)

API_KEY = os.getenv("GNANI_API_KEY")

stt_client = None
tts_client = None

if API_KEY:
    try:
        stt_client = GnaniSTTClient(api_key=API_KEY)
        tts_client = GnaniTTSClient(api_key=API_KEY)
        print("Gnani AI clients initialized.")
    except Exception as e:
        print("Gnani AI initialization error:", e)
else:
    print("WARNING: GNANI_API_KEY was not found in .env")


_last_geocode_request = 0.0


# =========================================================
# LANGUAGE DETECTION
# =========================================================

def detect_language(text, fallback="Kannada"):
    if not text:
        return fallback

    counts = {
        "Kannada": 0,
        "Telugu": 0,
        "Tamil": 0,
        "Hindi": 0,
        "English": 0
    }

    for char in text:
        code = ord(char)

        if 0x0C80 <= code <= 0x0CFF:
            counts["Kannada"] += 1
        elif 0x0C00 <= code <= 0x0C7F:
            counts["Telugu"] += 1
        elif 0x0B80 <= code <= 0x0BFF:
            counts["Tamil"] += 1
        elif 0x0900 <= code <= 0x097F:
            counts["Hindi"] += 1
        elif char.isascii() and char.isalpha():
            counts["English"] += 1

    detected = max(counts, key=counts.get)

    if counts[detected] == 0:
        return fallback

    return detected


# =========================================================
# DEPARTMENT CLASSIFICATION
# =========================================================

DEPARTMENTS = {
    "Water Supply": [
        "water", "drinking water", "no water", "water supply",
        "tap", "pipeline", "pipe leakage", "ಬರ ನೀರು",
        "ನೀರು", "ಕುಡಿಯುವ ನೀರು", "ನೀರಿನ ಸಮಸ್ಯೆ",
        "ನೀರು ಬರುತ್ತಿಲ್ಲ", "ನೀರಿನ ಪೈಪ್",
        "पानी", "पेयजल", "पानी नहीं",
        "నీరు", "తాగునీరు", "నీటి సమస్య",
        "தண்ணீர்", "குடிநீர்", "தண்ணீர் இல்லை"
    ],

    "Road Development / PWD": [
        "road", "pothole", "roads", "street", "bridge",
        "road damage", "broken road",
        "ರಸ್ತೆ", "ಗುಂಡಿ", "ರಸ್ತೆ ಹಾಳಾಗಿದೆ",
        "ರಸ್ತೆ ಸಮಸ್ಯೆ", "ಸೇತುವೆ",
        "सड़क", "गड्ढा", "खराब सड़क",
        "రోడ్డు", "గుంత", "రోడ్డు సమస్య",
        "சாலை", "பள்ளம்", "சாலை பிரச்சினை"
    ],

    "Sanitation": [
        "garbage", "waste", "dustbin", "cleaning",
        "dirty", "rubbish", "trash",
        "ಕಸ", "ತ್ಯಾಜ್ಯ", "ಸ್ವಚ್ಛತೆ", "ಕಸ ಸಂಗ್ರಹ",
        "குப்பை", "சுத்தம்", "கழிவு",
        "చెత్త", "పరిశుభ్రత", "వ్యర్థాలు",
        "कचरा", "सफाई", "गंदगी"
    ],

    "Drainage": [
        "drainage", "drain", "sewage", "sewer",
        "blocked drain", "drain overflow",
        "ಚರಂಡಿ", "ಒಳಚರಂಡಿ", "ಚರಂಡಿ ನೀರು",
        "கழிவுநீர்", "வடிகால்",
        "మురుగునీరు", "కాలువ",
        "नाली", "नाली जाम", "गंदा पानी"
    ],

    "Electricity / Streetlights": [
        "electricity", "power cut", "streetlight",
        "street light", "electric pole", "no power",
        "current", "light not working",
        "ವಿದ್ಯುತ್", "ಕರೆಂಟ್", "ಬೀದಿ ದೀಪ",
        "ವಿದ್ಯುತ್ ಸಮಸ್ಯೆ", "ದೀಪ ಉರಿಯುತ್ತಿಲ್ಲ",
        "बिजली", "बिजली कटौती", "स्ट्रीट लाइट",
        "విద్యుత్", "కరెంట్", "వీధి దీపం",
        "மின்சாரம்", "தெருவிளக்கு", "மின்தடை"
    ]
}


def analyze(text):
    text = (text or "").lower()

    department_scores = {}

    for department, keywords in DEPARTMENTS.items():
        score = 0

        for keyword in keywords:
            if keyword.lower() in text:
                score += 1

        department_scores[department] = score

    best_department = max(
        department_scores,
        key=department_scores.get
    )

    if department_scores[best_department] == 0:
        best_department = "General Public Grievance"

    urgent_words = [
        "emergency", "danger", "accident", "life threatening",
        "fire", "electric shock", "ಅಪಾಯ", "ತುರ್ತು", "ಅಪಘಾತ",
        "आपातकाल", "खतरा", "दुर्घटना",
        "ప్రమాదం", "అత్యవసరం", "பாதிப்பு", "அவசரம்",
        "விபத்து"
    ]

    high_words = [
        "not working", "overflow", "no water", "three days",
        "3 days", "broken", "damaged", "blocked",
        "not available", "ಕೆಲಸ ಮಾಡುತ್ತಿಲ್ಲ", "ನೀರು ಬರುತ್ತಿಲ್ಲ",
        "ಹಾಳಾಗಿದೆ", "ಮುಚ್ಚಿಹೋಗಿದೆ",
        "काम नहीं कर रहा", "पानी नहीं",
        "పని చేయడం లేదు", "నీరు రావడం లేదు",
        "வேலை செய்யவில்லை", "தண்ணீர் இல்லை"
    ]

    medium_words = [
        "every day", "daily", "many days", "often",
        "repeatedly", "ಪ್ರತಿದಿನ", "ದಿನವೂ", "ಹಲವು ದಿನಗಳಿಂದ",
        "रोज", "हर दिन", "कई दिनों से",
        "ప్రతిరోజు", "రోజూ",
        "தினமும்", "பல நாட்களாக"
    ]

    if any(word in text for word in urgent_words):
        severity = "Urgent"
    elif any(word in text for word in high_words):
        severity = "High"
    elif any(word in text for word in medium_words):
        severity = "Medium"
    elif text.strip():
        severity = "Medium"
    else:
        severity = "Low"

    return best_department, severity


# =========================================================
# DATABASE HELPERS
# =========================================================

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def current_timestamp():
    return datetime.now().strftime("%d-%m-%Y %I:%M %p")


def add_status_history(con, complaint_id, status, created_at=None):
    if not created_at:
        created_at = current_timestamp()

    con.execute("""
        INSERT INTO complaint_status_history
        (complaint_id, status, changed_at)
        VALUES (?, ?, ?)
    """, (complaint_id, status, created_at))
# =========================================================
# SIMILAR / DUPLICATE COMPLAINT DETECTION
# =========================================================

SIMILARITY_THRESHOLD = 0.65
DUPLICATE_DISTANCE_KM = 0.5
# Synonym mapping for civic complaint duplicate detection
COMPLAINT_SYNONYMS = {
    "blockage": [
        "blocked", "clogged", "clog", "choked"
    ],
    "drainage": [
        "drain", "drainage pipe", "sewer"
    ],
    "wastewater": [
        "sewage", "dirty water", "waste water"
    ],
    "overflow": [
        "overflowing", "spreading", "spilled"
    ],
    "leakage": [
        "leaking", "leak"
    ],
    "pothole": [
        "road hole", "crater"
    ]
}

def normalize_for_similarity(text):
    text = unicodedata.normalize("NFKC", (text or "").lower())
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def complaint_similarity(text1, text2):
    first = normalize_for_similarity(text1)
    second = normalize_for_similarity(text2)

    if not first or not second:
        return 0.0

    # Replace known synonyms with common terms
    for common_word, synonyms in COMPLAINT_SYNONYMS.items():
        for synonym in synonyms:
            first = re.sub(
                r"\b" + re.escape(synonym) + r"\b",
                common_word,
                first
            )

            second = re.sub(
                r"\b" + re.escape(synonym) + r"\b",
                common_word,
                second
            )

    sequence_score = SequenceMatcher(
        None, first, second
    ).ratio()

    words1 = set(first.split())
    words2 = set(second.split())

    union = words1 | words2

    token_score = (
        len(words1 & words2) / len(union)
        if union else 0.0
    )

    return max(sequence_score, token_score)
def distance_in_km(lat1, lon1, lat2, lon2):
    try:
        lat1, lon1, lat2, lon2 = map(
            float, (lat1, lon1, lat2, lon2)
        )
    except (TypeError, ValueError):
        return None

    radius = 6371.0

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(dlon / 2) ** 2
    )

    return radius * 2 * atan2(
        sqrt(a), sqrt(1 - a)
    )


def find_similar_complaint(
    con, text, department, location, latitude, longitude
):
    if not text or not location:
        return None

    candidates = con.execute("""
        SELECT complaint_id, original_text, complaint_text,
               location, latitude, longitude, duplicate_of
        FROM complaints
        WHERE department = ?
        ORDER BY id DESC
        LIMIT 1000
    """, (department,)).fetchall()

    new_location = normalize_for_similarity(location)

    best_match = None
    best_score = 0.0

    for old in candidates:
        old_location = normalize_for_similarity(old["location"])

        same_location = (
            new_location != ""
            and new_location == old_location
        )

        distance = distance_in_km(
            latitude,
            longitude,
            old["latitude"],
            old["longitude"]
        )

        nearby_location = (
            distance is not None
            and distance <= DUPLICATE_DISTANCE_KM
        )

        if not same_location and not nearby_location:
            continue

        old_text = (
            old["original_text"]
            or old["complaint_text"]
            or ""
        )

        score = complaint_similarity(text, old_text)

        if (
            score >= SIMILARITY_THRESHOLD
            and score > best_score
        ):
            best_score = score

            best_match = {
                "complaint_id": (
                    old["duplicate_of"]
                    or old["complaint_id"]
                ),
                "similarity": round(score, 3)
            }

    return best_match

# =========================================================
# LOCATION GEOCODING
# =========================================================

def geocode_location(location):
    global _last_geocode_request

    if not location or not location.strip():
        return None, None

    location = location.strip()

    try:
        with db() as con:
            cached = con.execute("""
                SELECT latitude, longitude
                FROM location_cache
                WHERE location = ?
            """, (location,)).fetchone()

            if cached:
                return cached["latitude"], cached["longitude"]

        wait_time = 1.1 - (time.time() - _last_geocode_request)

        if wait_time > 0:
            time.sleep(wait_time)

        query = urllib.parse.urlencode({
            "q": location + ", Karnataka, India",
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "in"
        })

        url = "https://nominatim.openstreetmap.org/search?" + query

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "NammaVoice/1.0 (civic complaint mapping)"
            }
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        _last_geocode_request = time.time()

        if not data:
            return None, None

        latitude = data[0].get("lat")
        longitude = data[0].get("lon")

        with db() as con:
            con.execute("""
                INSERT OR REPLACE INTO location_cache
                (location, latitude, longitude)
                VALUES (?, ?, ?)
            """, (location, latitude, longitude))

        return latitude, longitude

    except Exception as e:
        print("Geocoding error:", e)
        return None, None


# =========================================================
# DATABASE INITIALIZATION AND MIGRATION
# =========================================================

def init_db():
    with db() as con:

        con.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id TEXT UNIQUE,
                name TEXT,
                phone TEXT,
                language TEXT,
                original_text TEXT,
                complaint_text TEXT,
                department TEXT,
                severity TEXT,
                location TEXT,
                latitude TEXT,
                longitude TEXT,
                photo TEXT,
                status TEXT DEFAULT 'Submitted',
                created_at TEXT
            )
        """)
                # Add duplicate detection columns safely
        complaint_columns = [
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(complaints)"
            ).fetchall()
        ]

        if "duplicate_of" not in complaint_columns:
            con.execute("""
                ALTER TABLE complaints
                ADD COLUMN duplicate_of TEXT
            """)

        if "similarity_score" not in complaint_columns:
            con.execute("""
                ALTER TABLE complaints
                ADD COLUMN similarity_score REAL
            """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS location_cache (
                location TEXT PRIMARY KEY,
                latitude TEXT,
                longitude TEXT
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS complaint_remarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id TEXT,
                remark_text TEXT,
                language TEXT,
                created_at TEXT NOT NULL
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS complaint_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT
            )
        """)

        # Check whether the history table needs a created_at column.
        history_columns = [
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(complaint_status_history)"
            ).fetchall()
        ]

        if "created_at" not in history_columns:
            con.execute("""
                ALTER TABLE complaint_status_history
                ADD COLUMN created_at TEXT
            """)

        # Update language for older complaints.
        old_complaints = con.execute("""
            SELECT id, original_text, complaint_text
            FROM complaints
            WHERE language IS NULL OR language = ''
        """).fetchall()

        for row in old_complaints:
            text_value = row["original_text"] or row["complaint_text"] or ""
            language = detect_language(text_value)

            con.execute("""
                UPDATE complaints
                SET language = ?
                WHERE id = ?
            """, (language, row["id"]))

        # Fill missing history timestamps.
        con.execute("""
            UPDATE complaint_status_history
            SET created_at = COALESCE(
                (
                    SELECT complaints.created_at
                    FROM complaints
                    WHERE complaints.complaint_id =
                          complaint_status_history.complaint_id
                ),
                ?
            )
            WHERE created_at IS NULL OR created_at = ''
        """, (current_timestamp(),))

        # Add initial history entries for existing complaints.
        complaints = con.execute("""
            SELECT complaint_id, status, created_at
            FROM complaints
        """).fetchall()

        for complaint in complaints:
            complaint_id = complaint["complaint_id"]

            existing_history = con.execute("""
                SELECT COUNT(*) AS total
                FROM complaint_status_history
                WHERE complaint_id = ?
            """, (complaint_id,)).fetchone()["total"]

            if existing_history == 0:
                submitted_at = (
                    complaint["created_at"] or current_timestamp()
                )

                add_status_history(
                    con,
                    complaint_id,
                    "Submitted",
                    submitted_at
                )

                current_status = complaint["status"] or "Submitted"

                if current_status != "Submitted":
                    add_status_history(
                        con,
                        complaint_id,
                        current_status,
                        submitted_at
                    )

    # Geocode existing complaints with missing coordinates.
    with db() as con:
        missing_locations = con.execute("""
            SELECT id, location
            FROM complaints
            WHERE (latitude IS NULL OR latitude = ''
                   OR longitude IS NULL OR longitude = '')
              AND location IS NOT NULL
              AND location != ''
        """).fetchall()

    for row in missing_locations:
        latitude, longitude = geocode_location(row["location"])

        if latitude and longitude:
            with db() as con:
                con.execute("""
                    UPDATE complaints
                    SET latitude = ?, longitude = ?
                    WHERE id = ?
                """, (latitude, longitude, row["id"]))

    print("NammaVoice database initialized successfully.")


# =========================================================
# GENERAL HELPERS
# =========================================================

def formalize(text, language):
    return re.sub(r"\s+", " ", (text or "")).strip()


def is_allowed(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )

# =========================================================
# ADMIN LOGIN AND LOGOUT
# =========================================================

def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))

        return view(*args, **kwargs)

    return wrapped_view


@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():

    if session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    if request.method == "POST":

        username = request.form.get("username", "")
        password = request.form.get("password", "")

        correct_username = os.getenv("ADMIN_USERNAME", "")
        correct_password = os.getenv("ADMIN_PASSWORD", "")

        if (
            correct_username
            and correct_password
            and secrets.compare_digest(username, correct_username)
            and secrets.compare_digest(password, correct_password)
        ):
            session.clear()
            session["admin_logged_in"] = True

            flash("Admin login successful.", "success")

            return redirect(url_for("admin"))

        flash("Invalid username or password.", "error")

    return render_template("admin_login.html")


@app.route("/admin_logout")
def admin_logout():

    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("admin_login"))
# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return render_template("index.html")


# =========================================================
# GNANI AI SPEECH-TO-TEXT
# =========================================================

@app.route("/transcribe", methods=["POST"])
def transcribe():
    if not stt_client:
        return jsonify({
            "success": False,
            "error": "Gnani STT is not configured. Check GNANI_API_KEY."
        }), 500

    audio = request.files.get("audio")

    if not audio or not audio.filename:
        return jsonify({
            "success": False,
            "error": "No audio file received."
        }), 400

    input_path = None
    output_path = None

    try:
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

        with tempfile.NamedTemporaryFile(
            suffix=".webm",
            delete=False
        ) as input_file:
            audio.save(input_file.name)
            input_path = input_file.name

        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False
        ) as output_file:
            output_path = output_file.name

        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i", input_path,
                "-ar", "16000",
                "-ac", "1",
                output_path
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        with open(output_path, "rb") as wav_file:
            audio_bytes = wav_file.read()

        result = stt_client.transcribe_bytes(
            audio_bytes,
            filename="recording.wav",
            language_code="indic-auto",
            model="prisma-v3.0",
            format="codemix"
        )

        if not result:
            return jsonify({
                "success": False,
                "error": "Speech recognition returned no result."
            }), 500

        if isinstance(result, dict):
            transcript = (
                result.get("transcript")
                or result.get("text")
                or ""
            )
        else:
            transcript = str(result)

        if not transcript.strip():
            return jsonify({
                "success": False,
                "error": "Could not recognize speech. Please try again."
            }), 400

        detected_language = detect_language(transcript)

        return jsonify({
            "success": True,
            "transcript": transcript,
            "detected_language": detected_language
        })

    except Exception as e:
        print("Transcription error:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        for path in [input_path, output_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


# =========================================================
# COMPLAINT SUBMISSION
# =========================================================

@app.route("/submit", methods=["POST"])
def submit():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    language = request.form.get("language", "Kannada")
    original_text = request.form.get("complaint", "").strip()
    location = request.form.get("location", "").strip()

    latitude = request.form.get("latitude", "").strip()
    longitude = request.form.get("longitude", "").strip()

    if not original_text:
        flash("Please enter or record your complaint.")
        return redirect(url_for("home"))

    detected_language = detect_language(original_text, language)

    department, severity = analyze(original_text)

    complaint_text = formalize(
        original_text,
        detected_language
    )

    if location and (not latitude or not longitude):
        latitude, longitude = geocode_location(location)

    photo_filename = None
    photo = request.files.get("photo")

    if photo and photo.filename and is_allowed(photo.filename):
        extension = photo.filename.rsplit(".", 1)[1].lower()

        photo_filename = secure_filename(
            uuid.uuid4().hex + "." + extension
        )

        photo.save(
            os.path.join(UPLOAD_FOLDER, photo_filename)
        )

    complaint_id = "NV" + uuid.uuid4().hex[:7].upper()
    submitted_at = current_timestamp()

    possible_duplicate = None
    duplicate_of = None
    similarity_score = None

    try:
        with db() as con:

            # Check earlier complaints before inserting.
            possible_duplicate = find_similar_complaint(
                con,
                original_text,
                department,
                location,
                latitude,
                longitude
            )

            if possible_duplicate:
                duplicate_of = possible_duplicate["complaint_id"]
                similarity_score = possible_duplicate["similarity"]

            con.execute("""
                INSERT INTO complaints (
                    complaint_id,
                    name,
                    phone,
                    language,
                    original_text,
                    complaint_text,
                    department,
                    severity,
                    location,
                    latitude,
                    longitude,
                    photo,
                    status,
                    created_at,
                    duplicate_of,
                    similarity_score
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                complaint_id,
                name,
                phone,
                detected_language,
                original_text,
                complaint_text,
                department,
                severity,
                location,
                latitude,
                longitude,
                photo_filename,
                "Submitted",
                submitted_at,
                duplicate_of,
                similarity_score
            ))

            add_status_history(
                con,
                complaint_id,
                "Submitted",
                submitted_at
            )

    except Exception as e:
        print("Complaint submission error:", e)
        flash("Could not submit complaint. Please try again.")
        return redirect(url_for("home"))

    # Voice confirmation using Gnani Timbre TTS.
    audio_url = None

    if tts_client:
        confirmation_messages = {
            "Kannada": f"ನಿಮ್ಮ ದೂರು ಯಶಸ್ವಿಯಾಗಿ ಸಲ್ಲಿಸಲಾಗಿದೆ. ನಿಮ್ಮ ದೂರು ಸಂಖ್ಯೆ {complaint_id}.",
            "English": f"Your complaint has been submitted successfully. Your complaint ID is {complaint_id}.",
            "Hindi": f"आपकी शिकायत सफलतापूर्वक दर्ज की गई है। आपकी शिकायत संख्या {complaint_id} है।",
            "Telugu": f"మీ ఫిర్యాదు విజయవంతంగా నమోదు చేయబడింది. మీ ఫిర్యాదు సంఖ్య {complaint_id}.",
            "Tamil": f"உங்கள் புகார் வெற்றிகரமாக பதிவு செய்யப்பட்டது. உங்கள் புகார் எண் {complaint_id}."
        }

        voices = {
            "Kannada": "Kaveri",
            "English": "Pranav",
            "Hindi": "Pranav",
            "Telugu": "Pranav",
            "Tamil": "Pranav"
        }

        try:
            message = confirmation_messages.get(
                detected_language,
                confirmation_messages["English"]
            )

            voice = voices.get(
                detected_language,
                "Pranav"
            )

            audio_filename = uuid.uuid4().hex + ".wav"
            audio_path = os.path.join(AUDIO_FOLDER, audio_filename)

            tts_client.synthesize(
                text=message,
                voice=voice,
                model="timbre-v2.5",
                output_file=audio_path
            )

            if os.path.exists(audio_path):
                audio_url = url_for(
                    "static",
                    filename="audio/" + audio_filename
                )

        except Exception as e:
            print("Confirmation TTS error:", e)

    return render_template(
        "success.html",
        complaint_id=complaint_id,
        department=department,
        severity=severity,
        audio_url=audio_url,
        possible_duplicate=possible_duplicate,
        duplicate_of=duplicate_of
    )


# =========================================================
# COMPLAINT TRACKING + PROGRESS TIMELINE
# =========================================================

@app.route("/track", methods=["GET", "POST"])
def track():
    complaint = None
    remarks = []
    status_history = []

    if request.method == "POST":
        complaint_id = request.form.get(
            "complaint_id", ""
        ).strip().upper()

        if not complaint_id:
            flash("Please enter your complaint ID.")
        else:
            with db() as con:
                complaint = con.execute("""
                    SELECT *
                    FROM complaints
                    WHERE complaint_id = ?
                """, (complaint_id,)).fetchone()

                if complaint:
                    remarks = con.execute("""
                        SELECT id, complaint_id, remark_text,
                               language, created_at
                        FROM complaint_remarks
                        WHERE complaint_id = ?
                        ORDER BY id ASC
                    """, (complaint_id,)).fetchall()

                    status_history = con.execute("""
                        SELECT status, created_at
                        FROM complaint_status_history
                        WHERE complaint_id = ?
                        ORDER BY id ASC
                    """, (complaint_id,)).fetchall()

                else:
                    flash("Complaint ID not found. Please check and try again.")

    return render_template(
        "track.html",
        complaint=complaint,
        remarks=remarks,
        status_history=status_history
    )


# =========================================================
# GNANI AI VOICE STATUS
# =========================================================

@app.route("/speak_status", methods=["POST"])
def speak_status():
    if not tts_client:
        return jsonify({
            "success": False,
            "error": "Gnani TTS is not configured."
        }), 500

    complaint_id = request.form.get(
        "complaint_id", ""
    ).strip().upper()

    if not complaint_id:
        return jsonify({
            "success": False,
            "error": "Complaint ID is required."
        }), 400

    with db() as con:
        complaint = con.execute("""
            SELECT complaint_id, status, language
            FROM complaints
            WHERE complaint_id = ?
        """, (complaint_id,)).fetchone()

    if not complaint:
        return jsonify({
            "success": False,
            "error": "Complaint not found."
        }), 404

    status = complaint["status"] or "Submitted"
    language = complaint["language"] or "English"

    messages = {
        "Kannada": {
            "Submitted": "ನಿಮ್ಮ ದೂರು ಸಲ್ಲಿಸಲಾಗಿದೆ.",
            "Under Review": "ನಿಮ್ಮ ದೂರನ್ನು ಪರಿಶೀಲಿಸಲಾಗುತ್ತಿದೆ.",
            "In Progress": "ನಿಮ್ಮ ದೂರಿನ ಮೇಲೆ ಕೆಲಸ ನಡೆಯುತ್ತಿದೆ.",
            "Resolved": "ನಿಮ್ಮ ದೂರು ಪರಿಹರಿಸಲಾಗಿದೆ."
        },
        "English": {
            "Submitted": "Your complaint has been submitted.",
            "Under Review": "Your complaint is under review.",
            "In Progress": "Work is in progress on your complaint.",
            "Resolved": "Your complaint has been resolved."
        },
        "Hindi": {
            "Submitted": "आपकी शिकायत दर्ज कर ली गई है।",
            "Under Review": "आपकी शिकायत की समीक्षा की जा रही है।",
            "In Progress": "आपकी शिकायत पर काम चल रहा है।",
            "Resolved": "आपकी शिकायत का समाधान कर दिया गया है।"
        },
        "Telugu": {
            "Submitted": "మీ ఫిర్యాదు నమోదు చేయబడింది.",
            "Under Review": "మీ ఫిర్యాదు పరిశీలనలో ఉంది.",
            "In Progress": "మీ ఫిర్యాదుపై పని జరుగుతోంది.",
            "Resolved": "మీ ఫిర్యాదు పరిష్కరించబడింది."
        },
        "Tamil": {
            "Submitted": "உங்கள் புகார் பதிவு செய்யப்பட்டுள்ளது.",
            "Under Review": "உங்கள் புகார் பரிசீலனையில் உள்ளது.",
            "In Progress": "உங்கள் புகாருக்கான பணி நடைபெற்று வருகிறது.",
            "Resolved": "உங்கள் புகார் தீர்க்கப்பட்டுள்ளது."
        }
    }

    voices = {
    "Kannada": "Kaveri",
    "English": "Pranav",
    "Hindi": "Pranav",
    "Telugu": "Pranav",
    "Tamil": "Pranav"

    }

    message = messages.get(
        language,
        messages["English"]
    ).get(
        status,
        messages["English"]["Submitted"]
    )

    voice = voices.get(language,
    "Pranav"
    
)

    try:
        audio_filename = uuid.uuid4().hex + ".wav"
        audio_path = os.path.join(AUDIO_FOLDER, audio_filename)

        tts_client.synthesize(
            text=message,
            voice=voice,
            model="timbre-v2.5",
            output_file=audio_path
        )

        audio_url = url_for(
            "static",
            filename="audio/" + audio_filename
        )

        return jsonify({
            "success": True,
            "message": message,
            "audio_url": audio_url
        })

    except Exception as e:
        print("Status TTS error:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================================================
# ADMIN: SAVE REMARK
# =========================================================

@app.route("/save_remark", methods=["POST"])
@admin_required
def save_remark():
    complaint_id = request.form.get(
        "complaint_id", ""
    ).strip().upper()

    remark_text = request.form.get(
        "remark_text", ""
    ).strip()

    if not complaint_id or not remark_text:
        flash("Complaint ID and remark are required.")
        return redirect(url_for("admin"))

    if len(remark_text) > 3000:
        flash("Remark is too long. Maximum 3000 characters.")
        return redirect(url_for("admin"))

    with db() as con:
        complaint = con.execute("""
            SELECT language
            FROM complaints
            WHERE complaint_id = ?
        """, (complaint_id,)).fetchone()

        if not complaint:
            flash("Complaint not found.")
            return redirect(url_for("admin"))

        language = detect_language(
            remark_text,
            complaint["language"] or "English"
        )

        con.execute("""
            INSERT INTO complaint_remarks (
                complaint_id,
                remark_text,
                language,
                created_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            complaint_id,
            remark_text,
            language,
            current_timestamp()
        ))

    flash("Remark saved successfully.")
    return redirect(url_for("admin"))


# =========================================================
# GNANI AI: SPEAK ADMIN REMARK
# =========================================================


@app.route("/speak_remark", methods=["POST"])
@admin_required
def speak_remark():
    if not tts_client:
        return jsonify({
            "success": False,
            "error": "Gnani TTS is not configured."
        }), 500

    remark_id = request.form.get("remark_id", "").strip()

    if not remark_id.isdigit():
        return jsonify({
            "success": False,
            "error": "Invalid remark ID."
        }), 400

    with db() as con:
        remark = con.execute("""
            SELECT remark_text, language
            FROM complaint_remarks
            WHERE id = ?
        """, (remark_id,)).fetchone()

    if not remark:
        return jsonify({
            "success": False,
            "error": "Remark not found."
        }), 404

    language = (remark["language"] or "English").strip()

    voices = {
        "Kannada": "Kaveri",
        "English": "Pranav",
        "Hindi": "Pranav",
        "Telugu": "Pranav",
        "Tamil": "Pranav"
    }

    voice = voices.get(language, "Pranav")

    try:
        audio_filename = uuid.uuid4().hex + ".wav"
        audio_path = os.path.join(AUDIO_FOLDER, audio_filename)

        tts_client.synthesize(
            text=remark["remark_text"],
            voice=voice,
            model="timbre-v2.5",
            output_file=audio_path
        )

        return jsonify({
            "success": True,
            "audio_url": url_for(
                "static",
                filename="audio/" + audio_filename
            )
        })

    except Exception as e:
        print("Remark TTS error:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500



# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
@admin_required
def admin():
    with db() as con:
        complaints = con.execute("""
            SELECT *
            FROM complaints
            ORDER BY id DESC
        """).fetchall()

        total = con.execute("""
            SELECT COUNT(*) AS count
            FROM complaints
        """).fetchone()["count"]

        pending = con.execute("""
            SELECT COUNT(*) AS count
            FROM complaints
            WHERE status IN ('Submitted', 'Under Review')
        """).fetchone()["count"]

        progress = con.execute("""
            SELECT COUNT(*) AS count
            FROM complaints
            WHERE status = 'In Progress'
        """).fetchone()["count"]

        resolved = con.execute("""
            SELECT COUNT(*) AS count
            FROM complaints
            WHERE status = 'Resolved'
        """).fetchone()["count"]

        remark_rows = con.execute("""
            SELECT *
            FROM complaint_remarks
            ORDER BY id DESC
        """).fetchall()

    counts = {
        "total": total,
        "pending": pending,
        "progress": progress,
        "resolved": resolved
    }

    remarks_by_complaint = {}

    for remark in remark_rows:
        cid = remark["complaint_id"]

        if cid not in remarks_by_complaint:
            remarks_by_complaint[cid] = []

        remarks_by_complaint[cid].append(remark)

    return render_template(
        "admin.html",
        complaints=complaints,
        counts=counts,
        remarks_by_complaint=remarks_by_complaint
    )


# =========================================================
# ADMIN: UPDATE COMPLAINT STATUS
# =========================================================

@app.route("/update_status", methods=["POST"])
@admin_required
def update_status():
    complaint_id = request.form.get(
        "complaint_id", ""
    ).strip().upper()

    new_status = request.form.get(
        "status", ""
    ).strip()

    allowed_statuses = [
        "Submitted",
        "Under Review",
        "In Progress",
        "Resolved"
    ]

    if new_status not in allowed_statuses:
        flash("Invalid complaint status.")
        return redirect(url_for("admin"))

    if not complaint_id:
        flash("Complaint ID is required.")
        return redirect(url_for("admin"))

    with db() as con:
        complaint = con.execute("""
            SELECT status
            FROM complaints
            WHERE complaint_id = ?
        """, (complaint_id,)).fetchone()

        if not complaint:
            flash("Complaint not found.")
            return redirect(url_for("admin"))

        old_status = complaint["status"] or "Submitted"

        if old_status == new_status:
            flash("The complaint already has this status.")
        else:
            con.execute("""
                UPDATE complaints
                SET status = ?
                WHERE complaint_id = ?
            """, (new_status, complaint_id))

            # Add a timeline event only when status changes.
            add_status_history(
                con,
                complaint_id,
                new_status,
                current_timestamp()
            )

            flash("Complaint status updated successfully.")

    return redirect(url_for("admin"))


# =========================================================
# COMPLAINT API FOR MAP / ANALYTICS
# =========================================================

@app.route("/api/complaints")
@admin_required
def api_complaints():
    with db() as con:
        rows = con.execute("""
            SELECT
                complaint_id,
                department,
                severity,
                language,
                location,
                status,
                latitude,
                longitude
            FROM complaints
            ORDER BY rowid DESC
        """).fetchall()

    return jsonify([
        dict(row) for row in rows
    ])


@app.route("/download_csv")
@admin_required
def download_csv():

    output = io.StringIO()
    writer = csv.writer(output)

    # CSV column headings
    writer.writerow([
        "Complaint ID",
        "Name",
        "Phone",
        "Language",
        "Complaint",
        "Department",
        "Severity",
        "Location",
        "Status",
        "Created At"
    ])

    # Fetch complaint records
    with db() as con:
        complaints = con.execute("""
            SELECT
                complaint_id,
                name,
                phone,
                language,
                complaint_text,
                department,
                severity,
                location,
                status,
                created_at
            FROM complaints
            ORDER BY id DESC
        """).fetchall()

    # Add complaint records to CSV
    for complaint in complaints:
        writer.writerow([
            complaint["complaint_id"],
            complaint["name"],
            complaint["phone"],
            complaint["language"],
            complaint["complaint_text"],
            complaint["department"],
            complaint["severity"],
            complaint["location"],
            complaint["status"],
            complaint["created_at"]
        ])

    # Create downloadable response
    csv_data = "\ufeff" + output.getvalue()
    output.close()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=nammavoice_complaints.csv"
        }
    )

@app.route("/download_pdf")
@admin_required
def download_pdf():

    buffer = io.BytesIO()

    # Create PDF document
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "NammaTitle",
        parent=styles["Title"],
        fontName="Nirmala",
        fontSize=18,
        leading=22,
        shaping=1
    )

    normal_style = ParagraphStyle(
        "NammaNormal",
        parent=styles["Normal"],
        fontName="Nirmala",
        fontSize=9,
        leading=12,
        shaping=1
    )

    cell_style = ParagraphStyle(
        "CellStyle",
        parent=normal_style,
        fontName="Nirmala",
        fontSize=9,
        leading=12,
        wordWrap="CJK",
        shaping=1
    )

    header_style = ParagraphStyle(
        "HeaderStyle",
        parent=normal_style,
        fontName="Nirmala",
        fontSize=7,
        leading=9,
        textColor=colors.white,
        shaping=1
    )
    # Fetch complaints
    with db() as con:
        complaints = con.execute("""
            SELECT
                complaint_id,
                name,
                phone,
                language,
                complaint_text,
                department,
                severity,
                location,
                status,
                created_at
            FROM complaints
            ORDER BY id DESC
        """).fetchall()

    # Build PDF content
    elements = []

    elements.append(
        Paragraph("NAMMAVOICE", title_style)
    )

    elements.append(
        Paragraph(
            "Citizen Grievance Management - Complaint Report",
            normal_style
        )
    )

    elements.append(Spacer(1, 5 * mm))

    elements.append(
        Paragraph(
            f"<b>Total Complaints:</b> {len(complaints)}",
            normal_style
        )
    )

    elements.append(Spacer(1, 5 * mm))

    # Table headings
    table_data = [[
        Paragraph("Complaint ID", header_style),
        Paragraph("Name", header_style),
        Paragraph("Phone", header_style),
        Paragraph("Language", header_style),
        Paragraph("Complaint", header_style),
        Paragraph("Department", header_style),
        Paragraph("Priority", header_style),
        Paragraph("Location", header_style),
        Paragraph("Status", header_style),
        Paragraph("Created At", header_style)
    ]]

    # Add complaint records
    for complaint in complaints:

        row = [
            complaint["complaint_id"],
            complaint["name"],
            complaint["phone"],
            complaint["language"],
            complaint["complaint_text"],
            complaint["department"],
            complaint["severity"],
            complaint["location"],
            complaint["status"],
            complaint["created_at"]
        ]

        table_data.append([
            Paragraph(
                escape(str(value or "")),
                cell_style
            )
            for value in row
        ])

    if not complaints:
        elements.append(
            Paragraph("No complaints available.", normal_style)
        )
    else:
        # Create formatted table
        report_table = Table(
            table_data,
            colWidths=[
                22 * mm,
                18 * mm,
                18 * mm,
                18 * mm,
                65 * mm,
                25 * mm,
                18 * mm,
                28 * mm,
                22 * mm,
                30 * mm
            ],
            repeatRows=1
        )

        report_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#172554")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                colors.white,
                colors.HexColor("#eff6ff")
            ])
        ]))

        elements.append(report_table)

    # Generate PDF
    pdf.build(elements)

    buffer.seek(0)

    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
                "attachment; filename=nammavoice_complaints.pdf"
        }
    )

# =========================================================
# APPLICATION STARTUP
# =========================================================

if __name__ == "__main__":
    init_db()

    print("")
    print("======================================")
    print("       NAMMAVOICE IS STARTING")
    print("======================================")
    print("Open this address in your browser:")
    print("http://127.0.0.1:5000")
    print("======================================")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
