"""
groq_video.py
-------------
Optional Groq vision second-opinion for video frames.

Groq vision models accept images, not raw video, so TRACE samples the same
frames used by the forensic engine and sends them in batches of up to five.
The AI result is a secondary signal; it never gets to override metadata or
claim certainty from appearance alone.
"""
import os
import json
import base64
import urllib.request
import urllib.error
import cv2

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")

SYSTEM_PROMPT = """
You are the visual second-opinion component of TRACE, a deepfake video detector.
You are reviewing sampled video frames for visible signs that a face or scene
may have been AI-generated, face-swapped, composited, or manipulated.

IMPORTANT:
- Do not decide "fake" just because a person looks unusual, attractive,
  blurry, low quality, filtered, compressed, or because you cannot identify them.
- Look for visible temporal/visual inconsistencies across the supplied frames:
  facial geometry changes, warped edges, inconsistent identity, unnatural skin
  texture, mouth/teeth/eyes inconsistencies, hair/ear/jaw artifacts, repeated
  patterns, compositing seams, impossible lighting, or obvious generation errors.
- A normal-looking real video should be marked REAL unless there is concrete
  visible evidence of manipulation.
- If the frames are too poor to judge, use UNCERTAIN.
- This is not proof. Return a calibrated likelihood/risk, not a statement of
  certainty.
"""

def _key():
    return os.environ.get("GROQ_API_KEY", "").strip()

def _data_url(frame_bgr, max_side=768, quality=82):
    h, w = frame_bgr.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1:
        frame_bgr = cv2.resize(frame_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return None
    encoded = base64.b64encode(buf.tobytes()).decode("ascii")
    return "data:image/jpeg;base64," + encoded

def _call(images):
    if not _key():
        return None
    content = [{
        "type": "text",
        "text": (
            "Review these sampled frames from ONE video. They are in chronological "
            "order. Return JSON only with this exact shape: "
            '{"frames":[{"index":0,"label":"REAL|FAKE|UNCERTAIN","score":0.0,'
            '"reason":"short evidence"}],"overall_score":0.0,'
            '"overall_label":"REAL|FAKE|UNCERTAIN",'
            '"summary":"one short sentence"}. '
            "score is visual manipulation risk from 0.0 to 1.0. "
            "Use the frame index shown below, starting at 0."
        )
    }]
    for i, image in enumerate(images):
        content.append({"type": "text", "text": f"FRAME {i}"})
        content.append({"type": "image_url", "image_url": {"url": image}})

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": content},
        ],
        "temperature": 0.1,
        "max_completion_tokens": 1200,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    req = urllib.request.Request(
        GROQ_URL, data=payload,
        headers={
            "Authorization": f"Bearer {_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["choices"][0]["message"]["content"]
    return json.loads(text)

def review_video(video_path, frame_indices, max_frames=15):
    """
    Returns a dict or None. Uses up to max_frames evenly spaced sampled frames.
    """
    if not _key() or not frame_indices:
        return None

    selected = list(frame_indices)
    if len(selected) > max_frames:
        picks = [selected[int(i * (len(selected)-1) / (max_frames-1))] for i in range(max_frames)]
        selected = list(dict.fromkeys(picks))

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    wanted = set(selected)
    frames = {}
    i = 0
    while cap.isOpened() and len(frames) < len(wanted):
        ok, frame = cap.read()
        if not ok:
            break
        if i in wanted:
            frames[i] = frame.copy()
        i += 1
    cap.release()

    ordered = [(idx, frames[idx]) for idx in selected if idx in frames]
    if not ordered:
        return None

    all_results = []
    chunk_size = 5
    try:
        for start in range(0, len(ordered), chunk_size):
            chunk = ordered[start:start + chunk_size]
            images = [_data_url(frame) for _, frame in chunk]
            if any(x is None for x in images):
                continue
            result = _call(images)
            if not result:
                continue
            # Map local indices back to actual video frame indices.
            for item in result.get("frames", []):
                try:
                    local_i = int(item.get("index", -1))
                    if 0 <= local_i < len(chunk):
                        item["frame_index"] = int(chunk[local_i][0])
                        item["score"] = max(0.0, min(1.0, float(item.get("score", 0.5))))
                        item["label"] = str(item.get("label", "UNCERTAIN")).upper()
                        all_results.append(item)
                except (TypeError, ValueError):
                    continue

        if not all_results:
            return None

        scores = [x["score"] for x in all_results]
        fake_count = sum(x["label"] == "FAKE" for x in all_results)
        real_count = sum(x["label"] == "REAL" for x in all_results)
        overall_score = sum(scores) / len(scores)
        if fake_count >= max(2, len(all_results) // 2 + 1) and overall_score >= 0.55:
            label = "FAKE"
        elif real_count >= max(2, len(all_results) // 2 + 1) and overall_score <= 0.45:
            label = "REAL"
        else:
            label = "UNCERTAIN"

        return {
            "enabled": True,
            "model": GROQ_MODEL,
            "score": round(overall_score, 4),
            "label": label,
            "frames": all_results,
            "summary": (
                "Groq visual review agrees with the sampled frames."
                if label != "UNCERTAIN"
                else "Groq visual review was mixed or inconclusive."
            ),
        }
    except Exception as exc:
        return {"enabled": False, "error": str(exc)}
