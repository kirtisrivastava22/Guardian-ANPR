"""
alert_engine.py
───────────────
Core alert logic:
  1. Fuzzy plate matching  — handles 1-2 character OCR errors
     Uses Levenshtein distance (edit distance) so "MH12AB1234"
     still matches "MH12AB1Z34" (Z vs 2 confusion).

  2. Confidence gate       — only fires when YOLO+OCR conf ≥ MIN_CONF

  3. Deduplication         — same plate can't trigger again within
     COOLDOWN_SEC seconds (prevents alert spam on consecutive frames)

  4. Actions on match:
       a. Save Alert row to DB with frame snapshot
       b. Push real-time JSON event to all connected WebSocket clients
       c. Send SMS via Fast2SMS (free tier, India) or Twilio

  5. WebSocket broadcast   — any connected frontend receives the alert
     instantly without polling; the video.py router registers itself here.
"""

import os
import time
import base64
import asyncio
import logging
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("alert")
logger.setLevel(logging.DEBUG)

# ── Config (override via environment variables) ───────────────────────────────

MIN_CONFIDENCE   = float(os.getenv("ALERT_MIN_CONF",    "0.75"))  # 75 %
MIN_MATCH_SCORE  = float(os.getenv("ALERT_MIN_MATCH",   "0.80"))  # fuzzy threshold
COOLDOWN_SEC     = int(os.getenv("ALERT_COOLDOWN_SEC",  "30"))    # seconds between same-plate alerts
FRAME_SAVE_DIR   = os.getenv("ALERT_FRAME_DIR", "alert_frames")
os.makedirs(FRAME_SAVE_DIR, exist_ok=True)

# ── In-memory dedup cache  {plate: last_alert_timestamp} ─────────────────────
_alert_cooldown: dict[str, float] = {}

# ── Connected WebSocket clients (registered by video.py router) ───────────────
_ws_clients: set = set()


def register_ws_client(ws):
    _ws_clients.add(ws)
    logger.debug(f"[ALERT WS] Client registered. Total: {len(_ws_clients)}")


def unregister_ws_client(ws):
    _ws_clients.discard(ws)
    logger.debug(f"[ALERT WS] Client removed. Total: {len(_ws_clients)}")


# ── Fuzzy plate matching ──────────────────────────────────────────────────────

def _levenshtein(a: str, b: str) -> int:
    """Standard edit distance (insertions, deletions, substitutions)."""
    if a == b:
        return 0
    if len(a) == 0:
        return len(b)
    if len(b) == 0:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(
                prev[j + 1] + 1,      # deletion
                curr[j]     + 1,      # insertion
                prev[j] + (ca != cb), # substitution
            ))
        prev = curr
    return prev[-1]


def plate_match_score(ocr_plate: str, watchlist_plate: str) -> float:
    """
    Return similarity score 0.0–1.0.
    1.0 = exact match, 0.0 = completely different.
    Normalised by the length of the longer string.

    Examples:
      "MH12AB1234" vs "MH12AB1234" → 1.00  (exact)
      "MH12AB1Z34" vs "MH12AB1234" → 0.90  (1 char off — Z/2 OCR error)
      "KA01AB1234" vs "MH12AB1234" → 0.60  (too different)
    """
    a = ocr_plate.upper().strip()
    b = watchlist_plate.upper().strip()
    if not a or not b:
        return 0.0
    dist     = _levenshtein(a, b)
    max_len  = max(len(a), len(b))
    return round(1.0 - dist / max_len, 4)


def find_watchlist_match(
    ocr_plate: str,
    watchlist: list[dict],           # [{id, plate, reason, owner_name, description}, ...]
    min_score: float = MIN_MATCH_SCORE,
) -> Optional[dict]:
    """
    Return the best-matching watchlist entry if score ≥ min_score, else None.
    watchlist is passed in (loaded fresh from DB by the caller) so this
    function has no DB dependency and is easy to unit-test.
    """
    best_entry = None
    best_score = 0.0

    for entry in watchlist:
        score = plate_match_score(ocr_plate, entry["plate"])
        if score > best_score:
            best_score  = score
            best_entry  = entry

    if best_score >= min_score:
        return {**best_entry, "match_score": best_score}
    return None


# ── Cooldown check ────────────────────────────────────────────────────────────

def _is_on_cooldown(plate: str) -> bool:
    last = _alert_cooldown.get(plate, 0)
    return (time.time() - last) < COOLDOWN_SEC


def _set_cooldown(plate: str):
    _alert_cooldown[plate] = time.time()


# ── Frame saving ──────────────────────────────────────────────────────────────

def save_alert_frame(frame: np.ndarray, plate: str) -> str:
    """
    Draw a RED border + large plate text on the frame and save to disk.
    Returns the saved file path.
    """
    h, w = frame.shape[:2]
    annotated = frame.copy()

    # Red border
    cv2.rectangle(annotated, (0, 0), (w - 1, h - 1), (0, 0, 255), 6)

    # Large "ALERT" banner
    cv2.rectangle(annotated, (0, 0), (w, 60), (0, 0, 200), -1)
    cv2.putText(annotated, f"⚠ STOLEN VEHICLE DETECTED: {plate}",
                (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{FRAME_SAVE_DIR}/alert_{plate}_{ts}.jpg"
    cv2.imwrite(filename, annotated)
    logger.info(f"[ALERT] Frame saved: {filename}")
    return filename


# ── WebSocket broadcast ───────────────────────────────────────────────────────

async def broadcast_alert(alert_payload: dict):
    """
    Push alert JSON to all connected WebSocket clients simultaneously.
    Dead clients are removed from the set.
    """
    if not _ws_clients:
        return

    dead = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_json(alert_payload)
        except Exception:
            dead.add(ws)

    for ws in dead:
        _ws_clients.discard(ws)

    logger.info(f"[ALERT WS] Broadcast to {len(_ws_clients)} clients")


# ── Main entry point called from video.py ─────────────────────────────────────

async def process_alert(
    ocr_plate:   str,
    confidence:  float,
    source:      str,           # "video" | "live"
    frame:       np.ndarray,
    timestamp:   float,
    watchlist:   list[dict],    # fresh from DB
    db_session,                 # SQLAlchemy session
) -> Optional[dict]:
    """
    Called after every successful plate read.
    Returns the alert dict if an alert was fired, else None.

    Steps:
      1. Confidence gate
      2. Fuzzy match against watchlist
      3. Cooldown check
      4. Save frame, write DB, broadcast WS, send SMS
    """
    from app.models import Alert   # local import avoids circular deps

    # ── 1. Confidence gate ────────────────────────────────────────────────
    if confidence < MIN_CONFIDENCE:
        logger.debug(f"[ALERT] '{ocr_plate}' conf={confidence:.2f} below threshold {MIN_CONFIDENCE}")
        return None

    # ── 2. Fuzzy watchlist match ──────────────────────────────────────────
    match = find_watchlist_match(ocr_plate, watchlist)
    if not match:
        return None

    # ── 3. Cooldown ───────────────────────────────────────────────────────
    if _is_on_cooldown(ocr_plate):
        logger.debug(f"[ALERT] '{ocr_plate}' on cooldown — skipping")
        return None
    _set_cooldown(ocr_plate)

    logger.warning(
        f"[ALERT] 🚨 MATCH: ocr='{ocr_plate}' "
        f"watchlist='{match['plate']}' "
        f"score={match['match_score']:.2f} "
        f"conf={confidence:.2f}"
    )

    # ── 4a. Save annotated frame ──────────────────────────────────────────
    frame_path = save_alert_frame(frame, ocr_plate) if frame is not None else None

    # ── 4b. Write Alert to DB ─────────────────────────────────────────────
    alert_row = Alert(
        watchlist_id    = match["id"],
        detected_plate  = ocr_plate,
        watchlist_plate = match["plate"],
        match_score     = match["match_score"],
        det_confidence  = confidence,
        source          = source,
        timestamp       = datetime.utcnow(),
        frame_path      = frame_path,
        acknowledged    = False,
    )
    try:
        db_session.add(alert_row)
        db_session.commit()
        db_session.refresh(alert_row)
    except Exception as exc:
        logger.error(f"[ALERT DB] {exc}")
        db_session.rollback()

    # ── 4c. Build alert payload ───────────────────────────────────────────
    # Encode frame as base64 for WebSocket delivery
    frame_b64 = None
    if frame is not None:
        _, buf   = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_b64 = base64.b64encode(buf).decode("utf-8")

    alert_payload = {
        "type":             "STOLEN_VEHICLE_ALERT",
        "detection_time_utc":
    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "detected_plate":   ocr_plate,
        "watchlist_plate":  match["plate"],
        "match_score":      match["match_score"],
        "confidence":       round(confidence, 3),
        "reason":           match.get("reason", "unknown"),
        "owner":            match.get("owner_name", ""),
        "description":      match.get("description", ""),
        "source":           source,
        "timestamp":        timestamp,
        "alert_id":         alert_row.id if hasattr(alert_row, 'id') else None,
        "frame":            frame_b64,    # annotated frame with red border
    }
    
    # ── 4d. Broadcast to all connected WebSocket clients ──────────────────
    await broadcast_alert(alert_payload)
    return alert_payload