"""
metadata_forensics.py
----------------------
Checks the uploaded file's own embedded metadata for an AI-provenance
declaration - the same thing Samsung Gallery / Google Photos show as
"Content Credentials". This is NOT signal analysis: it only surfaces a
label if the exporting tool voluntarily wrote one into the file (per
the C2PA standard, or a vendor-specific tag).

HONESTY NOTE
------------
Absence of this metadata proves nothing - most video pipelines
(screen recording, re-encoding, simple re-uploading) strip it, so most
files - real or fake - will show "not found". Presence is meaningful
signal (a declared AI tool); absence is not evidence of authenticity.
Never present "not found" as "this is real".
"""

import subprocess
import json

# Keys/value fragments associated with AI-generation disclosure standards
# and common tool exports. Matching is case-insensitive substring search
# across both metadata keys and values.
DISCLOSURE_MARKERS = [
    "c2pa", "content credentials", "ai-generated", "ai generated",
    "generative ai", "digitalsourcetype", "trainedalgorithmicmedia",
    "compositewithtrainedalgorithmicmedia", "synthetic",
]

KNOWN_TOOL_HINTS = [
    "tiktok", "capcut", "dall-e", "dall·e", "midjourney", "runway",
    "sora", "veo", "stable diffusion", "adobe firefly", "pika labs",
    "kling", "luma", "openai", "google ai", "gemini",
]


def probe_metadata(video_path):
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", video_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
        )
        if proc.returncode != 0:
            return None
        return json.loads(proc.stdout.decode("utf-8", errors="ignore"))
    except Exception:
        return None


def check_ai_disclosure(video_path):
    """Returns dict: {found: bool, matches: [...], raw_tags: {...}}"""
    data = probe_metadata(video_path)
    if not data:
        return {"found": False, "matches": [], "checked": False}

    all_tags = {}
    fmt_tags = data.get("format", {}).get("tags", {}) or {}
    all_tags.update({f"format.{k}": v for k, v in fmt_tags.items()})
    for i, stream in enumerate(data.get("streams", [])):
        for k, v in (stream.get("tags") or {}).items():
            all_tags[f"stream{i}.{k}"] = v

    matches = []
    for key, value in all_tags.items():
        haystack = f"{key} {value}".lower()
        for marker in DISCLOSURE_MARKERS:
            if marker in haystack:
                matches.append({"field": key, "value": str(value), "matched": marker, "type": "disclosure"})
                break
        for tool in KNOWN_TOOL_HINTS:
            if tool in haystack:
                matches.append({"field": key, "value": str(value), "matched": tool, "type": "tool_hint"})
                break

    return {
        "found": len(matches) > 0,
        "matches": matches,
        "checked": True,
        "software_tag": fmt_tags.get("software") or fmt_tags.get("encoder"),
    }
