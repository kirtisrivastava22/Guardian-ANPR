# app/models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Detection(Base):
    """Every plate read — image, video, or live."""
    __tablename__ = "detections"

    id              = Column(Integer, primary_key=True, index=True)
    plate_number    = Column(String, index=True)
    confidence      = Column(Float)
    source          = Column(String)          # "image" | "video" | "live"
    timestamp       = Column(DateTime, default=datetime.utcnow)
    image_path      = Column(String, nullable=True)
    video_timestamp = Column(Float,  nullable=True)

    def __repr__(self):
        return f"<Detection plate={self.plate_number} conf={self.confidence:.2f}>"


class WatchlistVehicle(Base):
    """
    Stolen / wanted / suspicious vehicle registry.
    Populated manually via POST /watchlist or seeded from a CSV.
    """
    __tablename__ = "watchlist_vehicles"

    id          = Column(Integer, primary_key=True, index=True)
    plate       = Column(String, unique=True, index=True, nullable=False)
    owner_name  = Column(String, nullable=True)
    reason      = Column(String, nullable=False)   # "stolen" | "wanted" | "suspect"
    description = Column(Text,   nullable=True)    # vehicle make/model/colour
    reported_by = Column(String, nullable=True)    # police station / user
    active      = Column(Boolean, default=True)
    added_at    = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Watchlist plate={self.plate} reason={self.reason}>"


class Alert(Base):
    """
    Fired every time a watchlist vehicle is detected with conf ≥ threshold.
    Stores the frame snapshot path so you can review evidence later.
    """
    __tablename__ = "alerts"

    id               = Column(Integer, primary_key=True, index=True)
    watchlist_id     = Column(Integer, nullable=False)   # FK → WatchlistVehicle.id
    detected_plate   = Column(String,  nullable=False)   # what OCR actually read
    watchlist_plate  = Column(String,  nullable=False)   # what was in the watchlist
    match_score      = Column(Float,   nullable=False)   # 0-1 fuzzy similarity
    det_confidence   = Column(Float,   nullable=False)   # YOLO+OCR combined conf
    source           = Column(String,  nullable=False)   # "video" | "live"
    timestamp        = Column(DateTime, default=datetime.utcnow)
    frame_path       = Column(String,  nullable=True)    # saved annotated frame
    acknowledged     = Column(Boolean, default=False)    # operator confirmed/dismissed

    def __repr__(self):
        return (f"<Alert detected={self.detected_plate} "
                f"watchlist={self.watchlist_plate} score={self.match_score:.2f}>")