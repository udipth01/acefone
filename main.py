# filename: main.py

from fastapi import FastAPI, Request
import requests
import os
from pydantic import BaseModel

app = FastAPI()

# ==============================
# CONFIGURATION
# ==============================
ACEFONE_EMAIL = os.getenv("ACEFONE_EMAIL")        # e.g. udipth@gmail.com
ACEFONE_PASSWORD = os.getenv("ACEFONE_PASSWORD")  # your Acefone password
BITRIX_WEBHOOK = os.getenv("BITRIX_WEBHOOK")      # e.g. https://finideas.bitrix24.in/rest/24/abc123xyz/
LEMONFOX_API_KEY = os.getenv("LEMONFOX_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ACEFONE_LOGIN_URL = "https://api.acefone.in/v1/auth/login"
ACEFONE_LOG_URL = "https://api.acefone.in/v1/call/records"

# ==============================
# MODELS
# ==============================
class AcefoneWebhook(BaseModel):
    call_id: str
    client_number: str = None
    did_number: str = None
    status: str = None


# ==============================
# HELPER FUNCTIONS
# ==============================
def acefone_login():
    """Authenticate and get token"""
    payload = {"email": ACEFONE_EMAIL, "password": ACEFONE_PASSWORD}
    r = requests.post(ACEFONE_LOGIN_URL, json=payload)
    r.raise_for_status()
    data = r.json()
    return data.get("access_token")


def fetch_call_details(token, call_id):
    """Fetch specific call record using /call/records"""
    params = {"page": 1, "limit": 100}
    headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
    r = requests.get(ACEFONE_LOG_URL, headers=headers, params=params)
    r.raise_for_status()
    data = r.json()
    results = data.get("results", [])
    for call in results:
        if str(call.get("call_id")) == str(call_id):
            return call
    return None


def transcribe_audio_lemonfox(audio_url):
    """Upload audio to Lemonfox.ai for transcription"""
    endpoint = "https://api.lemonfox.ai/v1/transcribe"
    headers = {"Authorization": f"Bearer {LEMONFOX_API_KEY}"}
    payload = {"url": audio_url, "language": "auto"}
    r = requests.post(endpoint, headers=headers, json=payload)
    r.raise_for_status()
    result = r.json()
    return result.get("text", "")


def summarize_with_gemini(text):
    """Summarize text using Gemini 2.5 Flash"""
    if not text.strip():
        return "No transcription available."

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}
    body = {
        "contents": [{
            "parts": [{
                "text": f"Summarize this Hindi-English phone conversation clearly with key points and next actions:\n\n{text}"
            }]
        }]
    }

    r = requests.post(url, headers=headers, params=params, json=body)
    r.raise_for_status()
    data = r.json()
    return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")


def find_bitrix_lead_id(phone):
    """Find Bitrix Lead ID by phone number"""
    if not phone:
        return None
    phone = phone.replace("+", "").strip()
    url = f"{BITRIX_WEBHOOK}crm.lead.list.json"
    params = {"filter[PHONE]": phone, "select[]": ["ID", "TITLE", "PHONE"]}
    r = requests.get(url, params=params)
    data = r.json()
    if data.get("result"):
        return data["result"][0]["ID"]
    return None


def create_bitrix_lead(phone):
    """Create a new Bitrix lead"""
    url = f"{BITRIX_WEBHOOK}crm.lead.add.json"
    payload = {
        "fields": {
            "TITLE": f"New Lead from Acefone ({phone})",
            "PHONE": [{"VALUE": phone, "VALUE_TYPE": "WORK"}],
            "SOURCE_ID": "CALL",
        }
    }
    r = requests.post(url, json=payload)
    r.raise_for_status()
    data = r.json()
    return data.get("result")


def post_comment_to_lead(lead_id, text):
    """Post transcription + summary as comment in lead timeline"""
    url = f"{BITRIX_WEBHOOK}crm.timeline.comment.add.json"
    payload = {
        "fields": {
            "ENTITY_ID": lead_id,
            "ENTITY_TYPE": "lead",
            "COMMENT": text
        }
    }
    r = requests.post(url, json=payload)
    r.raise_for_status()
    return r.json()


# ==============================
# MAIN ENDPOINT
# ==============================
@app.post("/acefone/call-ended")
async def acefone_webhook(payload: AcefoneWebhook):
    """Triggered automatically when Acefone call ends"""
    if payload.status and payload.status.lower() != "completed":
        return {"message": "Call not completed. Ignoring."}

    print(f"Processing call_id={payload.call_id}")

    # 1️⃣ Login to Acefone
    try:
        token = acefone_login()
    except Exception as e:
        return {"error": f"Failed to login to Acefone: {e}"}

    # 2️⃣ Fetch call details
    call_data = fetch_call_details(token, payload.call_id)
    if not call_data:
        return {"error": "Call not found in Acefone records"}

    recording_url = call_data.get("recording_url")
    phone = call_data.get("client_number") or call_data.get("did_number")
    call_duration = call_data.get("call_duration")
    agent = call_data.get("agent_name", "Unknown Agent")
    start_time = f"{call_data.get('date', '')} {call_data.get('time', '')}"

    # 3️⃣ Transcription
    transcription = transcribe_audio_lemonfox(recording_url)

    # 4️⃣ Summary
    summary = summarize_with_gemini(transcription)

    # 5️⃣ Find or create lead
    lead_id = find_bitrix_lead_id(phone)
    if not lead_id:
        lead_id = create_bitrix_lead(phone)

    # 6️⃣ Post to Bitrix
    comment = (
        f"📞 **Call Summary for {phone}**\n\n"
        f"👤 Agent: {agent}\n🕒 Duration: {call_duration} sec\n📅 Time: {start_time}\n\n"
        f"🧠 **Summary:**\n{summary}\n\n"
        f"🎧 **Transcription:**\n{transcription}\n\n"
        f"🔗 [Recording Link]({recording_url})"
    )

    post_comment_to_lead(lead_id, comment)

    return {"status": "success", "lead_id": lead_id, "phone": phone}
