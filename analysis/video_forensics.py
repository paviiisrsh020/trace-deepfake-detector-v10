"""
video_forensics.py
-------------------
Baseline visual manipulation-detection engine using classical, fully
explainable forensic signals (no trained model required): Error Level
Analysis, noise-residual inconsistency, frequency-domain artifact
scoring, and boundary-blend analysis.

CALIBRATION NOTE
-----------------
Scores combine signals with a mean+max blend rather than a plain
average: a single strong forensic signal (e.g. a sharp frequency-domain
anomaly) is treated as meaningful evidence even when the other three
signals look normal, instead of being diluted into a low average. This
trades some false positives for fewer missed detections, which is the
safer failure mode for a baseline detector.

PLUG-IN POINT FOR A TRAINED MODEL
-----------------------------------
Once you train a CNN (e.g. ResNet-50) on FaceForensics++, wire it into
`classify_frame_with_model()` below and set USE_TRAINED_MODEL = True.
Its prediction will then replace the heuristic score entirely.
"""

import cv2
import numpy as np
import io
from PIL import Image

USE_TRAINED_MODEL = False

FAKE_THRESHOLD = 0.55  # avoid calling borderline/noisy footage fake by default

FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def extract_frames(video_path, max_frames=40):
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    if total <= 0:
        cap.release()
        return [], fps

    indices = np.linspace(0, total - 1, min(max_frames, total)).astype(int)
    frames = []
    idx_set = set(indices.tolist())
    i = 0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if i in idx_set:
            frames.append((i, frame))
        i += 1
    cap.release()
    return frames, fps


MAX_FACES_PER_FRAME = 5  # cap to bound compute cost on crowded frames


def detect_faces(frame_bgr):
    """Returns a list of bboxes for all detected faces (largest first),
    capped at MAX_FACES_PER_FRAME."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    faces = FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    if len(faces) == 0:
        return []
    faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)[:MAX_FACES_PER_FRAME]
    bboxes = []
    for (x, y, w, h) in faces:
        pad = int(0.15 * w)
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1 = min(frame_bgr.shape[1], x + w + pad)
        y1 = min(frame_bgr.shape[0], y + h + pad)
        bboxes.append((x0, y0, x1, y1))
    return bboxes


def error_level_analysis(frame_bgr, quality=90):
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    recompressed = np.array(Image.open(buf).convert("RGB"))
    diff = np.abs(rgb.astype(np.int16) - recompressed.astype(np.int16))
    return diff.sum(axis=2).astype(np.float32)


def noise_residual_map(frame_bgr):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    residual = gray - blurred
    return cv2.boxFilter(residual ** 2, -1, (9, 9))


def frequency_artifact_map(face_crop_gray, tile=32):
    h, w = face_crop_gray.shape
    heat = np.zeros((h, w), dtype=np.float32)
    step = max(8, tile // 2)
    for y in range(0, h - tile + 1, step):
        for x in range(0, w - tile + 1, step):
            patch = face_crop_gray[y:y + tile, x:x + tile].astype(np.float32)
            f = np.fft.fftshift(np.fft.fft2(patch))
            mag = np.abs(f)
            total = mag.sum() + 1e-6
            cy, cx = tile // 2, tile // 2
            r = tile // 4
            low_mask = np.zeros_like(mag)
            low_mask[cy - r:cy + r, cx - r:cx + r] = 1
            high_energy_ratio = (mag * (1 - low_mask)).sum() / total
            heat[y:y + tile, x:x + tile] = np.maximum(heat[y:y + tile, x:x + tile], high_energy_ratio)
    return heat


def boundary_blend_score(frame_bgr, bbox):
    x0, y0, x1, y1 = bbox
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    face = gray[y0:y1, x0:x1]
    if face.size == 0:
        return 0.0
    edges = cv2.Laplacian(face, cv2.CV_64F)
    h, w = face.shape
    ring = int(0.12 * min(h, w)) or 1
    mask = np.zeros_like(face, dtype=bool)
    mask[:ring, :] = mask[-ring:, :] = True
    mask[:, :ring] = mask[:, -ring:] = True
    ring_energy = np.abs(edges[mask]).mean() if mask.any() else 0
    interior_energy = np.abs(edges[~mask]).mean() if (~mask).any() else 1e-6
    return float(ring_energy / (interior_energy + 1e-6))


def classify_frame_with_model(face_crop_bgr):
    """Integration point for a trained CNN. Example once TensorFlow +
    weights are available:

        from tensorflow.keras.models import load_model
        _model = load_model("models/resnet50_deepfake.h5")

        def classify_frame_with_model(face_crop_bgr):
            img = cv2.resize(face_crop_bgr, (224, 224)).astype("float32") / 255.0
            return float(_model.predict(img[None, ...], verbose=0)[0][0])
    """
    if not USE_TRAINED_MODEL:
        return None
    raise NotImplementedError("Wire in your trained model here.")


def analyze_face(frame_bgr, bbox):
    """Analyze a single detected face region given its bbox."""
    x0, y0, x1, y1 = bbox
    face_crop = frame_bgr[y0:y1, x0:x1]
    face_gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)

    model_score = classify_frame_with_model(face_crop)

    ela_full = error_level_analysis(frame_bgr)
    ela_face = ela_full[y0:y1, x0:x1]
    ela_norm = ela_face / (ela_face.max() + 1e-6)

    noise_full = noise_residual_map(frame_bgr)
    noise_face = noise_full[y0:y1, x0:x1]
    med = np.median(noise_face)
    noise_incon = np.abs(noise_face - med)
    noise_incon = noise_incon / (noise_incon.max() + 1e-6)

    freq_face = frequency_artifact_map(face_gray)
    freq_norm = (freq_face - freq_face.min()) / (freq_face.max() - freq_face.min() + 1e-6)

    blend = boundary_blend_score(frame_bgr, bbox)
    blend_score = float(np.clip((blend - 1.0) / 2.0, 0, 1))

    h, w = face_gray.shape
    ela_r = cv2.resize(ela_norm, (w, h))
    noise_r = cv2.resize(noise_incon, (w, h))
    freq_r = cv2.resize(freq_norm, (w, h))

    heatmap = 0.35 * ela_r + 0.30 * noise_r + 0.35 * freq_r
    heatmap = heatmap / (heatmap.max() + 1e-6)

    ela_sig = float(np.clip(ela_r.mean() * 2.2, 0, 1))
    noise_sig = float(np.clip(noise_r.mean() * 2.2, 0, 1))
    freq_sig = float(np.clip(freq_r.mean() * 1.7, 0, 1))
    signals = [ela_sig, noise_sig, freq_sig, blend_score]

    # Use a conservative blend. A single noisy forensic signal should not
    # dominate the whole decision, which was causing ordinary compressed
    # videos to be labelled fake.
    weighted_avg = 0.30 * ela_sig + 0.25 * noise_sig + 0.25 * freq_sig + 0.20 * blend_score
    strongest = max(signals)
    heuristic_score = float(np.clip(0.75 * weighted_avg + 0.25 * strongest, 0, 1))

    final_score = model_score if model_score is not None else heuristic_score

    hm8 = (heatmap * 255).astype(np.uint8)
    hm8 = cv2.GaussianBlur(hm8, (9, 9), 0)
    _, thresh = cv2.threshold(hm8, int(0.6 * 255), 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    sub_boxes = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < 0.008 * w * h:
            continue
        cx, cy, cw, ch = cv2.boundingRect(c)
        sub_boxes.append({"x": int(x0 + cx), "y": int(y0 + cy), "w": int(cw), "h": int(ch)})
    sub_boxes = sorted(sub_boxes, key=lambda b: b["w"] * b["h"], reverse=True)[:4]

    return {
        "bbox": {"x": int(x0), "y": int(y0), "w": int(x1 - x0), "h": int(y1 - y0)},
        "score": final_score,
        "heatmap": heatmap,
        "sub_boxes": sub_boxes,
        "signals": {
            "ela": ela_sig,
            "noise_inconsistency": noise_sig,
            "frequency_artifact": freq_sig,
            "boundary_blend": blend_score,
        },
    }


def analyze_frame(frame_bgr):
    """Detects all faces in the frame and analyzes each one. Returns a
    dict with a `faces` list plus convenience top-level fields for the
    most suspicious face (the one driving the frame's overall score)."""
    bboxes = detect_faces(frame_bgr)
    if not bboxes:
        return None

    faces = [analyze_face(frame_bgr, bbox) for bbox in bboxes]
    primary_idx = max(range(len(faces)), key=lambda i: faces[i]["score"])

    return {
        "faces": faces,
        "primary_face_index": primary_idx,
        "score": faces[primary_idx]["score"],  # most suspicious face drives the frame score
    }


def colorize_heatmap(heatmap):
    hm8 = (np.clip(heatmap, 0, 1) * 255).astype(np.uint8)
    colored = cv2.applyColorMap(hm8, cv2.COLORMAP_JET)
    return cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)


def analyze_video(video_path, max_frames=24, progress_cb=None):
    frames, fps = extract_frames(video_path, max_frames=max_frames)
    results = []
    for i, (frame_idx, frame) in enumerate(frames):
        r = analyze_frame(frame)
        if r is not None:
            r["frame_index"] = int(frame_idx)
            r["timestamp"] = float(frame_idx / fps) if fps else 0.0
            results.append(r)
        if progress_cb:
            progress_cb(i + 1, len(frames))
    return results, fps
