
import sqlite3
import os
import uuid
import re
import subprocess
import tempfile
import imageio_ffmpeg

from datetime import datetime
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from gnani.stt import GnaniSTTClient
from gnani.tts import GnaniTTSClient


# =====================================================
# CONFIGURATION
# =====================================================

load_dotenv()

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
DB = "nammavoice.db"

API_KEY = os.getenv("GNANI_API_KEY")

stt_client = GnaniSTTClient(api_key=API_KEY) if API_KEY else None
tts_client = GnaniTTSClient(api_key=API_KEY) if API_KEY else None


# =====================================================
# AUTOMATIC LANGUAGE DETECTION
# =====================================================

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

    if counts[detected] > 0:
        return detected

    return fallback


# =====================================================
# MULTILINGUAL DEPARTMENT CLASSIFICATION
# =====================================================

DEPARTMENTS = {

    "Water Supply": [
        "water", "drinking water", "water supply", "no water",
        "tap water", "pipeline",
        "ನೀರು", "ಕುಡಿಯುವ ನೀರು", "ನೀರಿನ ಸಮಸ್ಯೆ",
        "ನೀರಿನ ಸರಬರಾಜು", "ನೀರು ಬರುತ್ತಿಲ್ಲ", "ಕೊಳವೆ",
        "पानी", "पीने का पानी", "पानी की समस्या",
        "पानी नहीं आ रहा", "जल आपूर्ति", "नल का पानी",
        "నీరు", "తాగునీరు", "నీటి సమస్య",
        "నీళ్లు రావడం లేదు", "నీటి సరఫరా",
        "தண்ணீர்", "குடிநீர்", "தண்ணீர் பிரச்சனை",
        "தண்ணீர் வரவில்லை", "நீர் வழங்கல்"
    ],

    "Road Development / PWD": [
        "road", "roads", "pothole", "damaged road",
        "bad road", "broken road", "road repair",
        "street", "mud road",
        "ರಸ್ತೆ", "ರೋಡ್", "ರಸ್ತೆಯಿಲ್ಲ", "ಗುಂಡಿ",
        "ರಸ್ತೆ ಹಾಳಾಗಿದೆ", "ರಸ್ತೆ ಸರಿಪಡಿಸಿ",
        "ಮಣ್ಣಿನ ರಸ್ತೆ", "ರಸ್ತೆ ನಿರ್ಮಾಣ",
        "सड़क", "सड़क", "रास्ता", "सड़क खराब",
        "सड़क अच्छी नहीं है", "सड़क अच्छा नहीं है",
        "सड़क की मरम्मत", "गड्ढे", "टूटी सड़क",
        "खराब सड़क", "सड़क बनवाएं",
        "రోడ్డు", "రహదారి", "రోడ్డు బాగాలేదు",
        "రోడ్డు పాడైంది", "గుంతలు", "రోడ్డు మరమ్మత్తు",
        "దెబ్బతిన్న రోడ్డు",
        "சாலை", "ரோடு", "சாலை சரியில்லை",
        "சாலை பழுதடைந்துள்ளது", "சாலையில் பள்ளம்",
        "சாலை சீரமைப்பு", "உடைந்த சாலை"
    ],

    "Sanitation": [
        "garbage", "trash", "waste", "dustbin",
        "dirty area", "cleaning", "sanitation",
        "ಕಸ", "ತ್ಯಾಜ್ಯ", "ಕಸ ವಿಲೇವಾರಿ",
        "ಸ್ವಚ್ಛತೆ", "ಕಸ ಸಂಗ್ರಹ",
        "कचरा", "कूड़ा", "गंदगी", "सफाई",
        "कचरा नहीं उठाया", "कूड़ेदान", "कचरा संग्रह",
        "చెత్త", "వ్యర్థాలు", "పరిశుభ్రత",
        "చెత్త సేకరణ", "చెత్త తొలగించండి",
        "குப்பை", "கழிவு", "சுத்தம்",
        "குப்பை அகற்றுதல்", "குப்பை சேகரிப்பு"
    ],

    "Drainage": [
        "drain", "drainage", "sewage", "blocked drain",
        "overflow", "sewer", "wastewater",
        "ಚರಂಡಿ", "ಒಳಚರಂಡಿ", "ಕೊಳಚೆ ನೀರು",
        "ಚರಂಡಿ ನೀರು", "ಚರಂಡಿ ಕಟ್ಟಿಕೊಂಡಿದೆ",
        "नाली", "नाला", "नाली जाम",
        "गंदा पानी", "सीवेज", "नाली का पानी",
        "नाली ओवरफ्लो",
        "కాలువ", "మురుగు నీరు", "డ్రైనేజీ",
        "కాలువ మూసుకుపోయింది", "మురుగునీరు",
        "சாக்கடை", "கழிவுநீர்", "வடிகால்",
        "சாக்கடை அடைப்பு", "கழிவுநீர் பிரச்சனை"
    ],

    "Electricity / Streetlights": [
        "electricity", "power cut", "current",
        "streetlight", "street light", "no power",
        "electric pole", "power supply",
        "ವಿದ್ಯುತ್", "ಬೀದಿ ದೀಪ", "ಲೈಟ್ ಇಲ್ಲ",
        "ವಿದ್ಯುತ್ ಕಡಿತ", "ಕರೆಂಟ್ ಇಲ್ಲ",
        "ವಿದ್ಯುತ್ ಕಂಬ",
        "बिजली", "बिजली कटौती", "बिजली नहीं है",
        "स्ट्रीट लाइट", "बत्ती नहीं", "बिजली की समस्या",
        "बिजली का खंभा",
        "విద్యుత్", "కరెంటు", "కరెంట్ లేదు",
        "వీధి దీపాలు", "విద్యుత్ సమస్య",
        "விளக்கு", "மின்சாரம்", "மின்தடை",
        "மின்சாரம் இல்லை", "தெருவிளக்கு",
        "மின்சார பிரச்சனை", "தெரு விளக்கு எரியவில்லை"
    ]
}


# =====================================================
# IMPROVED COMPLAINT ANALYSIS
# =====================================================

def analyze(text):

    t = text.lower().strip()

    # Department detection using keyword scores
    department_scores = {}

    for dept, words in DEPARTMENTS.items():

        score = 0

        for word in words:

            if word.lower() in t:
                score += 1

        department_scores[dept] = score

    if department_scores and max(department_scores.values()) > 0:

        department = max(
            department_scores,
            key=department_scores.get
        )

    else:

        department = "General Public Grievance"

    # Emergency keywords
    urgent_words = [
        "emergency", "danger", "accident",
        "life threatening", "fire", "electric shock",
        "ಅಪಾಯ", "ತುರ್ತು", "ಅಪಘಾತ",
        "आपातकाल", "खतरा", "दुर्घटना",
        "ప్రమాదం", "అత్యవసరం", "ప్రమాదకరం",
        "ஆபத்து", "அவசரம்", "விபத்து"
    ]

    # Serious problem keywords
    high_words = [
        "not working", "overflow", "no water",
        "three days", "3 days", "broken",
        "damaged", "blocked", "not available",
        "ಮೂರು ದಿನ", "ಬರುತ್ತಿಲ್ಲ", "ಕೆಲಸ ಮಾಡುತ್ತಿಲ್ಲ",
        "तीन दिन", "काम नहीं कर रहा", "नहीं आ रहा",
        "మూడు రోజులు", "పని చేయడం లేదు", "రావడం లేదు",
        "மூன்று நாட்கள்", "வேலை செய்யவில்லை", "வரவில்லை"
    ]

    # Repeated problem keywords
    medium_words = [
        "every day", "daily", "many days",
        "often", "repeatedly",
        "ಪ್ರತಿದಿನ", "ಹಲವು ದಿನ",
        "रोज", "हर दिन",
        "ప్రతిరోజు", "రోజూ",
        "தினமும்", "பல நாட்கள்"
    ]

    # Priority classification
    if any(word in t for word in urgent_words):

        severity = "Urgent"

    elif any(word in t for word in high_words):

        severity = "High"

    elif any(word in t for word in medium_words):

        severity = "Medium"

    elif t:

        severity = "Medium"

    else:

        severity = "Low"

    return department, severity


# =====================================================
# DATABASE
# =====================================================

def db():

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    return con


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

        rows = con.execute("""
            SELECT complaint_id, original_text, language
            FROM complaints
        """).fetchall()

        for row in rows:

            correct_language = detect_language(
                row["original_text"],
                row["language"] or "Kannada"
            )

            if correct_language != row["language"]:

                con.execute("""
                    UPDATE complaints
                    SET language = ?
                    WHERE complaint_id = ?
                """, (
                    correct_language,
                    row["complaint_id"]
                ))


# =====================================================
# OTHER FUNCTIONS
# =====================================================

def formalize(text, language):

    return re.sub(r'\s+', ' ', text).strip()


def is_allowed(filename):

    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# =====================================================
# HOME PAGE
# =====================================================

@app.route("/")
def home():

    return render_template("index.html")


# =====================================================
# GNANI PRISMA - SPEECH TO TEXT
# =====================================================

@app.route("/transcribe", methods=["POST"])
def transcribe():

    if not stt_client:

        return jsonify({
            "error": "Gnani API key is not configured."
        }), 500

    audio = request.files.get("audio")

    if not audio or not audio.filename:

        return jsonify({
            "error": "No audio recording received."
        }), 400

    try:

        audio_bytes = audio.read()

        if not audio_bytes:

            return jsonify({
                "error": "The audio recording is empty."
            }), 400

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

        with tempfile.TemporaryDirectory() as temp_dir:

            input_path = os.path.join(temp_dir, "recording.webm")
            output_path = os.path.join(temp_dir, "recording.wav")

            with open(input_path, "wb") as f:
                f.write(audio_bytes)

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
                capture_output=True,
                text=True
            )

            with open(output_path, "rb") as f:
                wav_bytes = f.read()

            result = stt_client.transcribe_bytes(
                wav_bytes,
                filename="recording.wav",
                language_code="indic-auto",
                model="prisma-v3.0",
                format="codemix"
            )

        if not result.get("success", True):

            return jsonify({
                "error": "Speech recognition failed."
            }), 502

        transcript = result.get("transcript", "")

        detected_language = detect_language(
            transcript,
            "Kannada"
        )

        return jsonify({
            "transcript": transcript,
            "detected_language": detected_language
        })

    except Exception:

        app.logger.exception(
            "Audio conversion or transcription failed"
        )

        return jsonify({
            "error": "Could not process audio. Please try again."
        }), 500


# =====================================================
# REGISTER COMPLAINT
# =====================================================

@app.route("/submit", methods=["POST"])
def submit():

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()

    selected_language = request.form.get(
        "language", "Kannada"
    )

    original = request.form.get(
        "complaint", ""
    ).strip()

    location = request.form.get("location", "").strip()
    lat = request.form.get("latitude", "").strip()
    lon = request.form.get("longitude", "").strip()

    if not original:

        flash("Please speak or type your complaint.", "error")

        return redirect(url_for("home"))

    language = detect_language(
        original,
        selected_language
    )

    department, severity = analyze(original)

    complaint_text = formalize(original, language)

    # Photo upload
    photo_path = None

    photo = request.files.get("photo")

    if photo and photo.filename and is_allowed(photo.filename):

        ext = photo.filename.rsplit(".", 1)[1].lower()

        filename = secure_filename(
            f"{uuid.uuid4().hex}.{ext}"
        )

        os.makedirs(
            app.config["UPLOAD_FOLDER"],
            exist_ok=True
        )

        photo.save(
            os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )
        )

        photo_path = filename

    # Generate complaint ID
    complaint_id = "NV" + uuid.uuid4().hex[:7].upper()

    with db() as con:

        con.execute("""
        INSERT INTO complaints
        (complaint_id, name, phone, language, original_text,
         complaint_text, department, severity, location,
         latitude, longitude, photo, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            complaint_id,
            name,
            phone,
            language,
            original,
            complaint_text,
            department,
            severity,
            location,
            lat,
            lon,
            photo_path,
            datetime.now().strftime("%d-%m-%Y %I:%M %p")
        ))

    # =================================================
    # GNANI TIMBRE - VOICE CONFIRMATION
    # =================================================

    audio_url = None

    if tts_client:

        try:

            messages = {

                "Kannada": (
                    f"ನಮಸ್ಕಾರ. ನಿಮ್ಮ ದೂರು ಯಶಸ್ವಿಯಾಗಿ ದಾಖಲಿಸಲಾಗಿದೆ. "
                    f"ನಿಮ್ಮ ದೂರು ಸಂಖ್ಯೆ {complaint_id}."
                ),

                "English": (
                    f"Hello. Your complaint has been successfully "
                    f"registered. Your complaint ID is {complaint_id}."
                ),

                "Hindi": (
                    f"नमस्ते। आपकी शिकायत सफलतापूर्वक दर्ज कर ली गई है। "
                    f"आपकी शिकायत संख्या {complaint_id} है।"
                ),

                "Telugu": (
                    f"నమస్కారం. మీ ఫిర్యాదు విజయవంతంగా నమోదు చేయబడింది. "
                    f"మీ ఫిర్యాదు సంఖ్య {complaint_id}."
                ),

                "Tamil": (
                    f"வணக்கம். உங்கள் புகார் வெற்றிகரமாக பதிவு செய்யப்பட்டது. "
                    f"உங்கள் புகார் எண் {complaint_id}."
                )
            }

            voices = {

                "Kannada": ("kn-IN", "Kaveri"),
                "English": ("en-IN", "Pranav"),
                "Hindi": ("hi-IN", "Pranav"),
                "Telugu": ("te-IN", "Pranav"),
                "Tamil": ("ta-IN", "Pranav")
            }

            language_code, voice = voices.get(
                language,
                ("kn-IN", "Kaveri")
            )

            message = messages.get(
                language,
                messages["Kannada"]
            )

            audio_folder = os.path.join(
                "static", "audio"
            )

            os.makedirs(
                audio_folder,
                exist_ok=True
            )

            audio_filename = f"{uuid.uuid4().hex}.wav"

            audio_path = os.path.join(
                audio_folder,
                audio_filename
            )

            tts_client.synthesize(
                message,
                voice=voice,
                model="timbre-v2.5",
                language=language_code,
                output_file=audio_path
            )

            audio_url = url_for(
                "static",
                filename=f"audio/{audio_filename}"
            )

        except Exception:

            app.logger.exception(
                "Gnani voice confirmation failed"
            )

    return render_template(
        "success.html",
        complaint_id=complaint_id,
        department=department,
        severity=severity,
        audio_url=audio_url
    )


# =====================================================
# TRACK COMPLAINT
# =====================================================

@app.route("/track", methods=["GET", "POST"])
def track():

    complaint = None

    if request.method == "POST":

        cid = request.form.get(
            "complaint_id", ""
        ).strip().upper()

        with db() as con:

            complaint = con.execute(
                """
                SELECT * FROM complaints
                WHERE complaint_id = ?
                """,
                (cid,)
            ).fetchone()

        if complaint is None:

            flash(
                "Complaint ID not found. Check the ID and try again.",
                "error"
            )

    return render_template(
        "track.html",
        complaint=complaint
    )


# =====================================================
# ADMIN DASHBOARD
# =====================================================

@app.route("/admin")
def admin():

    with db() as con:

        rows = con.execute(
            """
            SELECT * FROM complaints
            ORDER BY id DESC
            """
        ).fetchall()

        counts = {

            "total": con.execute(
                "SELECT COUNT(*) FROM complaints"
            ).fetchone()[0],

            "pending": con.execute(
                """
                SELECT COUNT(*) FROM complaints
                WHERE status IN ('Submitted', 'Under Review')
                """
            ).fetchone()[0],

            "progress": con.execute(
                """
                SELECT COUNT(*) FROM complaints
                WHERE status = 'In Progress'
                """
            ).fetchone()[0],

            "resolved": con.execute(
                """
                SELECT COUNT(*) FROM complaints
                WHERE status = 'Resolved'
                """
            ).fetchone()[0]
        }

    return render_template(
        "admin.html",
        complaints=rows,
        counts=counts
    )


# =====================================================
# UPDATE COMPLAINT STATUS
# =====================================================

@app.route("/update_status", methods=["POST"])
def update_status():

    cid = request.form.get(
        "complaint_id", ""
    ).strip().upper()

    status = request.form.get("status")

    allowed = {
        "Submitted",
        "Under Review",
        "In Progress",
        "Resolved"
    }

    if status not in allowed:

        flash("Invalid status.", "error")

    else:

        with db() as con:

            cursor = con.execute(
                """
                UPDATE complaints
                SET status = ?
                WHERE complaint_id = ?
                """,
                (status, cid)
            )

            if cursor.rowcount == 0:

                flash(
                    f"Complaint {cid} was not found.",
                    "error"
                )

            else:

                flash(
                    f"Status updated for {cid}.",
                    "success"
                )

    return redirect(url_for("admin"))


# =====================================================
# COMPLAINTS API
# =====================================================

@app.route("/api/complaints")
def api_complaints():

    with db() as con:

        rows = con.execute("""
        SELECT complaint_id, department, severity, language,
               location, status, latitude, longitude
        FROM complaints
        """).fetchall()

    return jsonify([
        dict(row) for row in rows
    ])


# =====================================================
# RUN APPLICATION
# =====================================================

if __name__ == "__main__":

    init_db()

    app.run(debug=True)
