# TRACE Deepfake Detector — Groq-enabled build

This build fixes the overly aggressive visual heuristic and adds a Groq vision
second opinion to sampled video frames.

## Groq setup

1. Create a Groq API key in the Groq Console.
2. Set `GROQ_API_KEY` in your environment/hosting dashboard. **Do not put the
   real key inside the ZIP or commit it to Git.**
3. Restart the Flask app.

The default vision model is `qwen/qwen3.6-27b`. Groq currently documents this
model as a multimodal model that accepts up to 5 images per request. TRACE
therefore samples frames and sends them in groups of five rather than trying
to upload the whole video as a single vision input.

The detector combines:
- classical ELA/noise/frequency/boundary signals,
- Groq visual review,
- audio analysis when available.

The default fake threshold is now 55% instead of 42%, and the classical score
no longer lets the top third of frames dominate the result. This is intended
to reduce false "FAKE" calls on ordinary compressed/filtered real videos.

## Run

```bash
pip install -r requirements.txt
export GROQ_API_KEY="your-key"
python app.py
```

On Windows PowerShell:

```powershell
$env:GROQ_API_KEY="your-key"
python app.py
```

If no Groq key is present, the app still runs with the classical fallback.
