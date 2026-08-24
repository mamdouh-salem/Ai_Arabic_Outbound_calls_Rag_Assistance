"""Quick standalone test: does the ElevenLabs key + voice ID actually work?
Run this on its own before touching app.py. Saves a short Arabic clip as
test_voice.mp3 in the current folder — copy it out of WSL and play it to
judge the accent before wiring anything into the live call.
"""
from dotenv import load_dotenv
import os

load_dotenv()

from elevenlabs.client import ElevenLabs

api_key = os.environ["ELEVENLABS_API_KEY"]
voice_id = os.environ["ELEVENLABS_VOICE_ID"]

client = ElevenLabs(api_key=api_key)

audio = client.text_to_speech.convert(
    text="أهلاً وسهلاً، معاك المساعد الآلي بخصوص شكوى حضرتك.",
    voice_id=voice_id,
    model_id="eleven_multilingual_v2",
)

with open("test_voice.mp3", "wb") as f:
    for chunk in audio:
        f.write(chunk)

print("Saved test_voice.mp3 — copy it out and play it.")
