"""
ocr.py
──────
EasyOCR wrapper for license plate text extraction.

Changes vs original:
  • _preprocess now uses the enhanced pipeline from video_pipeline
    (2× upscale → sharpen → CLAHE → conditional adaptive threshold)
    instead of just bilateralFilter + equalizeHist, which loses
    detail on small video-frame crops.
  • country is read from COUNTRY_CONFIG instead of hardcoded "IN"
  • EasyOCR reader is a module-level lazy singleton (unchanged)
  • read_plate now tries both the enhanced crop AND a fallback
    (inverted image) when the first attempt returns empty — helps
    with white-text-on-dark-background plates common in India.
"""

import cv2
import numpy as np
from app.detector.plate_postprocess import apply_plate_syntax
from app.config import COUNTRY_CONFIG

_easy_reader = None


def get_easy_reader():
    global _easy_reader
    if _easy_reader is None:
        import easyocr
        print("[LAZY LOAD] Initializing EasyOCR ...")
        _easy_reader = easyocr.Reader(["en"], gpu=False)
    return _easy_reader


class PlateOCR:
    def __init__(self):
        print("[INIT] PlateOCR lightweight init")

    # ── Public API ────────────────────────────────────────────────────────

    def read_plate(self, plate_img: np.ndarray) -> tuple[str, float]:
        if plate_img is None or plate_img.size == 0:
            return "", 0.0

        reader = get_easy_reader()

        # First attempt: standard enhanced crop
        processed = self._preprocess(plate_img)
        text, conf = self._run_ocr(reader, processed)

        # Second attempt: invert colours (handles dark bg / light text plates)
        if not text:
            inverted = cv2.bitwise_not(processed)
            text, conf = self._run_ocr(reader, inverted)

        return text, conf

    # ── Internal ──────────────────────────────────────────────────────────

    def _run_ocr(self, reader, img: np.ndarray) -> tuple[str, float]:
        results = reader.readtext(img)
        if not results:
            return "", 0.0

        # Take the highest-confidence result
        results.sort(key=lambda x: x[2], reverse=True)
        raw_text = results[0][1]
        conf     = float(results[0][2])

        text = self._clean(raw_text)
        return text, conf

    def _clean(self, text: str) -> str:
        text = "".join(c for c in text.upper() if c.isalnum())
        country = COUNTRY_CONFIG.get()          # ← reads live setting, not hardcoded
        return apply_plate_syntax(text, country=country)

    def _preprocess(self, img: np.ndarray) -> np.ndarray:
        """
        Video-optimised plate preprocessing pipeline:
          1. Convert to grayscale
          2. 2× upscale (critical for distant / small plates)
          3. Unsharp-mask sharpening
          4. CLAHE for uneven / night lighting
          5. Adaptive threshold fallback for very dark plates
          6. Light bilateral denoising
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Step 2 — upscale
        h, w = gray.shape[:2]
        target_h = max(64, h * 2)
        scale = target_h / h
        gray = cv2.resize(gray, (int(w * scale), target_h),
                          interpolation=cv2.INTER_CUBIC)

        # Step 3 — sharpen
        kernel = np.array([[0, -1, 0],
                            [-1, 5, -1],
                            [0, -1, 0]], dtype=np.float32)
        gray = cv2.filter2D(gray, -1, kernel)

        # Step 4 — CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        gray = clahe.apply(gray)

        # Step 5 — adaptive threshold only for very dark images
        if gray.mean() < 80:
            gray = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=15,
                C=4,
            )

        # Step 6 — light denoise
        gray = cv2.bilateralFilter(gray, 5, 50, 50)

        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)