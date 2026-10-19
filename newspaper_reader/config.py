from __future__ import annotations

import os
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "web" / "static"

RUNTIME_DIR = Path(os.environ.get("NEWSPAPER_RUNTIME_DIR") or (Path(tempfile.gettempdir()) / "newspaper_reader"))
UPLOAD_DIR = RUNTIME_DIR / "uploads"
OUTPUT_DIR = RUNTIME_DIR / "output"
PREVIEW_DIR = RUNTIME_DIR / "preview"
LIBRARY_DIR = RUNTIME_DIR / "library"

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

TESSERACT_CMD = os.environ.get("TESSERACT_CMD") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR = os.environ.get("TESSDATA_DIR") or r"C:\Program Files\Tesseract-OCR\tessdata"
OCR_LANG = os.environ.get("OCR_LANG") or "chi_sim"

MAX_UPLOAD = 60
MAX_IMAGE_SIDE = 3600
MIN_IMAGE_SIDE = 1200

# PDF target height in points (A4 height = 841.9)
PDF_TARGET_HEIGHT = 841.9
PDF_MAX_WIDTH = 1400.0

MIN_TEXT_CONF = 35
MIN_LINE_CHARS = 2
MIN_FONT_PT = 3.5
MAX_FONT_PT = 120.0

PHOTO_MIN_AREA_RATIO = 0.006
PHOTO_MIN_SIDE = 60
PHOTO_TEXT_OVERLAP = 0.55

DEFAULT_BG_OPACITY = 0.055

# reading / output
DEFAULT_SCAN_STYLE = "color"
DEFAULT_OUTPUT_MODE = "scan"    # keep the picture (enhanced), like a scanner app
DEFAULT_CLARITY = "high"
SCAN_JPEG_QUALITY = 95          # embedded page images
SCAN_JPEG_SUBSAMPLING = 0       # 4:4:4 - keeps text/line edges crisp

# reading history (documents kept on this device until the user deletes them)
LIBRARY_MAX_DOCS = int(os.environ.get("LIBRARY_MAX_DOCS") or 20)
PAGE_RENDER_WIDTH = 1600        # reader page image width (px)
PAGE_RENDER_MIN = 640
PAGE_RENDER_MAX = 2400

JOB_TTL_SECONDS = 6 * 3600


def ensure_dirs() -> None:
    for d in (RUNTIME_DIR, UPLOAD_DIR, OUTPUT_DIR, PREVIEW_DIR, LIBRARY_DIR):
        d.mkdir(parents=True, exist_ok=True)
