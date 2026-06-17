from fastapi import APIRouter
from app.database import SessionLocal
from app.models import Detection
import os

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@router.get("/")
def get_history():
    db = SessionLocal()
    try:
        records = db.query(Detection).order_by(Detection.timestamp.desc()).all()
        return [
            {
                "id": r.id,
                "plate_number": r.plate_number,
                "confidence": r.confidence,
                "timestamp": r.timestamp.isoformat(),
                "source": r.source,
                "image_path": r.image_path
            }
            for r in records
        ]
    finally:
        db.close()


@router.delete("/{record_id}")
def delete_record(record_id: int):
    db = SessionLocal()
    try:
        record = db.query(Detection).filter(Detection.id == record_id).first()
        if not record:
            return {"error": "Not found"}

        if record.image_path:
            abs_path = os.path.join(BASE_DIR, record.image_path.lstrip("/"))
            if os.path.exists(abs_path):
                os.remove(abs_path)

        db.delete(record)
        db.commit()
        return {"success": True}
    finally:
        db.close()

@router.delete("/clear")
def clear_history():
    db = SessionLocal()

    try:
        db.query(Detection).delete()
        db.commit()
        print("[HISTORY] Cleared all records")
        return {
            "success": True
        }

    finally:
        db.close()