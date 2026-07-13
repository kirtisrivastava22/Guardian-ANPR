from fastapi import APIRouter, UploadFile, File
import cv2
import numpy as np
import base64
from datetime import datetime
from app.detector.detector import process_license_plate,PlateDetector
from app.database import SessionLocal
from app.models import Detection
import os
import asyncio
from functools import partial

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "images")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MODEL_PATH = os.path.join(
    BASE_DIR,
    "model",
    "best(2).pt"
)

plate_detector = PlateDetector(model_path = MODEL_PATH)

@router.post("/image")
async def detect_image(file: UploadFile = File(...)):
    data = await file.read()
    np_img = np.frombuffer(data, np.uint8)
    image = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    if image is None:
        return {"detections": [], "count": 0}

    loop = asyncio.get_running_loop()
    annotated_image, detections = await loop.run_in_executor(
        None,
        partial(process_license_plate, image, plate_detector)
    )


    results = []
    db = SessionLocal()

    try:
        for det in detections:
            plate_text = det.get("plate")
            confidence = det.get("ocr_conf", 0.0)

            if not plate_text:
                continue

            plate_text_clean = plate_text.strip()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_filename = f"{timestamp}_{plate_text_clean}.jpg"
            abs_image_path = os.path.join(UPLOAD_DIR, image_filename)

            if annotated_image is not None:
                cv2.imwrite(abs_image_path, annotated_image)

            record = Detection(
                plate_number=plate_text_clean,
                confidence=float(confidence),
                source="image",
                image_path=f"/uploads/images/{image_filename}"
            )

            db.add(record)
            db.flush()  # faster than commit per row

            results.append({
                "id": record.id,
                "plate_number": record.plate_number,
                "confidence": float(record.confidence),
            })

        db.commit()

        annotated_b64 = None
        if annotated_image is not None:
            _, buffer = cv2.imencode(".jpg", annotated_image)
            annotated_b64 = base64.b64encode(buffer).decode("utf-8")

        return {
            "detections": results,
            "count": len(results),
            "annotated_image": annotated_b64,
        }

    except Exception as e:
        db.rollback()
        print("IMAGE DETECTION ERROR:", e)
        return {"detections": [], "count": 0}

    finally:
        db.close()
