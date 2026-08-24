"""Lists every voice on the account with its category, so you can tell
free "premade" voices apart from Voice Library voices that need a paid
plan to use over the API (the 402 error we just hit)."""
from dotenv import load_dotenv
import os

load_dotenv()

from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

for v in client.voices.get_all().voices:
    free = "FREE (premade)" if v.category == "premade" else f"CHECK — category={v.category}"
    print(f"{v.voice_id}  {v.name:<20}  {free}")