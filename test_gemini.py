"""
Standalone Gemini connectivity test - run this directly, NOT through streamlit.

    python test_gemini.py

This bypasses app.py's try/except (which silently falls back to the JSON
pool on ANY failure) so you see the real error if there is one: wrong API
key, wrong model name, network/firewall block, etc.

Run this from your project root (same folder as app.py) so the
prompts/templates.py import works, and make sure .streamlit/secrets.toml
has your real gemini_api_key.
"""

import tomllib

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

api_key = secrets.get("gemini_api_key")
if not api_key:
    print("FAIL: no gemini_api_key found in .streamlit/secrets.toml")
    raise SystemExit(1)

print(f"Found gemini_api_key (starts with: {api_key[:6]}...)")

from google import genai

MODEL_NAME = "gemini-3.5-flash"  # must match utils/gemini.py exactly

print(f"Attempting a real call to model: {MODEL_NAME}")
try:
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents="Reply with exactly the word: WORKING",
    )
    print("SUCCESS - Gemini responded:")
    print(resp.text)
except Exception as e:
    print(f"FAIL - {type(e).__name__}: {e}")
    print()
    print("Common causes:")
    print("  - Wrong model name (check https://aistudio.google.com for your available models)")
    print("  - Invalid/expired API key")
    print("  - Network/firewall blocking the request")