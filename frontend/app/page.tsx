"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { Play, Square, CheckCircle2, Clock, Camera, Copy } from "lucide-react";
import { useAlert } from "../contexts/AlertContext";

type Detection = {
  plate: string;
  confidence: number;
  timestamp: string;
};

// Send at most this many frames per second to avoid flooding the WebSocket
const TARGET_FPS = 5;
const FRAME_INTERVAL_MS = 1000 / TARGET_FPS;

export default function LivePage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const rafRef = useRef<number | null>(null);
  const lastSendRef = useRef<number>(0);
  const offscreenRef = useRef<HTMLCanvasElement | null>(null);
  const offCtxRef = useRef<CanvasRenderingContext2D | null>(null);

  const [active, setActive] = useState(false);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [wsStatus, setWsStatus] = useState<"disconnected" | "connecting" | "connected">(
    "disconnected"
  );

  const { pushAlert } = useAlert();

  /* ---------- FRAME SEND LOOP ---------- */
  const sendFrames = useCallback(() => {
    const loop = (now: number) => {
      rafRef.current = requestAnimationFrame(loop);

      const video = videoRef.current;
      const ws = wsRef.current;

      if (!video || !ws || ws.readyState !== WebSocket.OPEN) return;
      if (video.readyState < 2) return; // not enough data yet

      // Throttle to TARGET_FPS
      if (now - lastSendRef.current < FRAME_INTERVAL_MS) return;
      lastSendRef.current = now;

      // Reuse offscreen canvas
      if (!offscreenRef.current) {
        offscreenRef.current = document.createElement("canvas");
      }
      const oc = offscreenRef.current;
      if (oc.width !== video.videoWidth || oc.height !== video.videoHeight) {
        oc.width = video.videoWidth;
        oc.height = video.videoHeight;
        offCtxRef.current = oc.getContext("2d");
      }
      const ctx = offCtxRef.current;
      if (!ctx) return;

      ctx.drawImage(video, 0, 0);
      oc.toBlob(
        (blob) => {
          if (blob && ws.readyState === WebSocket.OPEN) {
            ws.send(blob);
          }
        },
        "image/jpeg",
        0.7
      );
    };

    rafRef.current = requestAnimationFrame(loop);
  }, []);

  /* ---------- START CAMERA ---------- */
  const start = async () => {
    if (active) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 } },
      });

      const video = videoRef.current!;
      video.srcObject = stream;
      await video.play();

      video.onloadedmetadata = () => {
        const canvas = canvasRef.current!;
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
      };
    } catch (err) {
      console.error("[Camera] getUserMedia failed:", err);
      return;
    }

    const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE ?? "";
    setWsStatus("connecting");

    const ws = new WebSocket(`${WS_BASE}/ws/webcam`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus("connected");
      ws.send(JSON.stringify({ type: "ping" }));
      sendFrames();
    };

    ws.onmessage = (e) => {
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(e.data);
      } catch {
        return;
      }

      // Pong keepalive
      if (data.type === "pong") return;

      // Draw annotated frame back on canvas
      if (data.frame && typeof data.frame === "string") {
        const img = new Image();
        img.onload = () => {
          const canvas = canvasRef.current;
          if (!canvas) return;
          const ctx = canvas.getContext("2d");
          if (!ctx) return;
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        };
        img.src = `data:image/jpeg;base64,${data.frame}`;
      }

      // Inline alert from video response (fires when backend sends alert alongside frame)
      if (data.alert && typeof data.alert === "object" && data.alert !== null) {
        pushAlert(data.alert as Parameters<typeof pushAlert>[0]);
      }

      // Store plate detection
      if (data.plate && typeof data.plate === "string") {
        const plate = data.plate;
        const confidence = typeof data.confidence === "number" ? data.confidence : 0;
        setDetections((prev) => {
          // Deduplicate consecutive identical plates
          if (prev[0]?.plate === plate) return prev;
          return [
            {
              plate,
              confidence,
              timestamp: new Date().toLocaleTimeString(),
            },
            ...prev,
          ].slice(0, 20);
        });
      }
    };

    ws.onclose = () => {
      setWsStatus("disconnected");
    };

    ws.onerror = (err) => {
      console.error("[WS] error", err);
      setWsStatus("disconnected");
    };

    setActive(true);
  };

  /* ---------- STOP ---------- */
  const stop = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }

    wsRef.current?.close();
    wsRef.current = null;

    const stream = videoRef.current?.srcObject as MediaStream | null;
    stream?.getTracks().forEach((t) => t.stop());
    if (videoRef.current) videoRef.current.srcObject = null;

    setActive(false);
    setWsStatus("disconnected");
  }, []);

  const copyPlate = (plate: string, index: number) => {
    navigator.clipboard.writeText(plate).catch(() => {});
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 1500);
  };

  useEffect(() => () => stop(), [stop]);

  const statusColor =
    wsStatus === "connected"
      ? "bg-green-500"
      : wsStatus === "connecting"
      ? "bg-amber-400 animate-pulse"
      : "bg-slate-500";

  /* ---------- UI ---------- */
  return (
    <div className="bg-white rounded-3xl shadow-sm border border-slate-200 p-8">
      <div className="max-w-7xl mx-auto">
        {/* HEADER */}
        <h1 className="text-4xl font-bold text-cyan-400 mb-8 flex items-center gap-3">
          <Camera className="w-10 h-10" />
          Live Camera License Plate Recognition
        </h1>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* CAMERA PANEL */}
          <div className="lg:col-span-2 space-y-4">
            <div className="bg-slate-900 backdrop-blur rounded-xl p-6 border border-slate-700">
              <div className="flex justify-between items-center mb-4">
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-semibold text-white">
                    Live Camera Feed
                  </h2>
                  {/* WS status indicator */}
                  <span className="flex items-center gap-1.5 text-xs text-slate-400">
                    <span className={`w-2 h-2 rounded-full ${statusColor}`} />
                    {wsStatus}
                  </span>
                </div>
                <button
                  onClick={active ? stop : start}
                  className={`flex items-center gap-2 px-5 py-3 rounded-xl text-white font-medium transition-all duration-300 ${
                    active
                      ? "bg-red-600 hover:bg-red-700"
                      : "bg-green-600 hover:bg-green-700"
                  }`}
                >
                  {active ? <Square className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                  {active ? "Stop" : "Start"}
                </button>
              </div>

              <div className="relative aspect-video bg-black rounded-lg overflow-hidden border-2 border-cyan-500/40">
                {/* Raw camera (hidden behind canvas) */}
                <video
                  ref={videoRef}
                  muted
                  playsInline
                  className="absolute inset-0 w-full h-full object-cover"
                />

                {/* Annotated output overlaid on top */}
                <canvas
                  ref={canvasRef}
                  className="absolute inset-0 w-full h-full pointer-events-none"
                />

                {!active && (
                  <div className="absolute inset-0 flex items-center justify-center text-slate-400 select-none">
                    Camera Offline
                  </div>
                )}
              </div>

              {/* FPS note */}
              <p className="text-xs text-slate-500 mt-2 text-right">
                Sending at {TARGET_FPS} fps to server
              </p>
            </div>
          </div>

          {/* DETECTIONS SIDEBAR */}
          <div className="lg:col-span-1">
            <div className="bg-slate-800 backdrop-blur rounded-xl p-6 border border-slate-700 sticky top-6">
              <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-cyan-400" />
                Live Detections
              </h2>

              <div className="mb-4 text-sm text-slate-300">
                Total Plates:{" "}
                <span className="font-bold text-cyan-400">{detections.length}</span>
              </div>

              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
                {detections.length === 0 ? (
                  <div className="text-center py-12 text-slate-400">
                    <Camera className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    Waiting for vehicles…
                  </div>
                ) : (
                  detections.map((d, i) => (
                    <div
                      key={i}
                      className="bg-slate-700/50 rounded-lg p-4 border border-slate-600 hover:border-cyan-500/50 transition group"
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="flex items-center gap-2 text-xs text-cyan-400 mb-1">
                            <Clock className="w-4 h-4" />
                            {d.timestamp}
                          </div>
                          <p className="font-mono text-xl font-bold text-white">
                            {d.plate}
                          </p>
                        </div>

                        <button
                          onClick={() => copyPlate(d.plate, i)}
                          className="p-2 rounded-xl bg-slate-900 text-white hover:bg-slate-800 transition-all duration-300"
                          aria-label={`Copy plate ${d.plate}`}
                        >
                          {copiedIndex === i ? (
                            <CheckCircle2 className="w-4 h-4 text-green-400" />
                          ) : (
                            <Copy className="w-4 h-4 text-slate-400 group-hover:text-cyan-400" />
                          )}
                        </button>
                      </div>

                      <div className="mt-3">
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-slate-400">Confidence</span>
                          <span className="text-cyan-400 font-semibold">
                            {Math.round(d.confidence * 100)}%
                          </span>
                        </div>
                        <div className="w-full bg-slate-600 rounded-full h-1.5">
                          <div
                            className="bg-cyan-500 h-1.5 rounded-full"
                            style={{ width: `${d.confidence * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}