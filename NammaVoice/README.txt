# NAMMAVOICE – MULTILINGUAL AI CIVIC COMPLAINT ASSISTANT

## Project Overview

NammaVoice is a multilingual voice-based civic complaint registration prototype. It helps citizens submit local complaints using their preferred language.

The application converts recorded speech into text, registers complaints, suggests the responsible department and priority, and provides a complaint ID with voice confirmation.

## Gnani AI Integration

- Gnani Prisma STT – Converts recorded voice complaints into text.
- Gnani Timbre TTS – Generates spoken voice confirmations for registered complaints.

## Supported Languages

- Kannada
- English
- Hindi
- Telugu
- Tamil

## Main Features

- Voice-based complaint registration.
- Multilingual speech-to-text.
- Voice confirmation using text-to-speech.
- Complaint classification and department suggestion.
- Rule-based priority suggestion.
- Automatic complaint ID generation.
- SQLite database for complaint storage.
- Optional photo and GPS location attachment.
- Complaint tracking using complaint ID.
- Admin dashboard for viewing complaints and updating status.

## Technologies Used

- Python
- Flask
- HTML, CSS and JavaScript
- SQLite
- Gnani AI Prisma STT
- Gnani AI Timbre TTS

## Installation and Setup

1. Install Python 3.10 or newer.
2. Open a terminal in the NammaVoice project folder.
3. Create a virtual environment:

   `py -m venv venv`

4. Activate it on Windows:

   `venv\Scripts\activate`

5. Install dependencies:

   `pip install -r requirements.txt`

6. Configure your Gnani API credentials locally. Never upload API keys or `.env` files to GitHub.

7. Start the application:

   `python app.py`

8. Open Chrome and visit:

   `http://127.0.0.1:5000`

## Application Pages

- `/` – Citizen complaint registration.
- `/track` – Track complaints using their complaint ID.
- `/admin` – Admin dashboard and complaint status updates.

## Current Limitations

- This is a student prototype and is not connected to any government portal.
- Speech recognition accuracy depends on audio quality and language support.
- Complaint classification and priority suggestions use rule-based logic.
- Reliable AI-based complaint rewriting and translation are not yet fully implemented.
- The admin dashboard does not currently have authentication.
- Do not use real citizens' personal information in a public demonstration.

## Project Purpose

NammaVoice aims to make civic complaint registration easier and more accessible through multilingual voice interaction, especially for people who prefer speaking rather than typing.