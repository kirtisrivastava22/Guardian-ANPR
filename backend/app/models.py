from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Detection(Base):
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
    __tablename__ = "watchlist_vehicles"

    id          = Column(Integer, primary_key=True, index=True)
    plate       = Column(String, unique=True, index=True, nullable=False)
    owner_name  = Column(String, nullable=True)
    reason      = Column(String, nullable=False)   
    description = Column(Text,   nullable=True)    
    reported_by = Column(String, nullable=True) 
    active      = Column(Boolean, default=True)
    added_at    = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Watchlist plate={self.plate} reason={self.reason}>"


class Alert(Base):
    __tablename__ = "alerts"

    id               = Column(Integer, primary_key=True, index=True)
    watchlist_id     = Column(Integer, nullable=False)  
    detected_plate   = Column(String,  nullable=False)   
    watchlist_plate  = Column(String,  nullable=False)   
    match_score      = Column(Float,   nullable=False)   
    det_confidence   = Column(Float,   nullable=False)   
    source           = Column(String,  nullable=False)   
    timestamp        = Column(DateTime, default=datetime.utcnow)
    frame_path       = Column(String,  nullable=True)    
    acknowledged     = Column(Boolean, default=False)   

    def __repr__(self):
        return (f"<Alert detected={self.detected_plate} "
                f"watchlist={self.watchlist_plate} score={self.match_score:.2f}>")