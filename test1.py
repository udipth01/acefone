import requests, os

api_key = "AIzaSyDtJhYBjJWOIyEwBT__j9jvBo2lnuV4A7c"
r = requests.get(
    f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
)
print(r.json())
