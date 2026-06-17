"""
routers/video.py
────────────────
WebSocket endpoints for video streaming and live webcam.

MESSAGE FORMAT DETECTIVE WORK:
  The browser sends two ws.send() calls back-to-back:
    ws.send(JSON.stringify({type:"frame_meta", timestamp:t}))
    ws.send(arrayBuffer)   ← JPEG bytes

  At the TCP/WebSocket layer these arrive CONCATENATED as one binary
  message. The structure is:
    [JSON string bytes (variable length)] [JPEG bytes starting with ffd8]

  We locate the JPEG start by scanning for the ffd8 SOI marker,
  then parse the prefix as JSON to extract the timestamp.

  This handler also supports the newer single-message framing protocol
  (Float64 LE timestamp header) if you switch the frontend later.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.detector.video_pipeline import process_license_plate
from app.database import SessionLocal
from app.models import Detection
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

CONF_THRESHOLD   = 0.0
DEDUP_WINDOW_SEC = 5
MAX_IN_MEMORY    = 500

history_buffer: deque = deque(maxlen=MAX_IN_MEMORY)
recent_plates:  dict  = {}


def encode_frame(frame: np.ndarray) -> str:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return base64.b64encode(buf).decode("utf-8")


def should_save_plate(plate: str) -> bool:
    now  = time.time()
    last = recent_plates.get(plate)
    if last and now - last < DEDUP_WINDOW_SEC:
        return False
    recent_plates[plate] = now
    return True


def _save(plate: str, confidence: float, source: str, video_ts=None):
    db = SessionLocal()
    try:
        db.add(Detection(
            plate_number    = plate,
            confidence      = confidence,
            source          = source,
            timestamp       = datetime.utcnow(),
            video_timestamp = video_ts,
            image_path      = None,
        ))
        db.commit()
        print(f"[DB] {source}: {plate} ({confidence:.2f})")
    except Exception as exc:
        print(f"[DB ERROR] {exc}")
        db.rollback()
    finally:
        db.close()


def parse_incoming_frame(data: bytes) -> tuple[float, bytes]:
    """
    Parse whatever binary format the frontend sends and return
    (timestamp: float, jpeg_bytes: bytes).

    Handles three cases:

    Case 1 — Concatenated JSON + JPEG (current frontend):
      The browser calls ws.send(jsonString) then ws.send(jpegBuffer).
      These arrive merged: [utf-8 JSON bytes][ffd8... JPEG bytes]
      We scan for the ffd8 SOI marker to split them.

    Case 2 — New framing protocol (Float64 header):
      [8-byte Float64 LE timestamp][JPEG bytes]
      Detectable because first 2 bytes are NOT ffd8 and NOT '{'.

    Case 3 — Raw JPEG only (webcam / no metadata):
      Starts directly with ffd8.
      Timestamp defaults to 0.0.
    """
    if not data:
        raise ValueError("Empty message")

    # ── Case 3: raw JPEG, no metadata ────────────────────────────────────
    if data[:2] == b'\xff\xd8':
        return 0.0, data

    # ── Case 1: JSON prefix + JPEG (what the current frontend sends) ─────
    # Find the JPEG SOI marker ffd8
    jpeg_start = data.find(b'\xff\xd8')
    if jpeg_start > 0:
        prefix = data[:jpeg_start]
        jpeg   = data[jpeg_start:]
        timestamp = 0.0
        try:
            payload   = json.loads(prefix.decode("utf-8", errors="replace").strip())
            timestamp = float(payload.get("timestamp", 0.0))
        except Exception:
            pass  # can't parse prefix JSON, use 0.0
        return timestamp, jpeg

    # ── Case 2: Float64 header framing ───────────────────────────────────
    if len(data) >= 9:
        try:
            ts = struct.unpack_from("<d", data, 0)[0]
            # sanity-check: a valid video timestamp is 0–86400 seconds
            if 0.0 <= ts <= 86400.0:
                return ts, data[8:]
        except struct.error:
            pass

    raise ValueError(f"Unrecognised frame format, first bytes: {data[:16].hex()}")


async def _process_and_reply(ws, loop, jpeg_data: bytes, timestamp: float, source: str):
    nparr = np.frombuffer(jpeg_data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        print(f"[WS] imdecode failed. JPEG header: {jpeg_data[:8].hex()}")
        return

    print(f"[WS] frame {frame.shape}  ts={timestamp:.3f}s  source={source}")

    _, annotated, plate_text, confidence = await loop.run_in_executor(
        None, partial(process_license_plate, frame)
    )

    if confidence < CONF_THRESHOLD:
        plate_text = None

    if plate_text and should_save_plate(plate_text):
        _save(plate_text.strip(), confidence, source,
              video_ts=timestamp if source == "video" else None)

    history_buffer.append({
        "plate": plate_text, "timestamp": timestamp,
        "confidence": confidence, "source": source,
    })

    await ws.send_json({
        "frame":      encode_frame(annotated),
        "plate":      plate_text,
        "confidence": confidence,
        "timestamp":  timestamp,
    })


# ── /video ───────────────────────────────────────────────────────────────────

@router.websocket("/video")
async def video_stream_ws(ws: WebSocket):
    await ws.accept()
    loop = get_running_loop()
    print("[WS /video] client connected")

    try:
        while True:
            msg = await ws.receive()

            # Text-only control messages (ping, standalone frame_meta)
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

            print(f"[WS /video] {len(jpeg_data)} JPEG bytes  ts={timestamp:.3f}s")

            try:
                await _process_and_reply(ws, loop, jpeg_data, timestamp, "video")
            except Exception as exc:
                print(f"[WS /video] processing error: {exc}")
                import traceback; traceback.print_exc()

    except WebSocketDisconnect:
        print("[WS /video] disconnected")
    except Exception as exc:
        print(f"[WS /video] fatal: {exc}")
        import traceback; traceback.print_exc()


# ── /webcam ──────────────────────────────────────────────────────────────────

@router.websocket("/webcam")
async def webcam_ws(ws: WebSocket):
    await ws.accept()
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
        import traceback; traceback.print_exc()