"use client";
import { useRef, useState, useCallback } from "react";
import { Copy, CheckCircle2, Clock, Shield, Video, Download, AlertCircle } from "lucide-react";

interface DetectionResult {
  plate: string;
  confidence: number;
  videoTimestamp: string;
  frameTime: number;
  id: string;
}

export default function LiveVideoUpload() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [plate, setPlate] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [processing, setProcessing] = useState(false);
  const [detections, setDetections] = useState<DetectionResult[]>([]);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [currentVideoTime, setCurrentVideoTime] = useState<string>("00:00.00");
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');
  const [debugInfo, setDebugInfo] = useState<string>("");

  // Refs to track state without re-renders
  const lastDetectionRef = useRef<{ plate: string; time: number } | null>(null);
  const frameCountRef = useRef(0);
  const detectionCountRef = useRef(0);

  const formatVideoTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 100);
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}.${ms.toString().padStart(2, "0")}`;
  };

  const copyToClipboard = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const exportDetections = () => {
    const csv = [
      "Video Time,License Plate,Confidence",
      ...detections.map(
        (d) =>
          `${d.videoTimestamp},${d.plate},${(d.confidence * 100).toFixed(1)}%`,
      ),
    ].join("\n");

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `plate_detections_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const addDetection = useCallback((plate: string, confidence: number, timestamp: number) => {
    // More sophisticated deduplication
    const last = lastDetectionRef.current;
    const timeDiff = last ? timestamp - last.time : Infinity;
    const isSamePlate = last?.plate === plate;
    
    // Only skip if same plate within 1 second (reduced from 2)
    if (isSamePlate && timeDiff < 1.0) {
      return;
    }

    lastDetectionRef.current = { plate, time: timestamp };
    detectionCountRef.current++;

    const newDetection: DetectionResult = {
      plate,
      confidence,
      videoTimestamp: formatVideoTime(timestamp),
      frameTime: timestamp,
      id: `${timestamp}-${detectionCountRef.current}`,
    };

    setDetections(prev => [...prev, newDetection]);
    
    // Update debug info
    setDebugInfo(`✓ Added detection #${detectionCountRef.current}: ${plate} at ${formatVideoTime(timestamp)}`);
  }, []);

  const connectWebSocket = useCallback(() => {
    if (ws) return;
    
    setConnectionStatus('connecting');
    const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE || "ws://localhost:8000";
    const socket = new WebSocket(`${WS_BASE}/ws/video`);
    
    socket.onopen = () => {
      console.log("WebSocket connected");
      setConnectionStatus('connected');
      setDebugInfo("✓ WebSocket connected successfully");
      socket.send(JSON.stringify({ type: "ping" }));
    };

    socket.binaryType = "arraybuffer";

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        frameCountRef.current++;

        // Update current plate display
        setPlate(data.plate || null);

        // Update current time
        const currentTime = data.timestamp || 0;
        setCurrentVideoTime(formatVideoTime(currentTime));

        // Add detection if valid plate found
        if (data.plate && data.plate.trim() && data.confidence > 0) {
          addDetection(data.plate.trim(), data.confidence, currentTime);
        }

        // Update canvas with annotated frame
        if (data.frame) {
          const img = new Image();
          img.src = `data:image/jpeg;base64,${data.frame}`;
          img.onload = () => {
            const ctx = canvasRef.current?.getContext("2d");
            if (ctx && canvasRef.current) {
              ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
              ctx.drawImage(img, 0, 0, canvasRef.current.width, canvasRef.current.height);
            }
          };
        }

        // Update debug every 30 frames
        if (frameCountRef.current % 30 === 0) {
          setDebugInfo(`Processed ${frameCountRef.current} frames | ${detectionCountRef.current} detections`);
        }
      } catch (error) {
        console.error("Error processing WebSocket message:", error);
        const errorMessage = error instanceof Error ? error.message : String(error);
        setDebugInfo(`⚠ Error: ${errorMessage}`);
      }
    };

    socket.onerror = (error) => {
      console.error("WebSocket error:", error);
      setConnectionStatus('disconnected');
      setDebugInfo("⚠ WebSocket error occurred");
    };

    socket.onclose = () => {
      console.log("WebSocket closed");
      setWs(null);
      setProcessing(false);
      setConnectionStatus('disconnected');
      setDebugInfo(`✓ Processing complete: ${detectionCountRef.current} detections found`);
    };

    setWs(socket);
  }, [ws, addDetection]);

  const handleStart = useCallback(() => {
    if (!file || !ws || processing) return;

    // Reset state
    setDetections([]);
    setPlate(null);
    frameCountRef.current = 0;
    detectionCountRef.current = 0;
    lastDetectionRef.current = null;
    setProcessing(true);
    setDebugInfo("▶ Starting video processing...");

    const video = videoRef.current;
    if (!video) return;

    video.src = URL.createObjectURL(file);
    video.load();
    video.playbackRate = 1.0; // Normal speed
    video.play();

    video.onplay = () => {
      let lastSent = 0;
      let pendingMetadata: number | null = null;

      const sendFrame = () => {
        if (!ws || video.paused || video.ended || ws.readyState !== WebSocket.OPEN) {
          setProcessing(false);
          setDebugInfo(`✓ Video complete: ${detectionCountRef.current} total detections`);
          return;
        }

        const now = performance.now();
        // Throttle to ~6-7 fps (150ms between frames)
        if (now - lastSent < 150) {
          requestAnimationFrame(sendFrame);
          return;
        }
        lastSent = now;

        const currentTime = video.currentTime;
        setCurrentVideoTime(formatVideoTime(currentTime));

        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        const ctx = canvas.getContext("2d");
        if (!ctx) {
          requestAnimationFrame(sendFrame);
          return;
        }

        ctx.drawImage(video, 0, 0);

        canvas.toBlob((blob) => {
          if (!blob || ws.readyState !== WebSocket.OPEN) {
            requestAnimationFrame(sendFrame);
            return;
          }

          blob.arrayBuffer().then((buffer) => {
            // Send metadata first
            ws.send(JSON.stringify({
              type: "frame_meta",
              timestamp: currentTime,
            }));

            // Then send frame immediately after
            ws.send(buffer);

            // Continue loop
            requestAnimationFrame(sendFrame);
          });
        }, "image/jpeg", 0.85); // Slightly lower quality for faster processing
      };

      sendFrame();
    };

    video.onended = () => {
      setProcessing(false);
      setDebugInfo(`✓ Video ended: ${detectionCountRef.current} total detections`);
    };
  }, [file, ws, processing]);

  const handleReset = () => {
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.currentTime = 0;
      videoRef.current.src = "";
    }
    setDetections([]);
    setPlate(null);
    setProcessing(false);
    setCurrentVideoTime("00:00.00");
    frameCountRef.current = 0;
    detectionCountRef.current = 0;
    lastDetectionRef.current = null;
    setDebugInfo("Reset complete");
  };

  const getStatusColor = () => {
    switch (connectionStatus) {
      case 'connected': return 'text-green-400';
      case 'connecting': return 'text-yellow-400';
      default: return 'text-slate-400';
    }
  };

  return (
    <div className="bg-white
  rounded-3xl
  shadow-sm
  border border-slate-200
  p-8">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-4xl font-bold text-cyan-400 flex items-center gap-3">
            <Video className="w-10 h-10" />
            Video License Plate Recognition
          </h1>
          <div className={`flex items-center gap-2 ${getStatusColor()}`}>
            <div className={`w-2 h-2 rounded-full ${connectionStatus === 'connected' ? 'bg-green-400 animate-pulse' : connectionStatus === 'connecting' ? 'bg-yellow-400 animate-pulse' : 'bg-slate-400'}`} />
            <span className="text-sm font-medium capitalize">{connectionStatus}</span>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Video Section */}
          <div className="lg:col-span-2 space-y-4">
            {/* Controls */}
            <div className=" border-2 border-dashed border-slate-300
    rounded-3xl
    bg-slate-800
    p-16
    text-center
    hover:border-slate-500
    transition-all">
              <h2 className="text-xl font-semibold text-white mb-4">
                Upload & Process
              </h2>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Select Video File
                  </label>
                  <input
                    type="file"
                    accept="video/*"
                    onChange={(e) => {
                      const selectedFile = e.target.files?.[0] || null;
                      setFile(selectedFile);
                      if (selectedFile) {
                        setDebugInfo(`✓ Selected: ${selectedFile.name} (${(selectedFile.size / 1024 / 1024).toFixed(2)} MB)`);
                      }
                    }}
                    className={
                      "block w-full text-sm text-slate-300 " +
                      "file:mr-4 file:py-2 file:px-4 " +
                      "file:rounded-lg file:border-0 " +
                      "file:text-sm file:font-semibold " +
                      "file:bg-cyan-600 file:text-white " +
                      "hover:file:bg-cyan-700 " +
                      "file:cursor-pointer cursor-pointer " +
                      "bg-slate-700/50 rounded-lg border border-slate-600"
                    }
                  />
                  {file && (
                    <p className="mt-2 text-sm text-slate-400">
                      {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
                    </p>
                  )}
                </div>

                <div className="flex gap-3 flex-wrap">
                  <button
                    onClick={connectWebSocket}
                    disabled={!!ws}
                    className="px-5 py-3
    rounded-xl
    bg-slate-900
    text-white
    font-medium
    hover:bg-slate-800
    transition-all
    duration-300"
                  >
                    {ws ? "Connected ✓" : "Connect"}
                  </button>

                  <button
                    onClick={handleStart}
                    disabled={!file || !ws || processing}
                    className="px-6 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-slate-600 disabled:cursor-not-allowed font-medium transition-colors flex items-center gap-2"
                  >
                    {processing ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        Processing...
                      </>
                    ) : (
                      "Start Detection"
                    )}
                  </button>

                  <button
                    onClick={handleReset}
                    className="px-5 py-3
    rounded-xl
    bg-slate-900
    text-white
    font-medium
    hover:bg-slate-800
    transition-all
    duration-300"
                  >
                    Reset
                  </button>

                  {detections.length > 0 && (
                    <button
                      onClick={exportDetections}
                      className="px-6 py-2.5
    rounded-xl
    bg-slate-900
    text-white
    font-medium
    hover:bg-slate-800
    transition-all
    duration-300"
                      title="Export to CSV"
                    >
                      <Download className="w-4 h-4" />
                      Export CSV
                    </button>
                  )}
                </div>

                {/* Debug Info */}
                {debugInfo && (
                  <div className="mt-4 p-3 bg-slate-700/50 rounded-lg border border-slate-600">
                    <p className="text-xs text-slate-300 font-mono">{debugInfo}</p>
                  </div>
                )}
              </div>
            </div>

            {/* Video Display */}
            <div className="bg-slate-800 backdrop-blur rounded-xl p-6 border border-slate-700">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-white">
                  Live Feed
                </h2>
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-2 text-cyan-400 font-mono text-sm">
                    <Clock className="w-4 h-4" />
                    <span>{currentVideoTime}</span>
                  </div>
                  <div className="text-xs text-slate-400">
                    Frames: {frameCountRef.current}
                  </div>
                </div>
              </div>

              <video ref={videoRef} className="hidden" />
              <canvas
                ref={canvasRef}
                width={640}
                height={480}
                className="w-full rounded-lg border-2 border-cyan-500/50 bg-slate-900"
              />

              {plate && (
                <div className="mt-4 p-4 bg-green-500/10 border border-green-500/30 rounded-lg animate-pulse">
                  <p className="text-green-400 font-semibold text-lg">
                    Current Detection:{" "}
                    <span className="font-mono text-2xl">{plate}</span>
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Detection Results Sidebar */}
          <div className="lg:col-span-1">
            <div className="bg-slate-800 backdrop-blur rounded-xl p-6 border border-slate-700 sticky top-6">
              <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-cyan-400" />
                Detection Results
              </h2>

              <div className="mb-4 p-3 bg-slate-700/50 rounded-lg">
                <p className="text-sm text-slate-300">
                  Total Detections:{" "}
                  <span className="font-bold text-cyan-400 text-xl">
                    {detections.length}
                  </span>
                </p>
                {processing && (
                  <p className="text-xs text-slate-400 mt-1">
                    Unique plates: {new Set(detections.map(d => d.plate)).size}
                  </p>
                )}
              </div>

              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2 custom-scrollbar">
                {detections.length === 0 ? (
                  <div className="text-center py-12 text-slate-400">
                    <Video className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    <p>No detections yet</p>
                    <p className="text-xs mt-1">
                      Start processing to see results
                    </p>
                  </div>
                ) : (
                  [...detections].reverse().map((detection, index) => {
                    const actualIndex = detections.length - 1 - index;
                    return (
                      <div
                        key={detection.id}
                        className="bg-slate-700/50 rounded-lg p-4 border border-slate-600 hover:border-cyan-500/50 transition-all group animate-fadeIn"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              <Clock className="w-4 h-4 text-cyan-400" />
                              <span className="font-mono text-sm font-semibold text-cyan-400">
                                {detection.videoTimestamp}
                              </span>
                            </div>
                            <p className="font-mono text-xl font-bold text-white">
                              {detection.plate}
                            </p>
                          </div>

                          <button
                            onClick={() =>
                              copyToClipboard(detection.plate, actualIndex)
                            }
                            className="px-5 py-3
    rounded-xl
    bg-slate-900
    text-white
    font-medium
    hover:bg-slate-800
    transition-all
    duration-300"
                            title="Copy to clipboard"
                          >
                            {copiedIndex === actualIndex ? (
                              <CheckCircle2 className="w-4 h-4 text-green-400" />
                            ) : (
                              <Copy className="w-4 h-4 text-slate-400 group-hover:text-cyan-400" />
                            )}
                          </button>
                        </div>

                        {detection.confidence > 0 && (
                          <div className="mt-3">
                            <div className="flex items-center justify-between text-xs mb-1">
                              <span className="text-slate-400">Confidence</span>
                              <span className="text-cyan-400 font-semibold">
                                {(detection.confidence * 100).toFixed(1)}%
                              </span>
                            </div>
                            <div className="w-full bg-slate-600 rounded-full h-1.5">
                              <div
                                className="bg-gradient-to-r from-cyan-500 to-green-500 h-1.5 rounded-full transition-all"
                                style={{
                                  width: `${detection.confidence * 100}%`,
                                }}
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <style dangerouslySetInnerHTML={{__html: `
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(51, 65, 85, 0.3);
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(6, 182, 212, 0.5);
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(6, 182, 212, 0.7);
        }
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .animate-fadeIn {
          animation: fadeIn 0.3s ease-out;
        }
      `}} />
    </div>
  );
}
