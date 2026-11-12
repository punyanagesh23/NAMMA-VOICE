NAMMAVOICE - STUDENT PROTOTYPE

1. Install Python 3.10 or newer.
2. Open a terminal in this NammaVoice folder.
3. Create and activate a virtual environment (recommended):
   Windows: py -m venv venv
   Windows: venv\Scripts\activate
4. Install packages:
   pip install -r requirements.txt
5. Start:
   python app.py
6. Open http://127.0.0.1:5000 in Chrome.

Pages:
- / : citizen complaint registration
- /track : track a complaint using its NV... ID
- /admin : admin dashboard and status updates

Included:
- Voice input using browser Web Speech API (availability/language accuracy depends on browser/device)
- Kannada/English/Hindi/Telugu/Tamil language selector
- Complaint classification and rule-based priority suggestion
- SQLite complaint storage
- Optional photo and GPS coordinates
- Complaint tracking and admin status updates

Important limitations:
- This is a local student demo, not connected to any government portal.
- Speech recognition support depends on browser, operating system and internet.
- AI classification is a simple keyword/rule-based demo, not a trained AI model.
- The formal complaint field preserves the user's wording; it does not yet perform reliable AI rewriting or translation.
- Admin page has no login. Add authentication before any real deployment.
- Do not collect real citizens' personal data in a public demo.
