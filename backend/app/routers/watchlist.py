from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import SessionLocal
from app.models import WatchlistVehicle, Alert
from app.alert_engine import plate_match_score, find_watchlist_match

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic schemas

class VehicleIn(BaseModel):
    plate:       str
    owner_name:  Optional[str] = None
    reason:      str = "stolen"      
    description: Optional[str] = None
    reported_by: Optional[str] = None


class VehicleOut(BaseModel):
    id:          int
    plate:       str
    owner_name:  Optional[str]
    reason:      str
    description: Optional[str]
    reported_by: Optional[str]
    active:      bool
    added_at:    datetime

    class Config:
        from_attributes = True


class AlertOut(BaseModel):
    id:              int
    detected_plate:  str
    watchlist_plate: str
    match_score:     float
    det_confidence:  float
    source:          str
    timestamp:       datetime
    acknowledged:    bool
    frame_path:      Optional[str]

    class Config:
        from_attributes = True


def _get_watchlist_dicts(db: Session) -> list[dict]:
    rows = db.query(WatchlistVehicle).filter_by(active=True).all()
    return [
        {
            "id":          r.id,
            "plate":       r.plate,
            "reason":      r.reason,
            "owner_name":  r.owner_name or "",
            "description": r.description or "",
        }
        for r in rows
    ]


@router.post("/", response_model=VehicleOut)
def add_vehicle(payload: VehicleIn, db: Session = Depends(get_db)):
    
    plate = payload.plate.upper().strip()

    existing = db.query(WatchlistVehicle).filter_by(plate=plate).first()
    if existing:
        if not existing.active:
            existing.active = True
            db.commit()
            db.refresh(existing)
            return existing
        raise HTTPException(status_code=409, detail=f"Plate {plate} already on watchlist")

    vehicle = WatchlistVehicle(
        plate       = plate,
        owner_name  = payload.owner_name,
        reason      = payload.reason,
        description = payload.description,
        reported_by = payload.reported_by,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.get("/", response_model=list[VehicleOut])
def list_vehicles(active_only: bool = True, db: Session = Depends(get_db)):
    """List watchlist vehicles."""
    q = db.query(WatchlistVehicle)
    if active_only:
        q = q.filter_by(active=True)
    return q.order_by(WatchlistVehicle.added_at.desc()).all()


@router.delete("/{vehicle_id}")
def remove_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    """Soft-delete (deactivate) a watchlist entry."""
    v = db.query(WatchlistVehicle).filter_by(id=vehicle_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    v.active = False
    db.commit()
    return {"status": "deactivated", "plate": v.plate}

@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()

    if not alert:
        raise HTTPException(
            status_code=404,
            detail="Alert not found"
        )

    db.delete(alert)
    db.commit()

    return {
        "success": True
    }
    
@router.post("/seed")
def seed_watchlist(vehicles: list[VehicleIn], db: Session = Depends(get_db)):
    added = 0
    skipped = 0
    for v in vehicles:
        plate = v.plate.upper().strip()
        if db.query(WatchlistVehicle).filter_by(plate=plate, active=True).first():
            skipped += 1
            continue
        db.add(WatchlistVehicle(
            plate       = plate,
            owner_name  = v.owner_name,
            reason      = v.reason,
            description = v.description,
            reported_by = v.reported_by,
        ))
        added += 1
    db.commit()
    return {"added": added, "skipped": skipped}


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    unacknowledged_only: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(Alert)
    if unacknowledged_only:
        q = q.filter_by(acknowledged=False)
    return q.order_by(Alert.timestamp.desc()).limit(limit).all()


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter_by(id=alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    db.commit()
    return {"status": "acknowledged", "alert_id": alert_id}


@router.get("/test-match")
def test_match(plate: str, db: Session = Depends(get_db)):
    watchlist = _get_watchlist_dicts(db)
    if not watchlist:
        return {"result": "no_watchlist", "message": "Watchlist is empty"}

    scored = sorted(
        [{"plate": w["plate"], "score": plate_match_score(plate.upper(), w["plate"]),
          "reason": w["reason"]} for w in watchlist],
        key=lambda x: x["score"], reverse=True
    )[:3]

    best = scored[0] if scored else None
    return {
        "query":       plate.upper(),
        "top_matches": scored,
        "would_alert": best and best["score"] >= 0.80,
    }
    
@router.get("/alerts/unread-count")
def unread_alert_count(db: Session = Depends(get_db)):
    count = (
        db.query(Alert)
        .filter(Alert.acknowledged == False)
        .count()
    )

    return {
        "count": count
    }