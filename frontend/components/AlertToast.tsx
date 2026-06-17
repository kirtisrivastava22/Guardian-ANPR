"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, X, CheckCircle2, Clock, Car, Shield } from "lucide-react";
import { useAlert } from "../contexts/AlertContext";

export default function AlertToast() {
  const { activeAlert, dismissAlert } = useAlert();
  const [visible, setVisible] = useState(false);

  // Animate in/out
  useEffect(() => {
    if (activeAlert) {
      // Small delay so CSS transition fires
      requestAnimationFrame(() => setVisible(true));
    } else {
      setVisible(false);
    }
  }, [activeAlert]);

  if (!activeAlert) return null;

  const matchPct = Math.round(activeAlert.match_score * 100);
  const confPct = Math.round(activeAlert.confidence * 100);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity duration-300"
        style={{ opacity: visible ? 1 : 0 }}
        onClick={dismissAlert}
        aria-hidden="true"
      />

      {/* Toast panel */}
      <div
        role="alertdialog"
        aria-modal="true"
        aria-label="Stolen vehicle detected"
        className="fixed z-50 transition-all duration-300"
        style={{
          top: "50%",
          left: "50%",
          transform: `translate(-50%, ${visible ? "-50%" : "-40%"})`,
          opacity: visible ? 1 : 0,
          width: "min(92vw, 580px)",
        }}
      >
        <div className="rounded-2xl overflow-hidden shadow-2xl border border-red-500/40">
          {/* Header bar */}
          <div className="bg-red-600 px-5 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-6 h-6 text-white animate-pulse" />
              <div>
                <p className="text-white font-bold text-lg leading-tight tracking-wide">
                  ⚠ STOLEN VEHICLE DETECTED
                </p>
                <p className="text-red-200 text-xs mt-0.5 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {activeAlert.detection_time_utc}
                </p>
              </div>
            </div>
            <button
              onClick={dismissAlert}
              className="text-red-200 hover:text-white transition-colors p-1 rounded-lg hover:bg-red-700"
              aria-label="Dismiss alert"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Body */}
          <div className="bg-slate-900 p-5 space-y-4">
            {/* Plate comparison */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-slate-800 rounded-xl p-4 border border-red-500/30">
                <p className="text-xs text-slate-400 mb-1 uppercase tracking-wider">
                  Detected plate
                </p>
                <p className="font-mono text-2xl font-bold text-white">
                  {activeAlert.detected_plate}
                </p>
              </div>
              <div className="bg-slate-800 rounded-xl p-4 border border-amber-500/30">
                <p className="text-xs text-slate-400 mb-1 uppercase tracking-wider">
                  Watchlist plate
                </p>
                <p className="font-mono text-2xl font-bold text-amber-400">
                  {activeAlert.watchlist_plate}
                </p>
              </div>
            </div>

            {/* Confidence bars */}
            <div className="space-y-2">
              <ConfBar label="Match score" value={matchPct} color="bg-red-500" />
              <ConfBar label="Detection confidence" value={confPct} color="bg-cyan-500" />
            </div>

            {/* Vehicle details */}
            <div className="bg-slate-800 rounded-xl p-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm border border-slate-700">
              <Detail icon={<Shield className="w-3.5 h-3.5" />} label="Reason" value={activeAlert.reason} />
              <Detail icon={<Car className="w-3.5 h-3.5" />} label="Source" value={activeAlert.source} />
              {activeAlert.owner && (
                <Detail label="Owner" value={activeAlert.owner} />
              )}
              {activeAlert.description && (
                <Detail label="Vehicle" value={activeAlert.description} className="col-span-2" />
              )}
            </div>

            {/* Frame snapshot */}
            {activeAlert.frame && (
              <div className="rounded-xl overflow-hidden border-2 border-red-500/50">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`data:image/jpeg;base64,${activeAlert.frame}`}
                  alt="Captured frame showing detected vehicle"
                  className="w-full object-cover"
                  style={{ maxHeight: "220px" }}
                />
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-1">
              <button
                onClick={dismissAlert}
                className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl bg-slate-700 hover:bg-slate-600 text-white text-sm font-medium transition-colors"
              >
                <X className="w-4 h-4" />
                Dismiss
              </button>
              <button
                onClick={async () => {
                  if (activeAlert.alert_id) {
                    const base = process.env.NEXT_PUBLIC_API_BASE ?? "";
                    await fetch(
                      `${base}/watchlist/alerts/${activeAlert.alert_id}/acknowledge`,
                      { method: "POST" }
                    ).catch(() => {});
                  }
                  dismissAlert();
                }}
                className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl bg-red-600 hover:bg-red-700 text-white text-sm font-medium transition-colors"
              >
                <CheckCircle2 className="w-4 h-4" />
                Acknowledge
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function ConfBar({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-slate-400">{label}</span>
        <span className="text-white font-medium">{value}%</span>
      </div>
      <div className="w-full bg-slate-700 rounded-full h-1.5">
        <div
          className={`${color} h-1.5 rounded-full transition-all duration-500`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

function Detail({
  icon,
  label,
  value,
  className = "",
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <p className="text-slate-400 text-xs flex items-center gap-1 mb-0.5">
        {icon}
        {label}
      </p>
      <p className="text-white font-medium capitalize">{value}</p>
    </div>
  );
}