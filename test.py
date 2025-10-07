from google import genai
from google.genai.types import GenerateContentConfig

client = genai.Client(api_key="AIzaSyDtJhYBjJWOIyEwBT__j9jvBo2lnuV4A7c")

response = client.models.generate_content(
    model="models/gemini-2.5-flash",
    contents="Summarize this text: Finideas is building a structured algorithmic platform for options strategies..."
)

print(response.text)
