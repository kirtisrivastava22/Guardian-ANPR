from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.alert_engine import register_ws_client, unregister_ws_client
import json

router = APIRouter()


@router.websocket("/alerts")
async def alerts_ws(ws: WebSocket):
    await ws.accept()
    register_ws_client(ws)

    try:
        while True:
            
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