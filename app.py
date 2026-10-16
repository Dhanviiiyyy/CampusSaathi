"""
CampusSaathi - Multilingual Academic Assistant for IIT Hyderabad
Pair-programmed hackathon MVP.
Tech Stack: Python, Streamlit, Sarvam AI API, SQLite, python-dotenv, PyMuPDF
"""

import os
import re
import json
import sqlite3
import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Optional, Tuple

import requests
import streamlit as st
from dotenv import load_dotenv
import pymupdf

# Load environment configuration automatically at application startup
# Keeps deployment environment variables if already set; loads .env otherwise
load_dotenv()

def get_sarvam_api_key() -> str:
    """Retrieve SARVAM_API_KEY from environment (.env or deployment environment)."""
    val = os.getenv("SARVAM_API_KEY", "")
    if val and val.strip():
        return val.strip().strip('"').strip("'")
    
    # Reload from .env in case the file was modified without restarting
    load_dotenv(override=True)
    val = os.getenv("SARVAM_API_KEY", "")
    if val and val.strip():
        return val.strip().strip('"').strip("'")
    return ""

# Constants
KOLKATA_TZ = ZoneInfo("Asia/Kolkata")
DB_PATH = "campussaathi.db"
SARVAM_CHAT_URL = "https://api.sarvam.ai/v1/chat/completions"
DEFAULT_MODEL = "sarvam-105b"

# Stopwords for simple keyword retrieval
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", 
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", 
    "by", "can", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for", 
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", 
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", 
    "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once", 
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "s", "same", "she", 
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves", 
    "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", 
    "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom", 
    "why", "will", "with", "would", "you", "your", "yours", "yourself", "yourselves", "tell", "show",
    "please", "give", "know", "iith", "hyderabad", "student", "students"
}

# ==========================================
# 1. SQLITE DATABASE FOR DEADLINES
# ==========================================

def get_db_connection():
    """Create and return a SQLite database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize deadlines table in SQLite."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                course TEXT,
                event_type TEXT,
                date TEXT NOT NULL,
                time TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

def add_deadline(title: str, course: str, event_type: str, date: str, time: str) -> Optional[int]:
    """Insert a new deadline into SQLite and return its ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO deadlines (title, course, event_type, date, time)
            VALUES (?, ?, ?, ?, ?)
        """, (title.strip(), course.strip() if course else "General", event_type.strip(), date.strip(), time.strip()))
        conn.commit()
        return cursor.lastrowid

def get_deadlines() -> List[Dict[str, Any]]:
    """Retrieve all saved deadlines ordered by date and time."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, course, event_type, date, time, created_at FROM deadlines ORDER BY date ASC, time ASC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def delete_deadline(deadline_id: int) -> bool:
    """Delete a deadline by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM deadlines WHERE id = ?", (deadline_id,))
        conn.commit()
        return cursor.rowcount > 0

# ==========================================
# 2. DATE & TIME RESOLUTION (ASIA/KOLKATA)
# ==========================================

def get_now_kolkata() -> datetime.datetime:
    """Return the current datetime in Asia/Kolkata timezone."""
    return datetime.datetime.now(KOLKATA_TZ)

def resolve_date_keyword(keyword: str, reference_dt: datetime.datetime) -> Optional[str]:
    """Resolve relative date keywords (today, tomorrow, weekday) relative to reference_dt."""
    kw = keyword.lower().strip()
    ref_date = reference_dt.date()
    
    if kw in ["today", "ఈరోజు", "आज"]:
        return ref_date.strftime("%Y-%m-%d")
    elif kw in ["tomorrow", "రేపు", "कल"]:
        return (ref_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    elif kw in ["day after tomorrow", "ఎల్లుండి", "परसों"]:
        return (ref_date + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    
    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
        "సోమవారం": 0, "మంగళవారం": 1, "బుధవారం": 2, "గురువారం": 3,
        "శుక్రవారం": 4, "శనివారం": 5, "ఆదివారం": 6,
        "सोमवार": 0, "मंगलवार": 1, "बुधवार": 2, "गुरुवार": 3,
        "शुक्रवार": 4, "शनिवार": 5, "रविवार": 6
    }
    
    for day_name, day_idx in weekdays.items():
        if day_name in kw:
            current_day = ref_date.weekday()
            days_ahead = (day_idx - current_day) % 7
            if days_ahead == 0:
                days_ahead = 7  # Next week's occurrence
            return (ref_date + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            
    # Try parsing YYYY-MM-DD or DD-MM-YYYY or DD/MM/YYYY
    date_match = re.search(r'\b(202\d[-/]\d{1,2}[-/]\d{1,2})\b', kw)
    if date_match:
        try:
            parts = [int(p) for p in re.split(r'[-/]', date_match.group(1))]
            return datetime.date(parts[0], parts[1], parts[2]).strftime("%Y-%m-%d")
        except Exception:
            pass
            
    return None

def normalize_time(time_str: str) -> Optional[str]:
    """Normalize time string to standard format like '10:00 AM' or '05:30 PM'."""
    clean = time_str.strip().upper()
    match = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?\b', clean, re.IGNORECASE)
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2)) if match.group(2) else 0
    meridiem = match.group(3)
    
    if meridiem:
        meridiem = meridiem.upper()
        if meridiem == "PM" and hours < 12:
            hours_24 = hours + 12
        elif meridiem == "AM" and hours == 12:
            hours_24 = 0
        else:
            hours_24 = hours
    else:
        # Default interpretation for student hours: 1..7 -> PM (e.g. 5 PM), 8..11 -> AM, 12..23 -> 24hr
        if 1 <= hours <= 7:
            meridiem = "PM"
            hours_24 = hours + 12
        elif 8 <= hours <= 11:
            meridiem = "AM"
            hours_24 = hours
        elif hours == 12:
            meridiem = "PM"
            hours_24 = 12
        elif 13 <= hours <= 23:
            meridiem = "PM"
            hours_24 = hours
            hours = hours - 12
        else:
            meridiem = "AM"
            hours_24 = 0
            
    try:
        t = datetime.time(hours_24, minutes)
        return t.strftime("%I:%M %p")
    except ValueError:
        return None

# ==========================================
# 3. RULE-BASED DEADLINE INTENT & PARSER
# ==========================================

def extract_deadline_rule_based(text: str, now_ist: datetime.datetime) -> Dict[str, Any]:
    """
    Deterministically extract deadline information from user natural language query.
    Works independently as a fast, reliable extractor or fallback for Sarvam.
    """
    text_lower = text.lower()
    
    # Event types detection
    event_type = "Event"
    if "quiz" in text_lower or "క్విజ్" in text_lower or "क्विज" in text_lower:
        event_type = "Quiz"
    elif "assignment" in text_lower or "అసైన్‌మెంట్" in text_lower or "असाइनमेंट" in text_lower:
        event_type = "Assignment"
    elif "exam" in text_lower or "midsem" in text_lower or "endsem" in text_lower or "పరీక్ష" in text_lower or "परीक्षा" in text_lower:
        event_type = "Exam"
    elif "project" in text_lower or "submission" in text_lower or "సబ్మిషన్" in text_lower:
        event_type = "Project / Submission"
    elif "presentation" in text_lower or "lab" in text_lower:
        event_type = "Lab / Presentation"
        
    # Course detection (e.g. DBMS, OS, AI, CS3510, Math, etc.)
    course = ""
    course_match = re.search(r'\b([A-Z]{2,}\s?\d{3,4}|DBMS|OS|DSA|AI|ML|MATH|PHYSICS|CHEMISTRY|NETWORKS|COMPILERS)\b', text, re.IGNORECASE)
    if course_match:
        course = course_match.group(1).upper()
        
    # Time detection
    time_val = None
    time_match = re.search(r'\b(?:at|by|before|around)?\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)|\d{1,2}\s*(?:am|pm|AM|PM))\b', text)
    if time_match:
        time_val = normalize_time(time_match.group(1))
    else:
        # Check raw 24-hr time e.g. 17:00
        time_24 = re.search(r'\b([01]?\d|2[0-3]):([0-5]\d)\b', text)
        if time_24:
            time_val = normalize_time(time_24.group(0))

    # Date detection
    date_val = None
    # Check words like today, tomorrow, day after tomorrow, weekday
    for kw in ["day after tomorrow", "tomorrow", "today", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
               "రేపు", "ఈరోజు", "ఎల్లుండి", "సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం", "ఆదివారం",
               "कल", "आज", "परसों", "सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]:
        if kw in text_lower:
            date_val = resolve_date_keyword(kw, now_ist)
            break
            
    # Check specific dates like "25th October", "Oct 25", "25-10-2026"
    if not date_val:
        month_names = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
            "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
        }
        month_match1 = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|[a-z]+)\b', text_lower)
        month_match2 = re.search(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|[a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b', text_lower)
        if month_match1 and month_match1.group(2) in month_names:
            day = int(month_match1.group(1))
            month = month_names[month_match1.group(2)]
            try:
                date_val = datetime.date(now_ist.year, month, day).strftime("%Y-%m-%d")
            except Exception:
                pass
        elif month_match2 and month_match2.group(1) in month_names:
            day = int(month_match2.group(2))
            month = month_names[month_match2.group(1)]
            try:
                date_val = datetime.date(now_ist.year, month, day).strftime("%Y-%m-%d")
            except Exception:
                pass
                
    # Ambiguity evaluation
    is_ambiguous = False
    clarification = ""
    if not date_val and not time_val:
        is_ambiguous = True
        clarification = "Could you please specify the date and time for this deadline?"
    elif not date_val:
        is_ambiguous = True
        clarification = "Could you please clarify what date this deadline is on (e.g., tomorrow, Friday, or Oct 25)?"
    elif not time_val:
        is_ambiguous = True
        clarification = f"Could you please specify the time for the deadline on {date_val} (e.g., 10 AM or 5 PM)?"
        
    # Check for subject/topic preceding the event type, e.g. "DBMS quiz", "Computer Networks assignment"
    if not course:
        subj_match = re.search(r'\b([A-Za-z0-9_-]+)\s+(?:quiz|assignment|exam|project|lab|submission)\b', text, re.IGNORECASE)
        if subj_match:
            candidate = subj_match.group(1).strip()
            if candidate.lower() not in ["my", "the", "a", "an", "this", "our", "new", "next", "one"]:
                course = candidate.upper()

    title = f"{course} {event_type}".strip() if course else f"{event_type}"
    if not title or title == "Event":
        title = "Academic Deadline"
            
    return {
        "title": title,
        "course": course or "General",
        "event_type": event_type,
        "date": date_val or "",
        "time": time_val or "",
        "is_ambiguous": is_ambiguous,
        "clarification_question": clarification
    }

# ==========================================
# 4. SARVAM AI API CALL & RESPONSE EXTRACTION
# ==========================================

def extract_text_from_sarvam_response(data: Any) -> Optional[str]:
    """
    Safely extract assistant message text from Sarvam AI response dictionary.
    Handles official Sarvam / OpenAI-compatible schema:
      - choices[0].message.content
      - choices[0].message.reasoning_content (if reasoning model)
      - choices[0].text (completion format fallback)
    Returns None if no valid, non-empty, non-'None' string is present.
    """
    if not isinstance(data, dict):
        return None
        
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) == 0:
        return None
        
    choice = choices[0]
    if not isinstance(choice, dict):
        return None
        
    # Standard Chat Completion: choices[0].message
    message = choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if content is not None:
            text = str(content).strip()
            if text and text != "None" and text.lower() != "null":
                return text
                
        # If content is empty or None, check reasoning_content
        reasoning = message.get("reasoning_content")
        if reasoning is not None:
            text = str(reasoning).strip()
            if text and text != "None" and text.lower() != "null":
                return text

    # Legacy / Alternate: choices[0].text
    choice_text = choice.get("text")
    if choice_text is not None:
        text = str(choice_text).strip()
        if text and text != "None" and text.lower() != "null":
            return text

    return None

def call_sarvam_chat(
    messages: List[Dict[str, str]],
    api_key: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 1024
) -> Tuple[bool, str]:
    """
    Call Sarvam AI Chat Completion API using official REST endpoints.
    Endpoint: https://api.sarvam.ai/v1/chat/completions
    Header: api-subscription-key
    """
    clean_key = (api_key or "").strip().strip('"').strip("'")
    if not clean_key:
        return False, "SARVAM_API_KEY is missing. Please add SARVAM_API_KEY=your_actual_key to .env and restart the application."

    # Validate and filter messages so only clean, non-empty strings are transmitted
    sanitized_messages = []
    for m in messages:
        if isinstance(m, dict):
            role = m.get("role", "user")
            content = m.get("content")
            if content is not None:
                c_str = str(content).strip()
                if c_str and c_str != "None":
                    sanitized_messages.append({"role": role, "content": c_str})

    if not sanitized_messages:
        return False, "Cannot send an empty message payload to Sarvam AI."

    headers = {
        "api-subscription-key": clean_key,
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": sanitized_messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    try:
        response = requests.post(SARVAM_CHAT_URL, headers=headers, json=payload, timeout=40)
        
        if response.status_code == 200:
            try:
                data = response.json()
            except Exception:
                return False, "Received an unparseable response from Sarvam AI API."

            reply = extract_text_from_sarvam_response(data)
            if reply is not None:
                return True, reply
            else:
                return False, "Sarvam AI responded with no usable content. Please try rephrasing your question."
        else:
            err_msg = ""
            try:
                err_json = response.json()
                if isinstance(err_json, dict):
                    err_field = err_json.get("error")
                    if isinstance(err_field, dict):
                        err_msg = err_field.get("message", "")
                    elif isinstance(err_field, str):
                        err_msg = err_field
                    elif "message" in err_json:
                        err_msg = str(err_json["message"])
            except Exception:
                pass
                
            if not err_msg:
                err_msg = f"HTTP {response.status_code} Error"
                
            # Ensure API key is never exposed in error message
            safe_err = str(err_msg).replace(clean_key, "[REDACTED]")
            return False, f"Sarvam AI Error ({response.status_code}): {safe_err}"
            
    except requests.exceptions.Timeout:
        return False, "Sarvam AI request timed out. Please check your network connection and try again."
    except requests.exceptions.RequestException as e:
        safe_e = str(e).replace(clean_key, "[REDACTED]")
        return False, f"Connection error connecting to Sarvam AI API: {safe_e}"
    except Exception as e:
        safe_e = str(e).replace(clean_key, "[REDACTED]")
        return False, f"Unexpected error during API call: {safe_e}"

# ==========================================
# 5. HANDBOOK PROCESSING & RETRIEVAL (PYMUPDF)
# ==========================================

def extract_pdf_handbook(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Extract text and page numbers from uploaded PDF bytes using PyMuPDF."""
    pages = []
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        for i in range(len(doc)):
            page_text = doc[i].get_text("text").strip()
            if page_text:
                pages.append({"page": i + 1, "text": page_text})
        doc.close()
    except Exception as e:
        st.error(f"Error parsing PDF with PyMuPDF: {e}")
    return pages

def retrieve_handbook_context(query: str, pages: List[Dict[str, Any]], top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Keyword matching retrieval to extract relevant pages from handbook.
    Calculates relevance score per page based on token frequency.
    """
    tokens = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', query) if w.lower() not in STOPWORDS]
    if not tokens or not pages:
        return []
    
    scored_pages = []
    for p in pages:
        text_lower = p["text"].lower()
        score = 0
        matched_tokens = 0
        for token in set(tokens):
            count = text_lower.count(token)
            if count > 0:
                score += count * 2
                matched_tokens += 1
                
        # Bonus if multiple distinct keywords match on the same page
        score += matched_tokens * 3
        
        if score > 0:
            scored_pages.append((score, p))
            
    scored_pages.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored_pages[:top_k]]

# ==========================================
# 6. INTENT CLASSIFICATION & LLM DISPATCH
# ==========================================

def parse_user_intent_with_llm(user_text: str, api_key: str, now_ist: datetime.datetime) -> Dict[str, Any]:
    """
    Use Sarvam AI to classify intent and parse deadlines into structured JSON.
    Falls back gracefully to local rule-based extractor if API call fails.
    """
    ref_time_str = now_ist.strftime("%Y-%m-%d %I:%M %p, %A")
    system_prompt = f"""You are an event extraction parser for CampusSaathi at IIT Hyderabad.
Reference current time in Asia/Kolkata: {ref_time_str}.
Classify the user input:
1. 'list_deadlines': User wants to view, show, or check upcoming deadlines or events.
2. 'add_deadline': User wants to add, create, schedule, or set a deadline, quiz, assignment, exam, or submission.
3. 'chat': General academic or policy question or normal conversation.

For 'add_deadline', resolve dates against the reference date.
Output STRICTLY valid JSON with these keys and no extra commentary:
{{
  "intent": "add_deadline" | "list_deadlines" | "chat",
  "title": "Title of the deadline",
  "course": "Course name or General",
  "event_type": "Quiz" | "Assignment" | "Exam" | "Project" | "Submission" | "Other",
  "date": "YYYY-MM-DD",
  "time": "HH:MM AM/PM",
  "is_ambiguous": false,
  "clarification_question": ""
}}
If date or time is missing or ambiguous, set "is_ambiguous": true and provide a helpful "clarification_question"."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text}
    ]
    
    if api_key:
        success, response_text = call_sarvam_chat(messages, api_key, temperature=0.1, max_tokens=350)
        if success and response_text and isinstance(response_text, str) and response_text.strip() != "None":
            try:
                # Strip code fences if present
                clean_json = re.sub(r'```json\s*|\s*```', '', response_text).strip()
                # Find JSON block
                json_match = re.search(r'\{.*\}', clean_json, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    if "intent" in parsed:
                        return parsed
            except Exception:
                pass  # Fall back to rule-based

    # Local rule-based fallback
    text_lower = user_text.lower()
    if any(q in text_lower for q in ["show my deadlines", "upcoming deadlines", "view deadlines", "list deadlines", "what are my deadlines", "నా డెడ్‌లైన్‌లు", "मेरे डेडलाइन"]):
        return {"intent": "list_deadlines"}
        
    deadline_keywords = ["add", "schedule", "quiz", "assignment", "due", "submit", "submission", "exam", "test", "remind", "డెడ్‌లైన్", "క్విజ్", "असाइनमेंट", "परीक्षा"]
    if any(k in text_lower for k in deadline_keywords) and any(w in text_lower for w in ["tomorrow", "today", "at", "on", "friday", "monday", "pm", "am", "due", "రేపు", "कल"]):
        extracted = extract_deadline_rule_based(user_text, now_ist)
        extracted["intent"] = "add_deadline"
        return extracted
        
    return {"intent": "chat"}

# ==========================================
# 7. STREAMLIT APPLICATION UI
# ==========================================

st.set_page_config(
    page_title="CampusSaathi - IIT Hyderabad Academic Copilot",
    page_icon="🎓",
    layout="wide"
)

# Initialize database
init_db()

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "👋 Namaste! I am **CampusSaathi**, your multilingual academic copilot for IIT Hyderabad.\n\n"
                       "- 📘 **Upload your Academic Handbook** in the sidebar to ask questions about credit requirements, grading, and policies.\n"
                       "- 📅 **Manage Deadlines:** Try saying *'Add my DBMS quiz tomorrow at 10 AM'* or *'My assignment is due Friday at 5 PM'*.\n"
                       "- 🌐 **Multilingual:** Select English, Telugu (తెలుగు), or Hindi (हिन्दी) in the sidebar."
        }
    ]

if "pending_deadline" not in st.session_state:
    st.session_state.pending_deadline = None

if "handbook_pages" not in st.session_state:
    st.session_state.handbook_pages = []

if "handbook_name" not in st.session_state:
    st.session_state.handbook_name = ""

# --- Sidebar Configuration ---
with st.sidebar:
    st.markdown("### 🎓 CampusSaathi Settings")
    
    # Language Selector
    lang_choice = st.selectbox(
        "🌐 Language / భాష / भाषा",
        ["English", "Telugu (తెలుగు)", "Hindi (हिन्दी)"],
        index=0
    )
    
    # Map to standard language name
    if "Telugu" in lang_choice:
        selected_lang = "Telugu"
    elif "Hindi" in lang_choice:
        selected_lang = "Hindi"
    else:
        selected_lang = "English"
        
    st.divider()
    
    # Sarvam AI Status Display (Loaded automatically from .env)
    st.markdown("#### 🔑 Sarvam AI Status")
    api_key = get_sarvam_api_key()
    
    if api_key:
        st.success("✅ `SARVAM_API_KEY` active (from `.env`)")
    else:
        st.warning(
            "⚠️ **`SARVAM_API_KEY` missing**\n\n"
            "Please add `SARVAM_API_KEY=your_actual_key` to your `.env` file and restart the application."
        )

    st.divider()

    # Academic Handbook Upload
    st.markdown("#### 📘 Academic Handbook")
    uploaded_handbook = st.file_uploader(
        "Upload IITH Handbook (PDF)",
        type=["pdf"],
        help="PyMuPDF will index pages for policy verification"
    )
    
    if uploaded_handbook is not None:
        if st.session_state.handbook_name != uploaded_handbook.name:
            file_bytes = uploaded_handbook.read()
            with st.spinner("Indexing handbook pages with PyMuPDF..."):
                extracted_pages = extract_pdf_handbook(file_bytes)
                st.session_state.handbook_pages = extracted_pages
                st.session_state.handbook_name = uploaded_handbook.name
            st.success(f"Indexed {len(extracted_pages)} pages from {uploaded_handbook.name}")
            st.rerun()
            
    if st.session_state.handbook_pages:
        st.caption(f"📑 Active Handbook: **{st.session_state.handbook_name}** ({len(st.session_state.handbook_pages)} pages)")
        if st.button("🗑️ Remove Handbook", use_container_width=True):
            st.session_state.handbook_pages = []
            st.session_state.handbook_name = ""
            st.rerun()
    else:
        st.caption("ℹ️ No handbook uploaded. Policy queries will indicate unverified status.")
        
    st.divider()

    # Upcoming Deadlines Section
    st.markdown("#### 📅 Upcoming Deadlines")
    deadlines = get_deadlines()
    
    if deadlines:
        st.caption(f"Total scheduled: **{len(deadlines)}**")
        for item in deadlines:
            with st.container(border=True):
                st.markdown(f"**{item['title']}**")
                st.caption(f"📚 {item['course']} | 🏷️ {item['event_type']}")
                st.markdown(f"🗓️ `{item['date']}` at `{item['time']}`")
                if st.button("🗑️ Delete", key=f"del_{item['id']}", use_container_width=True):
                    delete_deadline(item['id'])
                    st.toast(f"Deleted '{item['title']}'")
                    st.rerun()
    else:
        st.info("No upcoming deadlines yet.\nTry asking CampusSaathi to add one!")

# --- Main App Header ---
st.markdown("# 🎓 CampusSaathi")
st.markdown("##### *Your multilingual academic copilot for IIT Hyderabad*")
st.divider()

# --- Pending Deadline Confirmation Banner ---
if st.session_state.pending_deadline is not None:
    pending = st.session_state.pending_deadline
    with st.container(border=True):
        st.warning("⚠️ **Explicit Confirmation Required Before Saving Deadline**")
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f"**Title:** {pending['title']}")
            st.markdown(f"**Course:** {pending['course']} &nbsp;|&nbsp; **Type:** {pending['event_type']}")
            st.markdown(f"**Date:** `{pending['date']}` &nbsp;|&nbsp; **Time:** `{pending['time']}` *(Asia/Kolkata)*")
        with col2:
            st.write("")
            confirm_col, cancel_col = st.columns(2)
            with confirm_col:
                if st.button("✅ Confirm & Save", key="btn_confirm_deadline", use_container_width=True, type="primary"):
                    # Safely handle single execution
                    event_to_save = st.session_state.pending_deadline
                    st.session_state.pending_deadline = None
                    
                    saved_id = add_deadline(
                        event_to_save["title"],
                        event_to_save["course"],
                        event_to_save["event_type"],
                        event_to_save["date"],
                        event_to_save["time"]
                    )
                    
                    if saved_id:
                        success_msg = (
                            f"✅ **Deadline Confirmed & Saved!**\n\n"
                            f"- **Title:** {event_to_save['title']}\n"
                            f"- **Course:** {event_to_save['course']}\n"
                            f"- **Event Type:** {event_to_save['event_type']}\n"
                            f"- **Date & Time:** {event_to_save['date']} at {event_to_save['time']} (IST)\n"
                            f"- **Database ID:** #{saved_id} (SQLite)"
                        )
                        st.session_state.messages.append({"role": "assistant", "content": success_msg})
                    else:
                        st.session_state.messages.append({"role": "assistant", "content": "❌ Failed to save event to SQLite database."})
                    st.rerun()
            with cancel_col:
                if st.button("❌ Cancel", key="btn_cancel_deadline", use_container_width=True):
                    st.session_state.pending_deadline = None
                    st.session_state.messages.append({"role": "assistant", "content": "❌ Cancelled deadline creation."})
                    st.rerun()

# --- Display Chat History ---
for msg in st.session_state.messages:
    msg_content = msg.get("content")
    if msg_content is not None:
        content_str = str(msg_content).strip()
        if content_str and content_str != "None":
            with st.chat_message(msg.get("role", "assistant")):
                st.markdown(content_str)

# --- Chat Input Handler ---
if prompt := st.chat_input("Ask an academic question or add a deadline (e.g. 'Add DBMS quiz tomorrow at 10 AM')..."):
    # Append user prompt to history
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    now_ist = get_now_kolkata()
    
    # 1. Handle direct conversational confirmation if pending deadline exists
    if st.session_state.pending_deadline is not None and prompt.strip().lower() in ["yes", "confirm", "ok", "save", "సరే", "అవును", "हाँ", "पुष्टि करें"]:
        event_to_save = st.session_state.pending_deadline
        st.session_state.pending_deadline = None
        saved_id = add_deadline(
            event_to_save["title"],
            event_to_save["course"],
            event_to_save["event_type"],
            event_to_save["date"],
            event_to_save["time"]
        )
        if saved_id:
            reply = (
                f"✅ **Deadline Confirmed & Saved to SQLite!**\n\n"
                f"- **Title:** {event_to_save['title']}\n"
                f"- **Date & Time:** {event_to_save['date']} at {event_to_save['time']}\n"
                f"- Saved in your calendar schedule."
            )
        else:
            reply = "❌ Database error: Could not confirm save to SQLite."
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()

    # 2. Determine Intent using LLM / Fallback
    with st.spinner("CampusSaathi is processing..."):
        intent_info = parse_user_intent_with_llm(prompt, api_key, now_ist)
        intent = intent_info.get("intent", "chat")

        # --- A. Show / List Deadlines ---
        if intent == "list_deadlines":
            current_deadlines = get_deadlines()
            if not current_deadlines:
                if selected_lang == "Telugu":
                    reply = "📅 మీ క్యాలెండర్‌లో ప్రస్తుతం రాబోయే డెడ్‌లైన్‌లు ఏవీ లేవు."
                elif selected_lang == "Hindi":
                    reply = "📅 आपके कैलेंडर में वर्तमान में कोई आगामी समय सीमा (deadlines) नहीं हैं।"
                else:
                    reply = "📅 You have no upcoming deadlines scheduled right now."
            else:
                lines = ["### 📅 Upcoming Academic Deadlines\n"]
                for d in current_deadlines:
                    lines.append(f"- **{d['title']}** ({d['course']} - {d['event_type']}): `{d['date']}` at `{d['time']}`")
                reply = "\n".join(lines)
                
            st.session_state.messages.append({"role": "assistant", "content": reply})
            with st.chat_message("assistant"):
                st.markdown(reply)

        # --- B. Add Deadline Intent ---
        elif intent == "add_deadline":
            is_ambiguous = intent_info.get("is_ambiguous", False)
            date_val = intent_info.get("date", "").strip()
            time_val = intent_info.get("time", "").strip()
            
            # Additional validation
            if not date_val or not time_val:
                is_ambiguous = True

            if is_ambiguous:
                clarification = intent_info.get("clarification_question") or "Please specify both the date and time for this deadline."
                if selected_lang == "Telugu":
                    clarification_msg = f"⚠️ డెడ్‌లైన్ వివరాలు అస్పష్టంగా ఉన్నాయి. దయచేసి స్పష్టమైన తేదీ మరియు సమయాన్ని పేర్కొనండి (ఉదా: 'రేపు ఉదయం 10 గంటలకు').\n\n*{clarification}*"
                elif selected_lang == "Hindi":
                    clarification_msg = f"⚠️ समय सीमा का विवरण स्पष्ट नहीं है। कृपया स्पष्ट तारीख और समय बताएं (उदा. 'कल सुबह 10 बजे')।\n\n*{clarification}*"
                else:
                    clarification_msg = f"⚠️ The deadline details are ambiguous. {clarification}"
                    
                st.session_state.messages.append({"role": "assistant", "content": clarification_msg})
                with st.chat_message("assistant"):
                    st.markdown(clarification_msg)
            else:
                # Store pending event for explicit confirmation
                title_val = intent_info.get("title") or "Academic Deadline"
                course_val = intent_info.get("course") or "General"
                event_type_val = intent_info.get("event_type") or "Deadline"

                st.session_state.pending_deadline = {
                    "title": title_val,
                    "course": course_val,
                    "event_type": event_type_val,
                    "date": date_val,
                    "time": time_val
                }

                if selected_lang == "Telugu":
                    prompt_confirm = (
                        f"📅 **డెడ్‌లైన్ ప్రణాళికను సిద్ధం చేసాను:**\n"
                        f"- **శీర్షిక:** {title_val}\n"
                        f"- **కోర్సు:** {course_val} ({event_type_val})\n"
                        f"- **తేదీ & సమయం:** {date_val} at {time_val}\n\n"
                        f"సేవ్ చేయడానికి పైన ఉన్న **Confirm & Save** బటన్‌ను క్లిక్ చేయండి లేదా 'yes' అని టైప్ చేయండి."
                    )
                elif selected_lang == "Hindi":
                    prompt_confirm = (
                        f"📅 **प्रस्तावित समय सीमा (Deadline):**\n"
                        f"- **शीर्षक:** {title_val}\n"
                        f"- **कोर्स:** {course_val} ({event_type_val})\n"
                        f"- **तारीख और समय:** {date_val} को {time_val}\n\n"
                        f"सेव करने के लिए कृपया ऊपर दिए गए **Confirm & Save** बटन पर क्लिक करें या 'yes' टाइप करें।"
                    )
                else:
                    prompt_confirm = (
                        f"📅 **Proposed Deadline Details:**\n"
                        f"- **Title:** {title_val}\n"
                        f"- **Course:** {course_val} ({event_type_val})\n"
                        f"- **Date & Time:** {date_val} at {time_val} (Asia/Kolkata)\n\n"
                        f"👉 **Please review and click the 'Confirm & Save' button above to add it to SQLite.**"
                    )
                    
                st.session_state.messages.append({"role": "assistant", "content": prompt_confirm})
                st.rerun()

        # --- C. General Academic / Policy Chat ---
        else:
            # Check handbook context
            relevant_passages = []
            if st.session_state.handbook_pages:
                relevant_passages = retrieve_handbook_context(prompt, st.session_state.handbook_pages, top_k=3)
                
            # Construct System Prompt
            lang_instructions = {
                "English": "Respond strictly in clear, professional English.",
                "Telugu": "సమాధానాన్ని స్పష్టమైన, సరళమైన తెలుగులో మాత్రమే రాయండి (Respond strictly in Telugu).",
                "Hindi": "उत्तर को केवल स्पष्ट और सरल हिंदी में ही लिखें (Respond strictly in Hindi)."
            }
            
            system_prompt = (
                f"You are CampusSaathi, a knowledgeable, friendly academic copilot for IIT Hyderabad (IITH) students.\n"
                f"Selected Language: {selected_lang}.\n"
                f"{lang_instructions.get(selected_lang, 'Respond in English.')}\n\n"
            )
            
            if relevant_passages:
                evidence_text = "\n\n".join([f"--- [Page {p['page']}] ---\n{p['text']}" for p in relevant_passages])
                system_prompt += (
                    "ACADEMIC HANDBOOK EVIDENCE PROVIDED BELOW:\n"
                    f"{evidence_text}\n\n"
                    "CRITICAL INSTRUCTIONS FOR HANDBOOK QUESTIONS:\n"
                    "1. Answer academic-policy and rules questions ONLY using the evidence excerpts provided above.\n"
                    "2. Cite the exact handbook page number in brackets (e.g. [Page X]) for all rules or policies cited.\n"
                    "3. If the question asks about an academic policy, credit rule, prerequisite, or grading policy that CANNOT be verified from the provided excerpts, explicitly say that the information cannot be verified in the uploaded handbook.\n"
                    "4. NEVER invent, assume, or hallucinate credit requirements, elective rules, grading policies, attendance criteria, or prerequisites.\n"
                )
            else:
                system_prompt += (
                    "NOTE: No academic handbook is currently uploaded.\n"
                    "If the student asks about specific IIT Hyderabad academic policies, credit requirements, grading scales, or course regulations, you MUST explicitly state that official IITH academic policies cannot be verified without official material, and advise them to upload the official handbook in the sidebar.\n"
                )

            # Build clean multi-turn context (last 6 turns, ensuring valid non-empty strings)
            api_messages = [{"role": "system", "content": system_prompt}]
            for m in st.session_state.messages[-6:]:
                if m.get("role") in ["user", "assistant"]:
                    c = m.get("content")
                    if c is not None:
                        c_str = str(c).strip()
                        if c_str and c_str != "None":
                            api_messages.append({"role": m["role"], "content": c_str})
                    
            if not api_key:
                err_reply = (
                    "⚠️ **Sarvam AI API Key Required**\n\n"
                    "CampusSaathi loads your API key automatically from `.env`, but `SARVAM_API_KEY` is not set.\n\n"
                    "Please add `SARVAM_API_KEY=your_actual_key` to your `.env` file and restart the application."
                )
                st.session_state.messages.append({"role": "assistant", "content": err_reply})
                with st.chat_message("assistant"):
                    st.markdown(err_reply)
            else:
                success, reply_text = call_sarvam_chat(api_messages, api_key)
                if not success:
                    clean_err = f"⚠️ {reply_text}"
                    st.session_state.messages.append({"role": "assistant", "content": clean_err})
                    with st.chat_message("assistant"):
                        st.markdown(clean_err)
                else:
                    # Validate that reply_text is non-empty and not the literal string 'None'
                    valid_text = str(reply_text).strip() if reply_text is not None else ""
                    if valid_text and valid_text != "None" and valid_text.lower() != "null":
                        st.session_state.messages.append({"role": "assistant", "content": valid_text})
                        with st.chat_message("assistant"):
                            st.markdown(valid_text)
                    else:
                        no_content_msg = "⚠️ Sarvam AI returned no usable response content. Please try rephrasing your question."
                        st.session_state.messages.append({"role": "assistant", "content": no_content_msg})
                        with st.chat_message("assistant"):
                            st.markdown(no_content_msg)
