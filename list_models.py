"""List the actual models available to your API key - run this to get the
real model name instead of guessing."""

import tomllib
from google import genai

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

client = genai.Client(api_key=secrets["gemini_api_key"])

print("Models available to your key that support generateContent:\n")
for model in client.models.list():
    if "generateContent" in (model.supported_actions or []):
        print(f"  {model.name}")