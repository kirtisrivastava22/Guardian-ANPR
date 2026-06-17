from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.detector.video_pipeline import process_license_plate
from app.database import SessionLocal
from app.models import Detection, WatchlistVehicle
from app.alert_engine import (
    process_alert,
    register_ws_client,
    unregister_ws_client,
)

from datetime import datetime
import cv2
import numpy as np
import base64
import json
import struct
import time

from asyncio import get_running_loop
from functools import partial
from collections import deque

router = APIRouter()

CONF_THRESHOLD = 0.0
DEDUP_WINDOW_SEC = 5
MAX_IN_MEMORY = 500

history_buffer = deque(maxlen=MAX_IN_MEMORY)
recent_plates = {}

# ── Helpers ───────────────────────────────────────────────────────────────────
def encode_frame(frame: np.ndarray) -> str:
    _, buf = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, 70]
    )
    return base64.b64encode(buf).decode("utf-8")


def should_save_plate(plate: str) -> bool:
    now = time.time()
    last = recent_plates.get(plate)

    if last and now - last < DEDUP_WINDOW_SEC:
        return False

    recent_plates[plate] = now
    return True


def _save_detection(
    plate: str,
    confidence: float,
    source: str,
    video_ts=None,
):
    db = SessionLocal()

    try:
        db.add(
            Detection(
                plate_number=plate,
                confidence=confidence,
                source=source,
                timestamp=datetime.utcnow(),
                video_timestamp=video_ts,
                image_path=None,
            )
        )

        db.commit()

    except Exception as exc:
        print("[DB ERROR]", exc)
        db.rollback()

    finally:
        db.close()


def _get_active_watchlist():
    db = SessionLocal()

    try:
        rows = (
            db.query(WatchlistVehicle)
            .filter_by(active=True)
            .all()
        )

        return [
            {
                "id": r.id,
                "plate": r.plate,
                "reason": r.reason,
                "owner_name": r.owner_name or "",
                "description": r.description or "",
            }
            for r in rows
        ]

    finally:
        db.close()

def parse_incoming_frame(data: bytes):
    if not data:
        raise ValueError("Empty message")

    # Raw JPEG
    if data[:2] == b"\xff\xd8":
        return 0.0, data

    # JSON prefix + JPEG
    jpeg_start = data.find(b"\xff\xd8")

    if jpeg_start > 0:
        prefix = data[:jpeg_start]

        timestamp = 0.0

        try:
            payload = json.loads(
                prefix.decode(
                    "utf-8",
                    errors="replace"
                ).strip()
            )

            timestamp = float(
                payload.get("timestamp", 0.0)
            )

        except Exception:
            pass

        return timestamp, data[jpeg_start:]

    # Float64 timestamp + JPEG

    if len(data) >= 9:
        try:
            ts = struct.unpack_from("<d", data, 0)[0]

            if 0 <= ts <= 86400:
                return ts, data[8:]

        except Exception:
            pass

    raise ValueError("Unknown frame format")
async def _process_and_reply(
    ws, loop, jpeg_data: bytes, timestamp: float, source: str, frame_raw: np.ndarray = None
):
    """Decode JPEG → detect+OCR → alert check → reply."""

    # Decode frame
    if frame_raw is None:
        nparr     = np.frombuffer(jpeg_data, np.uint8)
        frame_raw = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame_raw is None:
        print(f"[WS] imdecode failed: {jpeg_data[:8].hex()}")
        return

    # Detection pipeline
    _, annotated, plate_text, confidence = await loop.run_in_executor(
        None, partial(process_license_plate, frame_raw)
    )

    if confidence < CONF_THRESHOLD:
        plate_text = None

    # ── Save detection to DB ──────────────────────────────────────────────
    if plate_text and should_save_plate(plate_text):
        _save_detection(plate_text.strip(), confidence, source,
                        video_ts=timestamp)

    history_buffer.append({
        "plate": plate_text, "timestamp": timestamp,
        "confidence": confidence, "source": source,
    })

    # ── Stolen vehicle alert check ────────────────────────────────────────
    alert_fired = None
    if plate_text and confidence >= 0.75:
        watchlist = _get_active_watchlist()
        if watchlist:
            db = SessionLocal()
            try:
                alert_fired = await process_alert(
                    ocr_plate  = plate_text,
                    confidence = confidence,
                    source     = source,
                    frame      = frame_raw.copy(),
                    timestamp  = timestamp,
                    watchlist  = watchlist,
                    db_session = db,
                )
            finally:
                db.close()
    print(
        f"[DETECTION] plate={plate_text} "
        f"conf={confidence:.2f} "
        f"time={timestamp}"
    )
    # ── Send normal frame response ────────────────────────────────────────
    response = {
        "frame":      encode_frame(annotated),
        "plate":      plate_text,
        "confidence": confidence,
        "timestamp":  timestamp,
        "alert":      alert_fired,   # None normally; dict when stolen vehicle found
    }

    try:
        await ws.send_json(response)
    except Exception as exc:
        print(f"[WS SEND ERROR] {exc}")
        raise


# ── /video ────────────────────────────────────────────────────────────────────

@router.websocket("/video")
async def video_stream_ws(ws: WebSocket):
    await ws.accept()
    register_ws_client(ws)          # register for alert broadcasts
    loop = get_running_loop()
    print("[WS /video] client connected")

    try:
        while True:
            msg = await ws.receive()

            if msg.get("text") is not None:
                try:
                    payload = json.loads(msg["text"])
                    if payload.get("type") == "ping":
                        await ws.send_json({"type": "pong"})
                except Exception:
                    pass
                continue

            raw = msg.get("bytes")
            if raw is None:
                continue

            try:
                timestamp, jpeg_data = parse_incoming_frame(raw)
            except ValueError as exc:
                print(f"[WS /video] parse error: {exc}")
                continue

            try:
                await _process_and_reply(ws, loop, jpeg_data, timestamp, "video")
            except Exception as exc:
                print(f"[WS /video] error: {exc}")
                import traceback; traceback.print_exc()
                break

    except WebSocketDisconnect:
        print("[WS /video] disconnected")
    except Exception as exc:
        print(f"[WS /video] fatal: {exc}")
    finally:
        unregister_ws_client(ws)    # clean up on disconnect


# ── /webcam ───────────────────────────────────────────────────────────────────

@router.websocket("/webcam")
async def webcam_ws(ws: WebSocket):
    await ws.accept()
    register_ws_client(ws)
    loop = get_running_loop()
    print("[WS /webcam] client connected")

    try:
        while True:
            msg = await ws.receive()

            if msg.get("text") is not None:
                try:
                    payload = json.loads(msg["text"])
                    if payload.get("type") == "ping":
                        await ws.send_json({"type": "pong"})
                except Exception:
                    pass
                continue

            raw = msg.get("bytes")
            if raw is None:
                continue

            try:
                timestamp, jpeg_data = parse_incoming_frame(raw)
                await _process_and_reply(ws, loop, jpeg_data, timestamp, "live")
            except Exception as exc:
                print(f"[WS /webcam] error: {exc}")

    except WebSocketDisconnect:
        print("[WS /webcam] disconnected")
    except Exception as exc:
        print(f"[WS /webcam] fatal: {exc}")
    finally:
        unregister_ws_client(ws)