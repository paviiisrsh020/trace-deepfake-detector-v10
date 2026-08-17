import os
import uuid
import secrets
import threading
import traceback
from functools import wraps
from datetime import datetime, timezone

import cv2
import numpy as np
from PIL import Image
from flask import Flask, request, jsonify, send_from_directory, render_template, session, redirect, url_for

from analysis import video_forensics as vf
from analysis import audio_forensics as af
from analysis import chatbot
from analysis import technique_classifier
from analysis import report_generator
from analysis import metadata_forensics
from analysis import url_downloader
from analysis import groq_video
import history_store
import auth_store
import job_store
import email_utils

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
ALLOWED_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_CONTENT_LENGTH = 200 * 1024 * 1024

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
history_store.init_db()
auth_store.init_db()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not signed in."}), 401
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login")
def login_page():
    if session.get("user_id"):
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/reset-password")
def reset_password_page():
    token = request.args.get("token", "")
    return render_template("reset_password.html", token=token)


@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    name = (data.get("name") or "").strip()
    password = data.get("password") or ""
    if not email or not name or not password:
        return jsonify({"error": "Name, email, and password are all required."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    user_id, error = auth_store.create_user(email, name, password)
    if error:
        return jsonify({"error": error}), 400
    session["user_id"] = user_id
    session["user_name"] = name
    threading.Thread(target=email_utils.send_welcome_email, args=(email, name), daemon=True).start()
    return jsonify({"ok": True, "name": name})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    user, error = auth_store.verify_user(email, password)
    if error:
        return jsonify({"error": error}), 400
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return jsonify({"ok": True, "name": user["name"]})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    if not email:
        return jsonify({"error": "Enter your email address."}), 400

    token = auth_store.create_reset_token(email)
    if token:
        reset_url = f"{request.host_url.rstrip('/')}/reset-password?token={token}"
        threading.Thread(
            target=email_utils.send_password_reset_email, args=(email, reset_url), daemon=True
        ).start()

    # Always return the same generic message, whether or not the email exists,
    # so this endpoint can't be used to check which emails have accounts.
    return jsonify({"ok": True, "message": "If that email has an account, a reset link is on its way."})


@app.route("/api/reset-password", methods=["POST"])
def do_reset_password():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    password = data.get("password") or ""
    if not token:
        return jsonify({"error": "Missing reset token."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    ok, error = auth_store.reset_password(token, password)
    if not ok:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


@app.route("/")
@login_required
def index():
    return render_template("index.html", user_name=session.get("user_name", ""))


@app.route("/api/analyze", methods=["POST"])
@login_required
def analyze():
    if "video" not in request.files:
        return jsonify({"error": "No video file uploaded."}), 400
    file = request.files["video"]
    if file.filename == "":
        return jsonify({"error": "Empty filename."}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": f"Unsupported file type '{ext}'."}), 400

    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(RESULTS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    video_path = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")
    file.save(video_path)

    job_store.create(job_id)
    user_id = session.get("user_id")
    filename = file.filename
    thread = threading.Thread(
        target=_run_file_job, args=(job_id, video_path, job_dir, filename, user_id), daemon=True
    )
    thread.start()
    return jsonify({"job_id": job_id, "status": "processing"})


def _run_file_job(job_id, video_path, job_dir, filename, user_id):
    try:
        payload = run_full_analysis(video_path, job_dir, job_id)
        save_to_history(payload, filename, user_id=user_id)
        job_store.set_done(job_id, payload)
    except Exception as e:
        traceback.print_exc()
        job_store.set_error(job_id, f"Analysis failed: {str(e)}")
    finally:
        try:
            os.remove(video_path)
        except OSError:
            pass


@app.route("/api/analyze-url", methods=["POST"])
@login_required
def analyze_url():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "No URL provided."}), 400
    if not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"error": "That doesn't look like a valid URL."}), 400

    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(RESULTS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    job_store.create(job_id)
    user_id = session.get("user_id")
    thread = threading.Thread(
        target=_run_url_job, args=(job_id, url, job_dir, user_id), daemon=True
    )
    thread.start()
    return jsonify({"job_id": job_id, "status": "processing"})


def _run_url_job(job_id, url, job_dir, user_id):
    try:
        video_path = url_downloader.download_video(url, UPLOAD_DIR, job_id)
    except url_downloader.DownloadError as e:
        job_store.set_error(job_id, str(e))
        return
    except Exception as e:
        traceback.print_exc()
        job_store.set_error(job_id, f"Download failed: {str(e)}")
        return

    try:
        payload = run_full_analysis(video_path, job_dir, job_id)
        save_to_history(payload, url, user_id=user_id)
        job_store.set_done(job_id, payload)
    except Exception as e:
        traceback.print_exc()
        job_store.set_error(job_id, f"Analysis failed: {str(e)}")
    finally:
        try:
            os.remove(video_path)
        except OSError:
            pass


@app.route("/api/job/<job_id>", methods=["GET"])
@login_required
def get_job(job_id):
    job = job_store.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found (it may have expired)."}), 404
    if job["status"] == "error":
        return jsonify({"status": "error", "error": job["error"]})
    if job["status"] == "done":
        return jsonify({"status": "done", "result": job["result"]})
    return jsonify({"status": "processing"})


def save_to_history(payload, original_filename, user_id=None):
    thumbnail = None
    if payload.get("frames"):
        best = max(payload["frames"], key=lambda f: f["score"])
        thumbnail = best["image"]
    history_store.add_record(
        job_id=payload["job_id"], filename=original_filename,
        created_at=datetime.now(timezone.utc).isoformat(),
        verdict=payload.get("verdict"), confidence=payload.get("confidence"),
        thumbnail=thumbnail, payload=payload, user_id=user_id,
    )


@app.route("/api/history", methods=["GET"])
@login_required
def get_history():
    return jsonify(history_store.list_records(user_id=session.get("user_id")))


@app.route("/api/history/<job_id>", methods=["GET"])
@login_required
def get_history_item(job_id):
    payload = history_store.get_record(job_id)
    if payload is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(payload)


@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    history = data.get("history", [])
    reply = chatbot.get_reply(message, history)
    return jsonify({"reply": reply})


def explanation_for(pct, verdict):
    if verdict == "FAKE":
        if pct >= 70:
            return "Strong evidence of alteration across multiple forensic signals — this clip is very likely manipulated."
        return "The combined forensic signals and AI review lean toward manipulation, but this is still a probabilistic result."
    else:
        if pct <= 25:
            return "The forensic signals and AI review are consistent with an unedited capture, with little evidence of manipulation."
        return "The evidence leans toward unedited, but some borderline signals were present — treat this as a weaker call."


def run_full_analysis(video_path, job_dir, job_id):
    metadata_check = metadata_forensics.check_ai_disclosure(video_path)
    frame_results, fps = vf.analyze_video(video_path, max_frames=24)
    # Groq is a visual second opinion. It reviews sampled frames, not the raw
    # video stream, because Groq vision accepts image inputs.
    groq_review = groq_video.review_video(
        video_path,
        [r["frame_index"] for r in frame_results],
        max_frames=15,
    )

    frames_payload = []
    for r in frame_results:
        faces_out = [
            {"bbox": f["bbox"], "sub_boxes": f["sub_boxes"], "signals": f["signals"], "score": round(f["score"], 4)}
            for f in r["faces"]
        ]
        frames_payload.append({
            "frame_index": r["frame_index"], "timestamp": round(r["timestamp"], 2),
            "score": round(r["score"], 4), "faces": faces_out,
            "primary_face_index": r["primary_face_index"], "image": None,
        })

    cap = cv2.VideoCapture(video_path)
    idx_to_result = {r["frame_index"]: r for r in frame_results}
    i, saved = 0, {}
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if i in idx_to_result:
            r = idx_to_result[i]
            annotated = render_annotated_frame(frame, r)
            fname = f"frame_{i:06d}.jpg"
            cv2.imwrite(os.path.join(job_dir, fname), annotated, [cv2.IMWRITE_JPEG_QUALITY, 88])
            saved[i] = fname
        i += 1
    cap.release()

    for fp in frames_payload:
        fp["image"] = f"/results/{job_id}/{saved.get(fp['frame_index'], '')}"

    if not frame_results:
        video_score = None
    else:
        scores = np.array([r["score"] for r in frame_results])
        # Keep the classical engine from being driven by only the most
        # suspicious third of frames.
        video_score = float(0.65 * scores.mean() + 0.35 * np.percentile(scores, 75))

    wav_path = os.path.join(job_dir, "audio.wav")
    audio_result = af.analyze_audio(video_path, wav_path)
    audio_payload = None
    if audio_result is not None:
        spec_fname = "spectrogram.png"
        save_spectrogram_image(audio_result["spectrogram"], os.path.join(job_dir, spec_fname))
        audio_payload = {
            "score": round(audio_result["score"], 4), "signals": audio_result["signals"],
            "timeline": audio_result["timeline"], "duration": round(audio_result["duration"], 2),
            "spectrogram_image": f"/results/{job_id}/{spec_fname}",
        }
        try:
            os.remove(wav_path)
        except OSError:
            pass

    groq_score = groq_review.get("score") if groq_review and groq_review.get("enabled") else None

    # When Groq is configured, use it as a second opinion. It gets enough
    # weight to correct obvious classical-forensics false positives, while
    # audio/forensics remain part of the decision.
    if groq_score is not None and video_score is not None and audio_payload is not None:
        final_score = 0.50 * video_score + 0.20 * audio_payload["score"] + 0.30 * groq_score
    elif groq_score is not None and video_score is not None:
        final_score = 0.65 * video_score + 0.35 * groq_score
    elif video_score is not None and audio_payload is not None:
        final_score = 0.80 * video_score + 0.20 * audio_payload["score"]
    elif video_score is not None:
        final_score = video_score
    elif groq_score is not None:
        final_score = groq_score
    elif audio_payload is not None:
        final_score = audio_payload["score"]
    else:
        final_score = None

    verdict, confidence, alteration_pct, explanation = None, None, None, None
    technique = None
    if final_score is not None:
        verdict = "FAKE" if final_score >= vf.FAKE_THRESHOLD else "REAL"
        confidence = final_score if verdict == "FAKE" else 1 - final_score
        alteration_pct = round(final_score * 100, 1)
        explanation = explanation_for(alteration_pct, verdict)

        if verdict == "FAKE" and frame_results:
            scores = np.array([r["score"] for r in frame_results])
            top_k = max(1, len(scores) // 3)
            top_idx = np.argsort(scores)[-top_k:]
            avg_signals = {
                key: float(np.mean([
                    frame_results[i]["faces"][frame_results[i]["primary_face_index"]]["signals"][key]
                    for i in top_idx
                ]))
                for key in ("ela", "noise_inconsistency", "frequency_artifact", "boundary_blend")
            }
            technique = technique_classifier.classify(avg_signals)

    max_faces_in_frame = max((len(r["faces"]) for r in frame_results), default=0)

    return {
        "job_id": job_id, "fps": fps,
        "video_score": round(video_score, 4) if video_score is not None else None,
        "final_score": round(final_score, 4) if final_score is not None else None,
        "alteration_pct": alteration_pct, "explanation": explanation, "technique": technique,
        "metadata_check": metadata_check,
        "verdict": verdict, "confidence": round(confidence, 4) if confidence is not None else None,
        "frames": frames_payload, "audio": audio_payload,
        "num_faces_detected": len(frame_results), "max_faces_in_frame": max_faces_in_frame, "num_frames_sampled": len(frames_payload),
    }


def render_annotated_frame(frame_bgr, result):
    out = frame_bgr.copy()
    for i, face in enumerate(result["faces"]):
        x, y, w, h = face["bbox"]["x"], face["bbox"]["y"], face["bbox"]["w"], face["bbox"]["h"]
        heatmap = face["heatmap"]
        colored = vf.colorize_heatmap(heatmap)
        colored_bgr = cv2.resize(cv2.cvtColor(colored, cv2.COLOR_RGB2BGR), (w, h))
        roi = out[y:y + h, x:x + w]
        if roi.shape[:2] == colored_bgr.shape[:2]:
            out[y:y + h, x:x + w] = cv2.addWeighted(roi, 0.55, colored_bgr, 0.45, 0)
        score = face["score"]
        color = (0, 0, 255) if score >= vf.FAKE_THRESHOLD else (0, 200, 0)
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
        for b in face["sub_boxes"]:
            cv2.rectangle(out, (b["x"], b["y"]), (b["x"] + b["w"], b["y"] + b["h"]), (0, 255, 255), 2)
        prefix = f"P{i+1}: " if len(result["faces"]) > 1 else ""
        label = f"{prefix}{score*100:.0f}% altered"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(out, (x, max(0, y - th - 10)), (x + tw + 10, y), color, -1)
        cv2.putText(out, label, (x + 5, max(15, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    return out


def save_spectrogram_image(Sxx_db, out_path):
    norm = (Sxx_db - Sxx_db.min()) / (Sxx_db.max() - Sxx_db.min() + 1e-6)
    colored = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_MAGMA)
    colored = cv2.flip(colored, 0)
    img = Image.fromarray(cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)).resize((900, 260))
    img.save(out_path)


@app.route("/results/<job_id>/<path:filename>")
@login_required
def serve_result(job_id, filename):
    return send_from_directory(os.path.join(RESULTS_DIR, job_id), filename)


@app.route("/api/report/<job_id>")
@login_required
def download_report(job_id):
    payload = history_store.get_record(job_id)
    if payload is None:
        return jsonify({"error": "Scan not found."}), 404
    job_dir = os.path.join(RESULTS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return jsonify({"error": "Report images are no longer available for this scan."}), 404
    out_path = os.path.join(job_dir, "report.pdf")
    try:
        report_generator.build_report(payload, job_dir, out_path)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Report generation failed: {str(e)}"}), 500
    return send_from_directory(job_dir, "report.pdf", as_attachment=True,
                                download_name=f"trace-report-{job_id}.pdf")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=True)
