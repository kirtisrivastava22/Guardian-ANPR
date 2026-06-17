"""
video_pipeline.py
─────────────────
Detection + OCR pipeline for both single frames (WebSocket streaming)
and full video file processing.

Key fixes vs original:
  1. Model path uses app/model/best.pt (place your best_1_.pt there renamed)
  2. Video-optimised preprocessing: motion-deblur + CLAHE + 2× upscale
  3. plate_buffer counts ints, not appends strings
  4. f-string bug fixed on final log line
  5. mp4v codec replaces H264 (universally supported)
  6. process_license_plate guards against empty OCR text before putText
"""

import cv2
import numpy as np
import os
import logging
from collections import defaultdict
from app.detector.ocr import PlateOCR
from ultralytics import YOLO
import torch

torch.set_grad_enabled(False)

logger = logging.getLogger("lpr")
logger.setLevel(logging.DEBUG)   # set to WARNING in production

# ── Singletons ──────────────────────────────────────────────────────────────

_ocr_engine: PlateOCR | None = None
_model: YOLO | None = None

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "model", "best.pt")

plate_buffer: dict = defaultdict(int)


def get_ocr_engine() -> PlateOCR:
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = PlateOCR()
    return _ocr_engine


def get_model() -> YOLO:
    global _model
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Model not found at {MODEL_PATH}. "
                "Place best.pt (your trained weights) in app/model/"
            )
        logger.info(f"[INIT] Loading YOLO model from {MODEL_PATH}")
        _model = YOLO(MODEL_PATH)
    return _model


# ── Video-frame preprocessing ────────────────────────────────────────────────

def preprocess_for_detection(frame: np.ndarray) -> np.ndarray:
    """
    Light sharpening pass applied to the full frame BEFORE YOLO inference.
    Counteracts the motion blur that's common in dashcam / traffic footage.
    Keep it cheap — this runs on every frame.
    """
    kernel = np.array([[0, -0.5, 0],
                       [-0.5, 3, -0.5],
                       [0, -0.5, 0]], dtype=np.float32)
    sharpened = cv2.filter2D(frame, -1, kernel)
    return sharpened


def preprocess_plate_crop(crop: np.ndarray) -> np.ndarray:
    """
    Aggressive enhancement applied to the small plate crop before OCR.
    Handles:
      • distant plates (tiny, blurry) → 2× upscale + sharpen
      • night / uneven lighting       → CLAHE
      • very dark plates              → adaptive threshold fallback
    """
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Always upscale — plate crops from traffic video are tiny
    h, w = gray.shape[:2]
    target_h = max(64, h * 2)
    scale = target_h / h
    gray = cv2.resize(gray, None, fx=scale, fy=scale,
                      interpolation=cv2.INTER_CUBIC)

    # Sharpen after upscale
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    gray = cv2.filter2D(gray, -1, kernel)

    # CLAHE — fixes uneven lighting without blowing out bright plates
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    gray = clahe.apply(gray)

    # Adaptive threshold only for very dark crops
    if gray.mean() < 80:
        gray = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 15, 4
        )

    # Light bilateral denoise after threshold
    gray = cv2.bilateralFilter(gray, 5, 50, 50)

    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


# ── Core detection ───────────────────────────────────────────────────────────

def detect_license_plate(image: np.ndarray):
    """
    Run YOLO on one frame.  Returns (best_crop, annotated_image, confidence).
    All three are None / original_image / 0.0 when nothing is found.
    """
    model = get_model()

    if image is None or image.size == 0:
        logger.error("[DETECT] Empty image received")
        return None, image, 0.0

    # Light full-frame sharpening to help with motion blur
    proc = preprocess_for_detection(image)

    results = model.predict(
        source=proc,
        imgsz=640,
        conf=0.25,       # raised from 0.15 → fewer FPs from distant objects
        iou=0.35,        # tighter NMS → cleaner detections in crowded scenes
        device="cpu",
        half=False,
        verbose=False,
    )

    if not results:
        return None, image, 0.0

    result = results[0]
    if result.boxes is None or len(result.boxes) == 0:
        logger.debug("[DETECT] No boxes in this frame")
        return None, image, 0.0

    best_plate = None
    best_conf = 0.0
    best_box = None

    for box in result.boxes:
        conf = float(box.conf[0])
        x1, y1, x2, y2 = map(int, box.xyxy[0])

        if x2 <= x1 or y2 <= y1:
            continue
        if (x2 - x1) < 20 or (y2 - y1) < 8:
            continue            # too small to be a real plate

        if conf > best_conf:
            crop = image[y1:y2, x1:x2]   # crop from ORIGINAL (not sharpened)
            if crop.size > 0:
                best_plate = crop
                best_conf = conf
                best_box = (x1, y1, x2, y2)

    if best_plate is None or best_box is None:
        return None, image, 0.0

    x1, y1, x2, y2 = best_box
    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(image, f"{best_conf:.2f}", (x1, max(y1 - 8, 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

    logger.debug(f"[DETECT] Plate found conf={best_conf:.3f} box={best_box}")
    return best_plate, image, best_conf


# ── Full pipeline (detection + OCR) ─────────────────────────────────────────

def process_license_plate(image: np.ndarray):
    """
    Full pipeline: YOLO detection → enhanced crop → OCR.
    Returns (plate_crop, annotated_image, plate_text, confidence).
    plate_text is None when nothing was reliably read.
    """
    plate_crop, annotated, det_conf = detect_license_plate(image)

    if plate_crop is None:
        return None, annotated, None, 0.0

    # Apply video-specific plate enhancement before OCR
    enhanced_crop = preprocess_plate_crop(plate_crop)

    ocr = get_ocr_engine()
    text, ocr_conf = ocr.read_plate(enhanced_crop)

    # Combined confidence — weight detection higher since it's more reliable
    final_conf = 0.65 * det_conf + 0.35 * ocr_conf if text else det_conf

    if text:
        cv2.putText(annotated, text, (10, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv2.LINE_AA)
        logger.info(f"[OCR] '{text}' det={det_conf:.2f} ocr={ocr_conf:.2f} final={final_conf:.2f}")
    else:
        logger.debug(f"[OCR] No text read from plate crop (det_conf={det_conf:.2f})")

    return plate_crop, annotated, text or None, final_conf


# ── Batch video file processing ──────────────────────────────────────────────

def process_video(input_path: str, output_path: str):
    """
    Process a saved video file frame-by-frame.
    Returns (success: bool, detected_plates: list[str]).
    A plate must appear in ≥3 frames before it's counted.
    """
    cap = cv2.VideoCapture(input_path)
    output_path = output_path.rsplit(".", 1)[0] + ".mp4"

    if not cap.isOpened():
        logger.error(f"[VIDEO] Cannot open: {input_path}")
        return False, []

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")   # H264 silently fails on most servers
    out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    if not out.isOpened():
        logger.error(f"[VIDEO] VideoWriter failed: {output_path}")
        cap.release()
        return False, []

    confirmed: set[str] = set()
    local_buf: dict = defaultdict(int)    # per-video, not shared global
    frame_n = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        try:
            _, annotated, ocr_text, _ = process_license_plate(frame)
            if annotated is None:
                annotated = frame
        except Exception as exc:
            logger.error(f"[VIDEO] Frame {frame_n} error: {exc}")
            annotated = frame
            ocr_text = None

        if annotated.shape[1] != w or annotated.shape[0] != h:
            annotated = cv2.resize(annotated, (w, h))

        out.write(annotated)

        if ocr_text:
            local_buf[ocr_text] += 1
            if local_buf[ocr_text] >= 3:
                confirmed.add(ocr_text)

        if frame_n % 30 == 0:
            logger.info(f"[VIDEO] Frame {frame_n} — OCR: {ocr_text}")

        frame_n += 1

    cap.release()
    out.release()

    logger.info(f"[VIDEO] Done. {frame_n} frames. Plates: {confirmed}")
    return True, list(confirmed)