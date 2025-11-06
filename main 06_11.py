# filename: main.py

from fastapi import FastAPI, Request,HTTPException,Header
import requests
import os
import base64
from pydantic import BaseModel
from google import genai
import time

app = FastAPI()

# ==============================
# CONFIGURATION
# ==============================
ACEFONE_EMAIL = os.getenv("ACEFONE_EMAIL")        # e.g. udipth@gmail.com
ACEFONE_PASSWORD = os.getenv("ACEFONE_PASSWORD")  # your Acefone password
BITRIX_WEBHOOK = os.getenv("BITRIX_WEBHOOK")      # e.g. https://finideas.bitrix24.in/rest/24/abc123xyz/
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")      # from https://aistudio.google.com/app/apikey
ACF_SECRET = os.getenv("ACF_SECRET")              # your Acefone webhook secret

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
    headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
    r = requests.get(ACEFONE_LOG_URL, headers=headers, params={"page": 1, "limit": 100})
    r.raise_for_status()
    data = r.json()
    results = data.get("results", [])
    for call in results:
        if str(call.get("call_id")) == str(call_id):
            return call
    return None


def download_audio(url):
    """Download MP3 recording from Acefone"""
    r = requests.get(url)
    if r.status_code != 200:
        raise Exception(f"Failed to download audio: {r.status_code}")
    if len(r.content) < 5000:
        raise Exception("Audio file too small or not ready.")
    return r.content


def transcribe_with_gemini(audio_bytes):
    """Transcribe audio using Gemini 2.5 Pro"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

    response = client.models.generate_content(
        model="models/gemini-2.5-pro",
        contents=[
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "audio/mp3",
                            "data": audio_base64
                        }
                    },
                    {
                        "text": "Transcribe this Hindi-English (Hinglish) mixed phone call accurately, maintaining tone and context."
                    }
                ]
            }
        ]
    )

    transcript = response.text.strip()
    return transcript


def summarize_with_gemini(transcript):
    """Summarize transcript using Gemini"""
    if not transcript.strip():
        return "No transcription available."

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = (
        "Summarize this phone conversation in 3-5 key points and 1 action suggestion:\n\n"
        f"{transcript}"
    )

    response = client.models.generate_content(
        model="models/gemini-2.5-pro",
        contents=[{"role": "user", "parts": [{"text": prompt}]}]
    )

    summary = response.text.strip()
    return summary


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
async def acefone_webhook(payload: AcefoneWebhook, x_secret: str = Header(None)):
    if ACF_SECRET and x_secret != os.getenv("ACF_SECRET"):
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    """Triggered automatically when Acefone call ends"""
    if payload.status and payload.status.lower() != "completed":
        return {"message": "Call not completed. Ignoring."}

    print(f"🎧 Processing call_id={payload.call_id}")

    # --- 3️⃣ Delay to ensure recording ready ---
    time.sleep(15)  # wait 15 seconds before downloading audio

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

    # 3️⃣ Download and Transcribe
    try:
        audio_bytes = download_audio(recording_url)
        transcription = transcribe_with_gemini(audio_bytes)
    except Exception as e:
        transcription = f"Transcription failed: {e}"

    # 4️⃣ Summarize
    try:
        summary = summarize_with_gemini(transcription)
    except Exception as e:
        summary = f"Summary failed: {e}"

    # 5️⃣ Find or create lead
    lead_id = find_bitrix_lead_id(phone)
    if not lead_id:
        lead_id = create_bitrix_lead(phone)

    # 6️⃣ Post to Bitrix
    comment = (
        f"📞 **Call Summary for {phone}**\n\n"
        f"👤 Agent: {agent}\n🕒 Duration: {call_duration} sec\n📅 Time: {start_time}\n\n"
        f"🧠 **Summary:**\n{summary}\n\n"
        f"🎧 **Transcription:**\n{transcription[:5000]}\n\n"
        f"🔗 [Recording Link]({recording_url})"
    )

    post_comment_to_lead(lead_id, comment)

    return {"status": "success", "lead_id": lead_id, "phone": phone}
