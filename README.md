# 🛡️ Guardian ANPR (Automatic Number Plate Recognition System)

Guardian ANPR is an **end-to-end Automatic Number Plate Recognition system** built for real-time traffic surveillance and **stolen vehicle detection**. It combines a **custom-trained YOLOv8 plate detector**, **EasyOCR** text extraction, a **FastAPI WebSocket backend**, and a **Next.js frontend** with a live alert system.

---

## ✨ Features

* 🔍 **Dual-model pipeline** — YOLOv8s (COCO) for vehicle detection + fine-tuned YOLOv8 for plate detection
* 🧠 **Custom-trained YOLO model** fine-tuned on Indian, UK, and international plate datasets
* 🔠 **OCR pipeline** with country-specific syntax correction and garbage filtering
* 🚨 **Stolen vehicle alert system** — fuzzy plate matching, real-time toast notification, audio alarm, and frame snapshot
* 📋 **Watchlist management** — add/remove/bulk-import vehicles, soft delete, acknowledge alerts
* 🎥 **Live WebSocket camera stream** at configurable fps
* 🖼️ **Image upload** endpoint for static plate detection
* ⚡ **FastAPI async backend** with thread-pool offloaded inference (non-blocking)
* 💾 **SQLite / PostgreSQL** database for detection history and alert audit trail
* 🚀 **Production-ready structure** with environment-variable configuration

---

## 🗂️ Project Structure

```
Guardian-ANPR/
├── backend/
│   ├── app/
│   │   ├── detector/
│   │   │   ├── detector.py          # PlateDetector — image endpoint only
│   │   │   ├── ocr.py               # EasyOCR wrapper (PlateOCR)
│   │   │   ├── plate_postprocess.py # Syntax correction + garbage filter
│   │   │   ├── utils.py             # Preprocessing helpers
│   │   │   └── video_pipeline.py    # Dual-model pipeline for WS stream
│   │   ├── routers/
│   │   │   ├── image.py             # POST /detect/image
│   │   │   ├── video.py             # WS /ws/video  WS /ws/webcam
│   │   │   ├── alerts_ws.py         # WS /ws/alerts (push-only alert channel)
│   │   │   ├── history.py           # GET/DELETE /history
│   │   │   └── watchlist.py         # Full watchlist + alert CRUD
│   │   ├── alert_engine.py          # Levenshtein matching, cooldown, WS broadcast
│   │   ├── config.py                # COUNTRY_CONFIG context variable
│   │   ├── database.py              # SQLAlchemy engine + session
│   │   ├── models.py                # Detection, WatchlistVehicle, Alert ORM models
│   │   └── main.py                  # FastAPI app entry point
│   ├── model/
│   │   ├── best.pt                  # Fine-tuned plate detector (place here)
│   │   └── yolov8s.pt               # COCO vehicle detector (auto-downloaded)
│   └── requirements.txt
│
├── frontend/                        # Next.js application
│   ├── app/
│   │   ├── live/page.tsx            # Live camera ANPR page
│   │   └── layout.tsx               # Root layout — mounts AlertProvider + AlertToast
│   ├── components/
│   │   └── AlertToast.tsx           # Global stolen-vehicle alert modal
│   └── contexts/
│       └── AlertContext.tsx         # Global alert state + /ws/alerts WebSocket
│
├── alert_frames/                    # Annotated frame snapshots saved on alert
├── uploads/
│   └── images/                      # Annotated images from /detect/image
├── README.md
└── .gitignore
```

---

## 🧠 Model Details

### Plate Detector (`best.pt`)
* Architecture: **YOLOv8s**, fine-tuned in two phases on merged plate datasets
* Task: **Single-class detection** (class 0 = `plate`) — specialised for plate bounding boxes only
* Training datasets: augmented-startups plates dataset + samrat-sahoo license plates dataset + custom auto-annotated hard data
* imgsz: 640 | Optimizer: AdamW | Phase 1: 80 epochs from scratch | Phase 2: 40 epochs fine-tuning with frozen backbone (freeze=10)
* Key augmentations: perspective warp, shear, scale variation, brightness jitter — no fliplr/flipud (plate text is direction-sensitive)

### Vehicle Detector (`yolov8s.pt`)
* Standard YOLOv8s pretrained on **COCO** — no custom training required
* Detects: Car (2), Motorcycle (3), Bus (5), Truck (7), Bicycle (1) via COCO class IDs
* Auto-downloaded by Ultralytics on first run if not present

---

## 🔌 Backend (FastAPI)

### Start the backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///app/detections.db` | Full DB connection URL |
| `ALERT_MIN_CONF` | `0.75` | Minimum confidence to trigger an alert |
| `ALERT_MIN_MATCH` | `0.80` | Minimum fuzzy match score for watchlist hit |
| `ALERT_COOLDOWN_SEC` | `30` | Seconds before same plate can alert again |
| `ALERT_FRAME_DIR` | `alert_frames` | Directory for saved alert frame JPEGs |

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/detect/image` | Detect plates from an uploaded image |
| `WS` | `/ws/webcam` | Live camera stream — send JPEG blobs, receive annotated frame + plate + alert |
| `WS` | `/ws/video` | Video file stream — same protocol as `/ws/webcam` |
| `WS` | `/ws/alerts` | Push-only alert channel — receives `STOLEN_VEHICLE_ALERT` broadcasts |
| `GET` | `/history/` | Detection history, newest first |
| `DELETE` | `/history/{id}` | Delete a detection record + image file |
| `DELETE` | `/history/clear` | Clear all detection history |
| `POST` | `/watchlist/` | Add a vehicle to the watchlist |
| `GET` | `/watchlist/` | List watchlist vehicles (`?active_only=true`) |
| `DELETE` | `/watchlist/{id}` | Soft-delete a watchlist entry |
| `POST` | `/watchlist/seed` | Bulk import vehicles from a JSON array |
| `GET` | `/watchlist/alerts` | List fired alerts (`?unacknowledged_only`, `?limit`) |
| `POST` | `/watchlist/alerts/{id}/acknowledge` | Mark an alert as reviewed |
| `DELETE` | `/watchlist/alerts/{id}` | Delete an alert record |
| `GET` | `/watchlist/alerts/unread-count` | Unread alert count |
| `GET` | `/watchlist/test-match?plate=X` | Dry-run fuzzy match against watchlist |
| `POST` | `/config/country` | Set OCR country (`IN` / `UK` / `DE`) |
| `GET` | `/health` | Health check |

### Sample Image Detection Response

```json
{
  "detections": [
    {
      "id": 1,
      "plate_number": "MH12AB1234",
      "confidence": 0.87
    }
  ],
  "count": 1,
  "annotated_image": "<base64 JPEG>"
}
```

### Sample WebSocket Frame Response

```json
{
  "frame": "<base64 annotated JPEG>",
  "plate": "MH12AB1234",
  "confidence": 0.83,
  "timestamp": 1234.56,
  "alert": null
}
```

When a watchlist match fires, `alert` contains the full `STOLEN_VEHICLE_ALERT` payload including `detected_plate`, `watchlist_plate`, `match_score`, `confidence`, `reason`, `owner`, `description`, `alert_id`, and `frame` (base64 snapshot with red border).

---

## 🚨 Alert System

When a detected plate matches a watchlist entry (with fuzzy tolerance for OCR errors):

1. **Confidence gate** — combined confidence must be ≥ 0.75
2. **Fuzzy match** — Levenshtein similarity ≥ 0.80 (handles 1–2 character OCR errors like Z↔2, B↔8, O↔0)
3. **Cooldown** — same plate cannot re-trigger for 30 s (prevents frame-by-frame spam)
4. **Actions**: annotated frame saved to disk → Alert row written to DB → JSON broadcast to all connected WebSocket clients
5. **Frontend**: `AlertContext` receives the broadcast on `/ws/alerts` → shows full-screen modal with frame preview, plate comparison, match score, vehicle details, audio alarm, and Acknowledge button

### Adding to the Watchlist

```bash
curl -X POST http://localhost:8000/watchlist/ \
  -H "Content-Type: application/json" \
  -d '{"plate": "MH12AB1234", "reason": "stolen", "description": "White Swift Dzire", "owner_name": "Rahul Sharma"}'
```

### Bulk Import

```bash
curl -X POST http://localhost:8000/watchlist/seed \
  -H "Content-Type: application/json" \
  -d '[
    {"plate": "MH12AB1234", "reason": "stolen",  "description": "White Swift Dzire"},
    {"plate": "KA01XY5678", "reason": "wanted",  "owner_name": "Ram Kumar"},
    {"plate": "DL8CAB9999", "reason": "suspect", "description": "Black Innova"}
  ]'
```

---

## 🎨 Frontend (Next.js)

```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_WS_BASE=ws://localhost:8000
npm run dev
```

### Pages

* **Live Camera** — WebSocket camera stream at 5 fps, annotated frame overlay, live detections sidebar with confidence bars and copy-to-plate
* **Image Upload** — upload a photo, view annotated result and extracted plates
* **Detection History** — paginated log of all detections with delete support
* **Watchlist** — add/remove/view stolen & wanted vehicles
* **Alert History** — view and acknowledge all fired alerts

### Global Alert Toast

`AlertContext` opens a persistent WebSocket to `/ws/alerts` from the root layout — alert modals appear on **any page**, not just the camera view. Features:

* Red emergency modal with animated warning icon
* Detected vs watchlist plate comparison
* Match score + confidence progress bars
* Frame snapshot preview (annotated JPEG from backend)
* Web Audio API 3-beep alarm (no audio file required)
* Auto-dismisses after 15 s or on Acknowledge (which calls the acknowledge API)

---

## 🔬 Detection & OCR Pipeline

### Per-Frame Flow

```
Browser JPEG (5 fps) 
  → WS /ws/webcam
  → decode frame (cv2.imdecode)
  → detect_vehicles() [YOLOv8s COCO]  →  draw YELLOW boxes
  → detect_plates()   [best.pt]        →  draw CYAN boxes
  → for each plate crop:
      → _enhance_plate_crop()
          upscale 2× (INTER_CUBIC)
          sharpen (kernel [[0,-1,0],[-1,5,-1],[0,-1,0]])
          CLAHE (clipLimit=2.0, tileGridSize=4×4)
          adaptive threshold if dark plate
          bilateral filter
      → EasyOCR.readtext()
      → try inverted image if empty result
      → apply_plate_syntax() — syntax correction + garbage filter
  → confidence = 0.65 × det_conf + 0.35 × ocr_conf
  → if conf ≥ 0.75 and watchlist non-empty → process_alert()
  → send annotated frame + plate + alert back over WS
```

### Country Syntax Patterns

| Country | Pattern | Example |
|---|---|---|
| `IN` (India) | `LL DD LL DDDD` (10-char) | `MH12AB1234` |
| `UK` | `LL DD LLL` (7-char) | `AB12CDE` |
| `DE` (Germany) | `LLL DDDD` or `LL DDDD` | `ABC1234` |

Misread digits in letter positions (and vice versa) are auto-corrected: `O→0`, `I→1`, `Z→2`, `S→5`, `B→8`, `G→6`.

---

## 🗄️ Database

Three tables managed via SQLAlchemy ORM:

* **Detection** — every plate read: `plate_number`, `confidence`, `source` (image/video/live), `timestamp`, `image_path`, `video_timestamp`
* **WatchlistVehicle** — stolen/wanted registry: `plate`, `reason`, `owner_name`, `description`, `active` (soft delete)
* **Alert** — audit trail: `detected_plate`, `watchlist_plate`, `match_score`, `det_confidence`, `frame_path`, `acknowledged`

Default: SQLite at `backend/app/detections.db`. Set `DATABASE_URL` for PostgreSQL in production.

---

## 🧪 Upcoming Improvements

* 📊 Analytics dashboard (plates per hour, alert frequency heatmaps)
* 🧠 Multi-frame plate tracking (stabilise OCR across consecutive frames)
* 📱 SMS / push notification on alert (Fast2SMS / Twilio integration)
* 🔒 Authentication & role-based access control
* 🌍 Expanded country syntax patterns (UAE, AUS, USA)
* 🖥️ RTSP stream support for IP cameras

---

## 🤝 Contributing

Contributions are welcome!

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes
4. Open a pull request

---

## 📜 License

This project is for educational and research purposes.

---

## 🙌 Acknowledgements

* [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)
* [EasyOCR](https://github.com/JaidedAI/EasyOCR)
* [OpenCV](https://opencv.org/)
* [FastAPI](https://fastapi.tiangolo.com/)
* [Roboflow](https://roboflow.com/) — datasets and annotation workflow

---

**Guardian ANPR** — intelligent surveillance for safer roads 🛡️
