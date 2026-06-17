"""
video_pipeline.py
─────────────────
Dual-model pipeline:
  Model A — YOLOv8s pretrained on COCO  → detects vehicles (car, bus, truck,
             motorcycle, bicycle) using the standard yolov8s.pt weights.
             No training needed; COCO already covers all vehicle classes.

  Model B — Your fine-tuned best.pt     → detects license plates only.

Per-frame flow:
  1. Run vehicle model on full frame   → draw YELLOW boxes + class label
  2. Run plate model on full frame     → for each detected plate region:
       a. Enhanced crop preprocessing
       b. EasyOCR
       c. Garbage filter (plate_postprocess)
       d. If valid text → draw CYAN box + plate text above vehicle box
  3. Return annotated frame

Colors:
  Vehicle box  → YELLOW  (0, 220, 255) in BGR
  Plate box    → CYAN    (255, 220, 0) in BGR
  Plate text   → GREEN   (0, 255, 80)  in BGR
"""

import cv2
import numpy as np
import os
import logging
from collections import defaultdict
from ultralytics import YOLO
from app.detector.ocr import PlateOCR
import torch

torch.set_grad_enabled(False)

logger = logging.getLogger("lpr")
logger.setLevel(logging.DEBUG)

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# ── Model paths ───────────────────────────────────────────────────────────────

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLATE_MODEL_PATH   = os.path.join(BASE_DIR, "model", "best.pt")
VEHICLE_MODEL_PATH = os.path.join(BASE_DIR, "model", "yolov8s.pt")
# yolov8s.pt will be auto-downloaded by ultralytics on first run if not present

# ── COCO class IDs that are vehicles ─────────────────────────────────────────
# Full COCO list: https://docs.ultralytics.com/datasets/detect/coco/
VEHICLE_CLASS_IDS = {
    2:  "Car",
    3:  "Motorcycle",
    5:  "Bus",
    7:  "Truck",
    1:  "Bicycle",
}

# ── Annotation colours (BGR) ──────────────────────────────────────────────────
COLOR_VEHICLE = (0,   210, 255)   # yellow-orange
COLOR_PLATE   = (255, 200,   0)   # cyan-blue
COLOR_TEXT    = (0,   255,  80)   # bright green

FONT       = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.55
THICKNESS  = 2

# ── Singletons ────────────────────────────────────────────────────────────────

_plate_model:   YOLO | None = None
_vehicle_model: YOLO | None = None
_ocr_engine:    PlateOCR | None = None

plate_buffer: dict = defaultdict(int)


def get_plate_model() -> YOLO:
    global _plate_model
    if _plate_model is None:
        if not os.path.exists(PLATE_MODEL_PATH):
            raise FileNotFoundError(
                f"Plate model not found: {PLATE_MODEL_PATH}\n"
                "Place your trained best.pt in app/model/"
            )
        logger.info(f"[INIT] Loading plate model: {PLATE_MODEL_PATH}")
        _plate_model = YOLO(PLATE_MODEL_PATH)
    return _plate_model


def get_vehicle_model() -> YOLO:
    global _vehicle_model
    if _vehicle_model is None:
        logger.info(f"[INIT] Loading vehicle model: {VEHICLE_MODEL_PATH}")
        # Ultralytics auto-downloads yolov8s.pt if path not found
        _vehicle_model = YOLO(VEHICLE_MODEL_PATH)
    return _vehicle_model


def get_ocr_engine() -> PlateOCR:
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = PlateOCR()
    return _ocr_engine


# ── Plate crop preprocessing ──────────────────────────────────────────────────

def _enhance_plate_crop(crop: np.ndarray) -> np.ndarray:
    """
    Aggressive enhancement for video-frame plate crops:
    upscale → sharpen → CLAHE → optional threshold
    """
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

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
            cv2.THRESH_BINARY, 15, 4
        )

    gray = cv2.bilateralFilter(gray, 5, 50, 50)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


# ── Label drawing helpers ─────────────────────────────────────────────────────

def _draw_label(image: np.ndarray, text: str, x: int, y: int,
                color_box, color_text=(255, 255, 255), scale=0.52):
    """Draw a filled-background label at (x, y)."""
    (tw, th), baseline = cv2.getTextSize(text, FONT, scale, THICKNESS)
    pad = 3
    # Background rectangle
    cv2.rectangle(image,
                  (x - pad, y - th - pad - baseline),
                  (x + tw + pad, y + pad),
                  color_box, -1)
    cv2.putText(image, text, (x, y - baseline),
                FONT, scale, color_text, 1, cv2.LINE_AA)


# ── Vehicle detection ─────────────────────────────────────────────────────────

def detect_vehicles(image: np.ndarray) -> list[dict]:
    """
    Run YOLOv8s on the frame and return all vehicle detections.
    Each item: {bbox, conf, label}
    """
    model   = get_vehicle_model()
    results = model.predict(
        source  = image,
        imgsz   = 640,
        conf    = 0.35,
        iou     = 0.45,
        classes = list(VEHICLE_CLASS_IDS.keys()),
        device  = "cpu",
        verbose = False,
    )

    vehicles = []
    if not results:
        return vehicles

    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls[0])
            if cls_id not in VEHICLE_CLASS_IDS:
                continue
            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            if x2 <= x1 or y2 <= y1:
                continue
            vehicles.append({
                "bbox":  (x1, y1, x2, y2),
                "conf":  conf,
                "label": VEHICLE_CLASS_IDS[cls_id],
            })
    print(f"[VEHICLES FOUND] {len(vehicles)}")
    logger.debug(f"[VEHICLE] {len(vehicles)} vehicles found")
    return vehicles


# ── Plate detection + OCR ─────────────────────────────────────────────────────

def detect_plates(image: np.ndarray) -> list[dict]:
    """
    Run plate model on the full frame.
    Returns items: {bbox, det_conf, crop}
    """
    model   = get_plate_model()
    results = model.predict(
        source  = image,
        imgsz   = 640,
        conf    = 0.25,
        iou     = 0.35,
        device  = "cpu",
        verbose = False,
    )

    plates = []
    if not results:
        return plates

    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            if x2 <= x1 or y2 <= y1:
                continue
            if (x2 - x1) < 20 or (y2 - y1) < 8:
                continue
            crop = image[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            plates.append({
                "bbox":     (x1, y1, x2, y2),
                "det_conf": conf,
                "crop":     crop,
            })
    print(f"[PLATES FOUND] {len(plates)}")
    return plates


def read_plate_text(crop: np.ndarray) -> tuple[str, float]:
    """
    Enhance crop → OCR → garbage filter.
    Returns ("", 0.0) if text is garbage or unreadable.
    """
    enhanced        = _enhance_plate_crop(crop)
    ocr             = get_ocr_engine()
    text, ocr_conf  = ocr.read_plate(enhanced)
    # ocr.read_plate already calls apply_plate_syntax which runs is_garbage
    # so empty string means garbage was caught there
    return text, ocr_conf


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process_license_plate(image: np.ndarray):
    """
    Full dual-model pipeline.

    Returns:
        plate_crop      : np.ndarray | None  — best plate image crop
        annotated       : np.ndarray         — frame with all annotations
        best_plate_text : str | None         — best plate text this frame
        best_confidence : float              — combined confidence
    """
    if image is None or image.size == 0:
        return None, image, None, 0.0

    annotated = image.copy()

    # ── Step 1: Detect and annotate vehicles ─────────────────────────────
    vehicles = detect_vehicles(image)

    for v in vehicles:
        x1, y1, x2, y2 = v["bbox"]
        label           = v["label"]
        conf            = v["conf"]

        # Yellow bounding box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), COLOR_VEHICLE, THICKNESS)

        # Label above box: "Car 91%"
        _draw_label(
            annotated,
            f"{label} {conf*100:.0f}%",
            x1, y1 - 2,
            color_box  = COLOR_VEHICLE,
            color_text = (0, 0, 0),
            scale      = 0.52,
        )

    # ── Step 2: Detect plates on full frame ──────────────────────────────
    plate_detections = detect_plates(image)

    best_plate_text  = None
    best_confidence  = 0.0
    best_crop        = None

    for pd in plate_detections:
        x1, y1, x2, y2 = pd["bbox"]
        det_conf        = pd["det_conf"]

        text, ocr_conf = read_plate_text(pd["crop"])

        # Cyan plate bounding box always drawn (even if OCR failed)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), COLOR_PLATE, THICKNESS)

        if text:
            final_conf = 0.65 * det_conf + 0.35 * ocr_conf

            # Plate text label on the plate box
            _draw_label(
                annotated,
                f"{text}  {final_conf*100:.0f}%",
                x1, y1 - 2,
                color_box  = COLOR_PLATE,
                color_text = (0, 0, 0),
                scale      = 0.58,
            )

            # Also print large plate text at the top-left HUD
            cv2.putText(
                annotated,
                text,
                (10, 36),
                FONT, 1.1, COLOR_TEXT, 2, cv2.LINE_AA,
            )

            if final_conf > best_confidence:
                best_confidence = final_conf
                best_plate_text = text
                best_crop       = pd["crop"]

            logger.info(f"[OCR] '{text}'  det={det_conf:.2f}  ocr={ocr_conf:.2f}  final={final_conf:.2f}")
        else:
            logger.debug(f"[OCR] No valid text at box {pd['bbox']}")

    logger.debug(f"[FRAME] {len(vehicles)} vehicles  {len(plate_detections)} plates  best='{best_plate_text}'")
    return best_crop, annotated, best_plate_text, best_confidence


# ── Batch video file processing ───────────────────────────────────────────────

def process_video(input_path: str, output_path: str):
    cap         = cv2.VideoCapture(input_path)
    output_path = output_path.rsplit(".", 1)[0] + ".mp4"

    if not cap.isOpened():
        logger.error(f"[VIDEO] Cannot open: {input_path}")
        return False, []

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out    = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    if not out.isOpened():
        logger.error(f"[VIDEO] VideoWriter failed: {output_path}")
        cap.release()
        return False, []

    confirmed:  set[str] = set()
    local_buf:  dict     = defaultdict(int)
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
            ocr_text  = None

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