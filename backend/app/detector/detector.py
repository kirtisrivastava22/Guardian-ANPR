import cv2
from ultralytics import YOLO
from collections import defaultdict
from app.detector.ocr import PlateOCR

_ocr_engine = None

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = PlateOCR()
    return _ocr_engine

plate_buffer = defaultdict(int)


class PlateDetector:
    def __init__(self, model_path: str):
        self.model = YOLO(model_path)

    def detect(self, image, conf_thresh=0.25):
        results = self.model.predict(image, imgsz=640, conf=conf_thresh, verbose=False)
        detections = []

        if not results:
            return detections

        for r in results:
            if r.boxes is None:
                continue

            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])

                if conf < conf_thresh:
                    continue

                if x2 <= x1 or y2 <= y1:
                    continue

                crop = image[y1:y2, x1:x2]
                if crop.size == 0:
                    continue

                detections.append({
                    "bbox": (x1, y1, x2, y2),
                    "det_conf": conf,
                    "crop": crop
                })

        return detections


def process_license_plate(image, detector: PlateDetector):
    detections = detector.detect(image)
    results = []
    ocr_engine = get_ocr_engine()

    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        plate_img = det["crop"]

        text, ocr_conf = ocr_engine.read_plate(plate_img)
        if not text or ocr_conf < 0.1:
            continue

        final_conf = 0.6 * det["det_conf"] + 0.4 * ocr_conf

        cv2.rectangle(image, (x1,y1),(x2,y2),(0,255,0),2)
        cv2.putText(
            image,
            f"{text} ({final_conf:.2f})",
            (x1, y1-8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0,255,0),
            2
        )

        results.append({
            "plate": text,
            "det_conf": det["det_conf"],
            "ocr_conf": final_conf,
            "bbox": det["bbox"]
        })

    return image, results
