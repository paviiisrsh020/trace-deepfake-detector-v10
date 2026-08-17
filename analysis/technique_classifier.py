"""
technique_classifier.py
------------------------
Classifies WHAT KIND of manipulation the forensic evidence is most
consistent with, based on which signal dominates across the most
suspicious frames. This is a heuristic category inferred from signal
patterns - not identification of a specific tool/model. It is honest
about uncertainty: if no signal clearly dominates, it says so rather
than forcing a guess.

Rationale for each mapping is a plain extension of what each signal
measures (see video_forensics.py docstrings):
- boundary-blend dominant  -> splice/face-swap seam
- frequency-artifact dominant, applies broadly -> full synthetic generation
- noise-residual dominant, localized           -> retouching / inpainting
- ELA dominant                                  -> recompression after edit
"""

DOMINANCE_THRESHOLD = 0.30  # out of ~0.25 baseline (4 signals) - needs to clearly lead


LABELS = {
    "blend": (
        "Face-swap / splicing",
        "Boundary-blend and compression artifacts dominate the evidence — consistent with a real "
        "face being swapped or spliced onto the footage, rather than a fully generated face.",
    ),
    "freq": (
        "Full synthetic generation",
        "Frequency-domain artifacts dominate fairly uniformly across the face — consistent with a "
        "fully AI-generated face (GAN/diffusion-style output) rather than an edited real one.",
    ),
    "noise": (
        "Localized retouching / inpainting",
        "Noise-residual inconsistency dominates in specific patches — consistent with localized "
        "retouching or inpainting rather than a full face replacement.",
    ),
    "ela": (
        "Re-encoding / recompression artifact",
        "Error-level analysis dominates — consistent with the frame being recompressed after "
        "editing, a common side-effect of most manipulation pipelines.",
    ),
}

MIXED = (
    "Mixed / inconclusive pattern",
    "No single forensic signal clearly dominates — evidence is spread across multiple indicators, "
    "or this may be a borderline case. Treat the technique category as low-confidence.",
)


def classify(avg_signals):
    """avg_signals: dict with keys ela, noise_inconsistency, frequency_artifact, boundary_blend
    (already averaged across the most suspicious frames)."""
    scores = {
        "ela": avg_signals.get("ela", 0),
        "noise": avg_signals.get("noise_inconsistency", 0),
        "freq": avg_signals.get("frequency_artifact", 0),
        "blend": avg_signals.get("boundary_blend", 0),
    }
    total = sum(scores.values()) + 1e-6
    dominant = max(scores, key=scores.get)
    dominance_ratio = scores[dominant] / total

    if dominance_ratio < DOMINANCE_THRESHOLD:
        label, desc = MIXED
    else:
        label, desc = LABELS[dominant]

    return {
        "technique": label,
        "technique_desc": desc,
        "dominant_signal": dominant if dominance_ratio >= DOMINANCE_THRESHOLD else None,
        "dominance_ratio": round(float(dominance_ratio), 3),
    }
