# NAMMAVOICE – MULTILINGUAL AI CIVIC GRIEVANCE PLATFORM

**Your voice. Your issue. Our attention.**

## Project Overview

NammaVoice is a multilingual AI-powered civic grievance platform designed to make local complaint registration more accessible. Citizens can submit complaints using their preferred language through voice or text.

The platform uses Gnani AI speech technologies to convert spoken complaints into text and provide multilingual voice confirmations. It organizes complaints, suggests the responsible department, detects duplicate complaints, and allows administrators to review and manage complaint progress.

## Gnani AI Integration

- **Gnani Prisma STT:** Converts citizens' recorded speech into text and supports multilingual speech recognition.
- **Gnani Timbre TTS:** Generates spoken complaint confirmations and multilingual voice responses.

## Supported Languages

- Kannada
- English
- Hindi
- Telugu
- Tamil

## Main Features

### Citizen Features
- Voice-based and text-based complaint registration.
- Multilingual speech recognition.
- Automatic complaint ID generation.
- Department classification.
- Complaint severity assessment.
- AI-based duplicate complaint detection.
- Optional photo evidence and GPS location.
- Complaint tracking using complaint ID.
- Multilingual voice confirmation and status updates.

### Administrator Features
- Secure administrator login.
- Complaint monitoring and management dashboard.
- Department, severity and status filters.
- Complaint details and photo evidence preview.
- Location-based complaint mapping.
- Complaint status updates.
- Voice-based administrative remarks.
- Multilingual spoken complaint remarks.
- Complaint analytics and charts.

## Technologies Used

- Python
- Flask
- HTML, CSS and JavaScript
- SQLite
- Gnani AI Prisma STT
- Gnani AI Timbre TTS
- Leaflet Maps
- Chart.js

## Installation and Setup

1. Install Python 3.10 or newer.
2. Open a terminal in the NammaVoice project folder.
3. Create a virtual environment:

   `py -m venv venv`

4. Activate it on Windows:

   `venv\Scripts\activate`

5. Install dependencies:

   `pip install -r requirements.txt`

6. Configure Gnani API credentials locally using a `.env` file. Never upload API keys or secrets to GitHub.

7. Start the application:

   `python app.py`

8. Open Chrome and visit:

   `http://127.0.0.1:5000`

## Application Pages

- `/` – Citizen complaint registration.
- `/track` – Complaint tracking.
- `/admin` – Administrator dashboard (login protected).

## Transparency and Limitations

- NammaVoice records and manages citizen complaints for administrator review.
- It does not automatically forward complaints to government departments or government portals.
- Complaint classification and severity assessment assist administrative review; they do not replace official government decisions.
- Speech recognition accuracy depends on audio quality and language support.
- The platform should be demonstrated using sample data rather than real citizens' private information.

## Project Purpose

NammaVoice aims to reduce language and accessibility barriers in civic complaint registration by allowing citizens to communicate local issues naturally through voice or text.

It combines multilingual AI speech technologies with complaint management and administrative tools to support more accessible civic grievance handling.
