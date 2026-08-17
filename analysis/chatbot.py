"""
chatbot.py
----------
Chat assistant for the dashboard. Uses Groq's free API for real,
open-ended answers when GROQ_API_KEY is set as an environment variable.
Falls back automatically to a local keyword-matched FAQ bot when no key
is present, or if the Groq request fails for any reason (network,
rate limit, etc.) - so the chat never breaks even without a key.

SETTING UP GROQ (free, no card required)
------------------------------------------
1. Go to https://console.groq.com , sign up (Google login works)
2. Create an API key
3. Set it as an environment variable before running the app:

     Windows (PowerShell):  $env:GROQ_API_KEY = "your-key-here"
     Mac/Linux:              export GROQ_API_KEY="your-key-here"

   Or add it as an Environment Variable in Render's dashboard when
   deployed, so it's set every time the server starts.
"""

import os
import re
import json
import urllib.request
import urllib.error

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile")

SYSTEM_PROMPT = (
    "You are the assistant embedded in TRACE, a deepfake video detection dashboard. "
    "You answer questions about how the tool works: it samples video frames, detects faces, "
    "scores four forensic signals (ELA/error-level-analysis, noise-residual inconsistency, "
    "frequency-domain artifacts, boundary-blend seam analysis), combines them into a heatmap "
    "and a per-frame manipulation score, and separately analyses the audio track's spectrogram. "
    "Scores above ~42% are labelled likely-altered. This is a classical signal-analysis baseline, "
    "not a trained deep-learning classifier, so it should be described as a first-pass indicator, "
    "not a guaranteed verdict. Keep answers short (2-4 sentences), clear, and non-technical unless "
    "the user asks for technical depth."
)

FAQ_RULES = [
    (["heatmap", "colour", "color", "jet"],
     "The heatmap uses a jet colour scale — red/yellow marks where the forensic signals scored "
     "highest, meaning strongest evidence of alteration in that area. Blue/green looks normal."),
    (["yellow box", "bounding box", "sub box", "which part", "where was it edited", "where is it edited"],
     "The yellow boxes mark the specific sub-regions where the heatmap crossed the suspicion "
     "threshold — the most likely altered areas, not just 'somewhere in the face'."),
    (["ela", "error level"],
     "ELA re-compresses the frame and diffs it against the original — spliced or generated "
     "regions often carry a different compression history, so they light up under ELA."),
    (["noise residual", "noise"],
     "Noise-residual analysis compares local sensor-noise levels — blended or generated regions "
     "are often unnaturally smooth or mismatched compared to the rest of the frame."),
    (["frequency", "fft", "artifact"],
     "The frequency-artifact signal inspects the 2D frequency spectrum for periodic or unnatural "
     "patterns that GAN/diffusion-generated content often leaves behind."),
    (["boundary", "blend", "seam"],
     "Boundary-blend scoring checks for a gradient irregularity right at the edge of the detected "
     "face — a common giveaway of face-swap splicing."),
    (["score", "percentage", "percent", "confidence", "altered"],
     "The score reflects how strongly the forensic signals suggest alteration — combined from "
     "video and audio. Above ~42% is labelled likely-altered."),
    (["accurate", "accuracy", "reliable", "trust", "wrong"],
     "This baseline uses classical forensic analysis, not a trained deep-learning classifier — "
     "treat it as a first-pass indicator, especially on low-resolution or heavily compressed clips."),
    (["audio", "spectrogram", "sound", "voice"],
     "The audio pass extracts the track with ffmpeg, builds a spectrogram, and scores roll-off "
     "naturalness, frame-to-frame discontinuity, and spectral flatness."),
    (["hi", "hello", "hey"],
     "Hey! Ask me about the heatmap, the score, or how the detection works."),
]
FALLBACK = "I can help with questions about the heatmap, the score, the signals, or how the tool works."


def _match_faq(message):
    msg = message.lower()
    for keywords, answer in FAQ_RULES:
        for kw in keywords:
            if kw in msg:
                return answer
    return None


def _call_groq(message, history=None):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-6:])
    messages.append({"role": "user", "content": message})

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": messages,
        "max_tokens": 300,
        "temperature": 0.4,
    }).encode("utf-8")

    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '').strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()


def get_reply(message, history=None):
    message = (message or "").strip()
    if not message:
        return "Ask me anything about how the detector works, the heatmap, or the score."

    if os.environ.get("GROQ_API_KEY", "").strip():
        try:
            return _call_groq(message, history)
        except Exception:
            pass  # silent fallback to FAQ bot below

    matched = _match_faq(message)
    return matched or FALLBACK
