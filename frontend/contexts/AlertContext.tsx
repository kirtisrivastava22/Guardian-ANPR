"use client";
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
  ReactNode,
} from "react";

export type AlertPayload = {
  type: string;
  detection_time_utc: string;
  detected_plate: string;
  watchlist_plate: string;
  match_score: number;
  confidence: number;
  reason: string;
  owner: string;
  description: string;
  source: string;
  timestamp: number;
  alert_id: number | null;
  frame: string | null; 
};

type AlertContextValue = {
  activeAlert: AlertPayload | null;
  alertHistory: AlertPayload[];
  dismissAlert: () => void;
  pushAlert: (a: AlertPayload) => void; 
};

const AlertContext = createContext<AlertContextValue>({
  activeAlert: null,
  alertHistory: [],
  dismissAlert: () => {},
  pushAlert: () => {},
});

export function AlertProvider({ children }: { children: ReactNode }) {
  const [activeAlert, setActiveAlert] = useState<AlertPayload | null>(null);
  const [alertHistory, setAlertHistory] = useState<AlertPayload[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<AudioContext | null>(null);
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const playAlarm = useCallback(() => {
    try {
      const ctx = new AudioContext();
      audioRef.current = ctx;
      const times = [0, 0.35, 0.7];
      times.forEach((t) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = "square";
        osc.frequency.setValueAtTime(880, ctx.currentTime + t);
        osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + t + 0.25);
        gain.gain.setValueAtTime(0.18, ctx.currentTime + t);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + t + 0.28);
        osc.start(ctx.currentTime + t);
        osc.stop(ctx.currentTime + t + 0.3);
      });
    } catch {}
  }, []);

  const pushAlert = useCallback(
    (payload: AlertPayload) => {
      setActiveAlert(payload);
      setAlertHistory((h) => [payload, ...h].slice(0, 100));
      playAlarm();
      if (dismissTimer.current) clearTimeout(dismissTimer.current);
      dismissTimer.current = setTimeout(() => setActiveAlert(null), 15000);
    },
    [playAlarm]
  );

  const dismissAlert = useCallback(() => {
    if (dismissTimer.current) clearTimeout(dismissTimer.current);
    setActiveAlert(null);
  }, []);


  useEffect(() => {
    const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE ?? "";
    if (!WS_BASE) return;

    let reconnectTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      const ws = new WebSocket(`${WS_BASE}/ws/alerts`);
      wsRef.current = ws;

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === "STOLEN_VEHICLE_ALERT") {
            pushAlert(data as AlertPayload);
          }
        } catch {}
      };

      ws.onclose = () => {
        // Reconnect every 5 s
        reconnectTimer = setTimeout(connect, 5000);
      };

      ws.onerror = () => ws.close();
    };

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [pushAlert]);

  return (
    <AlertContext.Provider
      value={{ activeAlert, alertHistory, dismissAlert, pushAlert }}
    >
      {children}
    </AlertContext.Provider>
  );
}

export function useAlert() {
  return useContext(AlertContext);
}
