"""
url_downloader.py
------------------
Downloads a video from a shared link (YouTube, TikTok, Instagram, X,
Facebook, etc.) using yt-dlp so it can be scanned the same way as an
uploaded file. yt-dlp handles the wide variety of source-site formats;
we force mp4 output so the rest of the pipeline (which expects a
standard container) doesn't need to care where the video came from.

NOTE: requires internet access at runtime (this feature was written
without the ability to test a live download in the build sandbox - see
project README). Standard yt-dlp usage, well-documented and widely
used, so it should work as-is once run somewhere with internet access.
"""

import os

MAX_FILESIZE = 200 * 1024 * 1024


class DownloadError(Exception):
    pass


def download_video(url, out_dir, job_id, max_duration_seconds=600):
    try:
        import yt_dlp
    except ImportError:
        raise DownloadError(
            "Link-scanning requires the 'yt-dlp' package, which isn't installed. "
            "Run: pip install yt-dlp"
        )

    out_template = os.path.join(out_dir, f"{job_id}.%(ext)s")

    ydl_opts = {
        "format": "mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "merge_output_format": "mp4",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "max_filesize": MAX_FILESIZE,
        "socket_timeout": 20,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration")
            if duration and duration > max_duration_seconds:
                raise DownloadError(
                    f"Video is {int(duration/60)} min long — please use a clip under "
                    f"{max_duration_seconds//60} minutes."
                )
            ydl.download([url])
    except DownloadError:
        raise
    except Exception as e:
        raise DownloadError(f"Couldn't download this link: {str(e)[:200]}")

    expected_path = os.path.join(out_dir, f"{job_id}.mp4")
    if os.path.exists(expected_path):
        return expected_path

    # yt-dlp occasionally keeps a different extension despite merge_output_format
    for fname in os.listdir(out_dir):
        if fname.startswith(job_id):
            return os.path.join(out_dir, fname)

    raise DownloadError("Download finished but the output file could not be found.")
