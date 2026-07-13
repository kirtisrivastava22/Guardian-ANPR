import cv2
import numpy as np
from app.detector.plate_postprocess import apply_plate_syntax
from app.config import COUNTRY_CONFIG

_easy_reader = None


def get_easy_reader():
    global _easy_reader
    if _easy_reader is None:
        import easyocr
        print("[LAZY LOAD] Initializing EasyOCR...")
        _easy_reader = easyocr.Reader(["en"], gpu=False)
    return _easy_reader


class PlateOCR:
    def __init__(self):
        print("[INIT] PlateOCR lightweight init")

    def read_plate(self, plate_img: np.ndarray) -> tuple[str, float]:
        if plate_img is None or plate_img.size == 0:
            return "", 0.0

        reader = get_easy_reader()

        # Try normal orientation
        text, conf = self._run_ocr(reader, plate_img)

        # Try inverted (handles white-on-dark plates)
        if not text:
            inverted    = cv2.bitwise_not(plate_img)
            text, conf  = self._run_ocr(reader, inverted)

        return text, conf

    def _run_ocr(self, reader, img: np.ndarray) -> tuple[str, float]:
        try:
            results = reader.readtext(img)
        except Exception as e:
            print(f"[OCR ERROR] {e}")
            return "", 0.0

        if not results:
            return "", 0.0

        # Highest confidence result first
        results.sort(key=lambda x: x[2], reverse=True)
        raw  = results[0][1]
        conf = float(results[0][2])

        text = self._clean(raw)
        return text, conf

    def _clean(self, text: str) -> str:
        text    = "".join(c for c in text.upper() if c.isalnum())
        country = COUNTRY_CONFIG.get()
        # apply_plate_syntax now returns "" for garbage strings
        return apply_plate_syntax(text, country=country)

    def _preprocess(self, img: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        h, w = gray.shape[:2]
        target_h = max(64, h * 2)
        scale    = target_h / h
        gray     = cv2.resize(gray, (int(w * scale), target_h),
                              interpolation=cv2.INTER_CUBIC)

        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        gray   = cv2.filter2D(gray, -1, kernel)

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        gray  = clahe.apply(gray)

        if gray.mean() < 80:
            gray = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 15, 4,
            )

        gray = cv2.bilateralFilter(gray, 5, 50, 50)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)