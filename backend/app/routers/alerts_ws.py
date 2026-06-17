"""
routers/alerts_ws.py
────────────────────
Dedicated WebSocket endpoint for the frontend AlertContext.
Clients that connect here receive every broadcast from
alert_engine.broadcast_alert() — even when they're not on the
video page.

Mount in main.py:
    from app.routers import alerts_ws
    app.include_router(alerts_ws.router, prefix="/ws", tags=["WebSocket"])
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.alert_engine import register_ws_client, unregister_ws_client
import json

router = APIRouter()


@router.websocket("/alerts")
async def alerts_ws(ws: WebSocket):
    """
    Pure push endpoint — server only sends, client only pings.
    Receives STOLEN_VEHICLE_ALERT JSON broadcasts from alert_engine.
    """
    await ws.accept()
    register_ws_client(ws)

    try:
        while True:
            # Block waiting for a ping (keepalive); ignore everything else.
            msg = await ws.receive()

            if msg.get("text"):
                try:
                    payload = json.loads(msg["text"])
                    if payload.get("type") == "ping":
                        await ws.send_json({"type": "pong"})
                except Exception:
                    pass

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[WS /alerts] error: {exc}")
    finally:
        unregister_ws_client(ws)