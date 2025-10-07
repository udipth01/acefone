# filename: main.py

from fastapi import FastAPI, Request
import requests
import os
from pydantic import BaseModel

app = FastAPI()

# ==============================
# CONFIG
# ==============================
BITRIX_WEBHOOK = os.getenv("BITRIX_WEBHOOK")  # e.g. https://finideas.bitrix24.in/rest/24/abc123xyz/
ACEFONE_API_KEY = os.getenv("ACEFONE_API_KEY")
LEMONFOX_API_KEY = os.getenv("LEMONFOX_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ==============================
# MODELS
# ==============================
class AcefoneWebhook(BaseModel):
    call_id: str
    from_number: str
    to_number: str
    direction: str
    status: str

# ==============================
# HELPERS
# ==============================

def fetch_recording_url(call_id):
    """Fetch recording URL from Acefone"""
    url = f"https://api.acefone.in/v1/recordings/{call_id}"
    headers = {"Authorization": f"Bearer {ACEFONE_API_KEY}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    data = r.json()
    return data["data"]["url"]

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
    """Use Gemini 2.5 Flash to generate a summary"""
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}
    body = {"contents": [{"parts": [{"text": f"Summarize this Hindi-English mix conversation:\n\n{text}"}]}]}
    r = requests.post(url, headers=headers, params=params, json=body)
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

def find_bitrix_lead_id(phone):
    """Find Bitrix Lead ID by phone number"""
    phone = phone.replace("+", "").strip()
    url = f"{BITRIX_WEBHOOK}crm.lead.list.json"
    params = {"filter[PHONE]": phone, "select[]": ["ID", "TITLE", "PHONE"]}
    r = requests.get(url, params=params)
    data = r.json()
    if data.get("result"):
        return data["result"][0]["ID"]
    return None

def post_comment_to_lead(lead_id, text):
    """Post transcription and summary as comment in lead timeline"""
    url = f"{BITRIX_WEBHOOK}crm.timeline.comment.add.json"
    payload = {"fields": {"ENTITY_ID": lead_id, "ENTITY_TYPE": "lead", "COMMENT": text}}
    r = requests.post(url, json=payload)
    r.raise_for_status()
    return r.json()

# ==============================
# WEBHOOK ENDPOINT
# ==============================
@app.post("/acefone/call-ended")
async def acefone_webhook(payload: AcefoneWebhook):
    if payload.status.lower() != "completed":
        return {"message": "Call not completed, ignoring."}

    print(f"Processing call: {payload.call_id}")

    # 1️⃣ Fetch recording URL
    recording_url = fetch_recording_url(payload.call_id)

    # 2️⃣ Transcribe using Lemonfox
    transcription = transcribe_audio_lemonfox(recording_url)

    # 3️⃣ Summarize using Gemini
    summary = summarize_with_gemini(transcription)

    # 4️⃣ Find Bitrix lead
    lead_id = find_bitrix_lead_id(payload.to_number) or find_bitrix_lead_id(payload.from_number)

    if not lead_id:
        return {"error": "No matching lead found in Bitrix."}

    # 5️⃣ Post to Bitrix
    comment_text = f"🗣 **Call Transcription:**\n{transcription}\n\n🧩 **Summary:**\n{summary}"
    post_comment_to_lead(lead_id, comment_text)

    return {"message": "Processed successfully", "lead_id": lead_id}
