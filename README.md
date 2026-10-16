# 🎓 CampusSaathi: Multilingual Academic Assistant for IIT Hyderabad

**CampusSaathi** is a hackathon MVP designed as an intelligent academic copilot for IIT Hyderabad students. It pairs Sarvam AI's multilingual LLM with PyMuPDF document grounding and a local SQLite deadline management engine.

---

## 🌟 Key Features

1. **Multilingual Academic Chat**
   - Seamlessly switch between **English**, **Telugu (తెలుగు)**, and **Hindi (हिन्दी)**.
   - Powered by Sarvam AI (`sarvam-105b`) conversational models.
   - Clean, distraction-free chat interface with full session-state memory.

2. **Grounded Academic Handbook Q&A**
   - Upload any official IIT Hyderabad Academic Handbook PDF.
   - Uses **PyMuPDF** to index and extract page-by-page text.
   - Strict retrieval-augmented grounding: Answers academic-policy questions **only** from verified handbook excerpts and cites exact handbook page numbers (e.g. `[Page 4]`).
   - Hallucination Prevention: Explicitly declines to answer unverified policies and never invents credits, grading rules, or prerequisites.

3. **Natural Language Deadline Calendar (Asia/Kolkata)**
   - Add deadlines using natural language, e.g.:
     - *"Add my DBMS quiz tomorrow at 10 AM"*
     - *"My assignment is due Friday at 5 PM"*
     - *"Show my upcoming deadlines"*
   - Resolves relative dates and times automatically in `Asia/Kolkata` timezone.
   - **Explicit Confirmation Flow**: Prompts student with an interactive confirmation card before persisting.
   - **Safe Storage in SQLite**: Deadlines stored locally with title, course, event type, date, time, and timestamps.
   - Duplicate prevention and one-click deletion from the sidebar.

---

## 📁 Repository Structure

```text
├── app.py              # Main Streamlit application with chat, PDF Q&A & SQLite calendar
├── requirements.txt    # Python package dependencies
├── .env.example        # Environment variable template for Sarvam AI key
├── .gitignore          # Git ignore file protecting .env and SQLite databases
└── README.md           # Documentation and quick-start instructions
```

---

## 🚀 Quick Start (Windows)

### 1. Prerequisites
Ensure you have Python 3.10+ installed on your system.

### 2. Install Dependencies
Open PowerShell or Command Prompt in the project folder and run:

```powershell
pip install -r requirements.txt
```

*(Or use the specific Python executable on your system):*
```powershell
& "C:\Users\LENOVO\AppData\Local\Programs\Python\Python313\python.exe" -m pip install -r requirements.txt
```

### 3. Configure Sarvam AI API Key
Create a `.env` file from `.env.example`:

```powershell
Copy-Item .env.example .env
```

Open `.env` and enter your Sarvam AI API subscription key:
```env
SARVAM_API_KEY=your_actual_sarvam_api_key_here
```

CampusSaathi automatically loads this key on startup.

### 4. Launch CampusSaathi
Start the Streamlit application:

```powershell
streamlit run app.py
```

Or using the direct Python binary:
```powershell
& "C:\Users\LENOVO\AppData\Local\Programs\Python\Python313\python.exe" -m streamlit run app.py
```

The application will automatically open in your default browser at `http://localhost:8501`.

---

## 🧪 Demo Test Prompts

- **Handbook Q&A (after uploading PDF):**
  - *"How many credits are required to graduate with a B.Tech degree?"*
  - *"What is the minimum attendance required to appear in final exams?"*
  - *"What are the criteria for enrolling in an Honors or Minor program?"*
- **Multilingual Support:**
  - Select *Telugu (తెలుగు)* or *Hindi (हिन्दी)* in the sidebar and ask:
    - *"క్రెడిట్ అవసరాలు ఏమిటి?"*
    - *"परीक्षा में बैठने के लिए न्यूनतम उपस्थिति कितनी होनी चाहिए?"*
- **Deadline Calendar:**
  - *"Add my DBMS quiz tomorrow at 10 AM"*
  - *"My Machine Learning assignment is due Friday at 5 PM"*
  - *"Show my upcoming deadlines"*
  - Click **Confirm & Save** to persist to SQLite.

---

## 🛡️ Privacy & Security
- API keys are loaded via `python-dotenv` and never hardcoded or exposed in logs.
- `.env` and `*.db` are strictly excluded in `.gitignore`.
