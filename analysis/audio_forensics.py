"""
audio_forensics.py
-------------------
Baseline audio manipulation-detection engine: extracts the audio track
via ffmpeg, builds a spectrogram, and scores it on roll-off naturalness,
frame-to-frame discontinuity (a splice cue), and spectral flatness.
"""

import subprocess
import numpy as np
from scipy.io import wavfile
from scipy.signal import spectrogram as sp_spectrogram

USE_TRAINED_MODEL = False
FAKE_THRESHOLD = 0.42


def extract_audio(video_path, out_wav_path, sr=16000):
    cmd = ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "wav", out_wav_path]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode == 0


def build_spectrogram(wav_path):
    sr, data = wavfile.read(wav_path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = data.astype(np.float32)
    if np.abs(data).max() > 0:
        data = data / np.abs(data).max()
    f, t, Sxx = sp_spectrogram(data, fs=sr, nperseg=512, noverlap=384)
    Sxx_db = 10 * np.log10(Sxx + 1e-10)
    return f, t, Sxx_db, sr, data


def classify_spectrogram_with_model(Sxx_db):
    if not USE_TRAINED_MODEL:
        return None
    raise NotImplementedError("Wire in your trained audio model here.")


def analyze_audio(video_path, work_wav_path):
    ok = extract_audio(video_path, work_wav_path)
    if not ok:
        return None

    f, t, Sxx_db, sr, waveform = build_spectrogram(work_wav_path)
    model_score = classify_spectrogram_with_model(Sxx_db)

    nyquist_idx = len(f)
    high_band = Sxx_db[int(nyquist_idx * 0.75):, :]
    high_band_var = float(np.var(high_band))
    rolloff_score = float(np.clip(1.0 - (high_band_var / 40.0), 0, 1))

    frame_diffs = np.diff(Sxx_db, axis=1)
    discontinuity = float(np.percentile(np.abs(frame_diffs), 99))
    discontinuity_score = float(np.clip(discontinuity / 60.0, 0, 1))

    power = 10 ** (Sxx_db / 10)
    geo_mean = np.exp(np.mean(np.log(power + 1e-12), axis=0))
    arith_mean = np.mean(power, axis=0) + 1e-12
    flatness = geo_mean / arith_mean
    flatness_score = float(np.clip(np.mean(flatness) * 4, 0, 1))

    signals = [rolloff_score, discontinuity_score, flatness_score]
    weighted_avg = 0.4 * rolloff_score + 0.35 * discontinuity_score + 0.25 * flatness_score
    heuristic_score = float(np.clip(0.6 * weighted_avg + 0.4 * max(signals), 0, 1))
    final_score = model_score if model_score is not None else heuristic_score

    per_bin = np.abs(Sxx_db - np.median(Sxx_db, axis=1, keepdims=True)).mean(axis=0)
    per_bin = (per_bin - per_bin.min()) / (per_bin.max() - per_bin.min() + 1e-6)

    return {
        "score": final_score,
        "signals": {
            "rolloff_naturalness": rolloff_score,
            "discontinuity": discontinuity_score,
            "spectral_flatness": flatness_score,
        },
        "spectrogram": Sxx_db,
        "freqs": f,
        "times": t,
        "timeline": per_bin.tolist(),
        "duration": float(t[-1]) if len(t) else 0.0,
    }
