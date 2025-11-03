import requests
import os

# Environment / replace with your credentials for quick test
ACEFONE_EMAIL = os.getenv("ACEFONE_EMAIL", "udipth@gmail.com")
ACEFONE_PASSWORD = os.getenv("ACEFONE_PASSWORD", "Super@001")
LEMONFOX_API_KEY = os.getenv("LEMONFOX_API_KEY", "<your_lemonfox_api_key>")

ACEFONE_LOGIN_URL = "https://api.acefone.in/v1/auth/login"
ACEFONE_LOG_URL = "https://api.acefone.in/v1/call/records"


def acefone_login():
    """Authenticate and return token"""
    payload = {"email": ACEFONE_EMAIL, "password": ACEFONE_PASSWORD}
    r = requests.post(ACEFONE_LOGIN_URL, json=payload)
    r.raise_for_status()
    data = r.json()
    print("✅ Acefone Login Success")
    return data.get("access_token")


def fetch_latest_recording(token):
    """Fetch the latest completed call with a recording URL"""
    headers = {"Authorization": f"Bearer {token}"}
    params = {"page": 1, "limit": 1, "order": "desc"}
    r = requests.get(ACEFONE_LOG_URL, headers=headers, params=params)
    r.raise_for_status()
    data = r.json()
    results = data.get("results", [])
    if not results:
        raise Exception("No call records found.")
    call = results[0]
    print(f"📞 Call ID: {call.get('call_id')}")
    print(f"🎧 Recording URL: {call.get('recording_url')}")
    return call.get("recording_url")


def transcribe_with_lemonfox(audio_url):
    """Transcribe the audio URL using Lemonfox.ai"""
    endpoint = "https://api.lemonfox.ai/v1/transcribe"
    headers = {"Authorization": f"Bearer {LEMONFOX_API_KEY}"}
    payload = {"url": audio_url, "language": "auto"}
    r = requests.post(endpoint, headers=headers, json=payload)
    if r.status_code != 200:
        print("❌ Lemonfox error:", r.text)
        return None
    result = r.json()
    print("🧠 Transcription (first 300 chars):")
    print(result.get("text", "")[:300])
    return result.get("text")


if __name__ == "__main__":
    token = acefone_login()
    audio_url = fetch_latest_recording(token)
    if audio_url:
        transcribe_with_lemonfox(audio_url)
