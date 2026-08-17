"""job_store.py — tracks background scan jobs so the client can poll
status instead of blocking on one long request. In-memory only: fine
for a single-process dev/demo deployment; jobs are lost on restart,
but completed scans are already persisted separately in history_store.
"""

import threading
import time

_lock = threading.Lock()
_jobs = {}  # job_id -> {"status": "processing"|"done"|"error", "result": dict|None, "error": str|None, "created_at": float}

STALE_AFTER_SECONDS = 3600  # drop finished job records after an hour to bound memory


def create(job_id):
    with _lock:
        _jobs[job_id] = {"status": "processing", "result": None, "error": None, "created_at": time.time()}


def set_done(job_id, result):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["result"] = result


def set_error(job_id, error_message):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = error_message


def get(job_id):
    with _lock:
        _cleanup()
        return dict(_jobs[job_id]) if job_id in _jobs else None


def _cleanup():
    now = time.time()
    stale = [jid for jid, j in _jobs.items() if j["status"] != "processing" and now - j["created_at"] > STALE_AFTER_SECONDS]
    for jid in stale:
        del _jobs[jid]
