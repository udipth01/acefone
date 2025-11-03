import requests
import tempfile
import os
import base64
from google import genai

# === CONFIG ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDtJhYBjJWOIyEwBT__j9jvBo2lnuV4A7c")

# ✅ Direct working Acefone recording link
RECORDING_URL = "https://console.acefone.in/file/recording?callId=1762172202.162636&type=rec&token=Nm9hZWdVL280eFJmekxoeXZsV0VVem9wSmUyUkVvcnNZUjJCTEF0SC9wellCSlRBcDU4bDg4aGFyeHZ6OUc0Rjo6YWIxMjM0Y2Q1NnJ0eXl1dQ%3D%3D"

# === STEP 1: Download Audio ===
def download_audio(url):
    print("⬇️ Downloading from Acefone...")
    r = requests.get(url)
    if r.status_code != 200:
        raise Exception(f"❌ Download failed ({r.status_code}): {r.text}")

    size = len(r.content)
    print(f"📦 File size: {size} bytes")
    if size < 5000:
        raise Exception("❌ File too small, possibly empty or recording still processing.")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.write(r.content)
    tmp.close()
    print(f"✅ Audio saved at: {tmp.name}")
    return tmp.name


# === STEP 2: Transcribe Audio with Gemini ===
def transcribe_with_gemini(file_path):
    print("🎙️ Sending to Gemini for transcription...")
    client = genai.Client(api_key=GEMINI_API_KEY)

    with open(file_path, "rb") as f:
        audio_data = f.read()

    audio_base64 = base64.b64encode(audio_data).decode("utf-8")

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
                        "text": "Transcribe this Hindi-English (Hinglish) mixed phone conversation as accurately as possible. Return only the transcript text."
                    }
                ]
            }
        ]
    )

    transcript = response.text.strip()
    print("\n🧠 Gemini Transcription:\n")
    print(transcript[:1000] + ("..." if len(transcript) > 1000 else ""))
    return transcript


# === STEP 3: Generate Summary ===
def summarize_with_gemini(transcript):
    print("\n📝 Summarizing call...")
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"Summarize the following call transcript in 4-5 bullet points:\n\n{transcript}"
    response = client.models.generate_content(
        model="models/gemini-2.5-pro",
        contents=[{"role": "user", "parts": [{"text": prompt}]}]
    )

    summary = response.text.strip()
    print("\n📋 Summary:\n")
    print(summary)
    return summary


# === MAIN ===
if __name__ == "__main__":
    try:
        audio_file = download_audio(RECORDING_URL)
        transcript = transcribe_with_gemini(audio_file)
        summarize_with_gemini(transcript)
    except Exception as e:
        print("❌ Error:", e)
