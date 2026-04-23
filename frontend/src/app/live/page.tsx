"use client";

import { useEffect, useState, useRef } from "react";
import Navbar from "@/components/Navbar";

export default function LivePage() {
  const [cameras, setCameras] = useState<{ id: string; image: string; lastSeen: number }[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const connect = () => {
      const protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
      const wsHost = window.location.host;
      const ws = new WebSocket(`${protocol}${wsHost}/ws/dashboard`);
      wsRef.current = ws;

      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => {
        setWsConnected(false);
        setTimeout(connect, 3000); // auto-reconnect
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "preview") {
            setCameras((prev) => {
              const now = Date.now();
              const existing = prev.find((c) => c.id === data.id);
              if (existing) {
                return prev.map((c) =>
                  c.id === data.id ? { ...c, image: data.image, lastSeen: now } : c
                );
              } else {
                return [...prev, { id: data.id, image: data.image, lastSeen: now }];
              }
            });
          } else if (data.type === "disconnect") {
            setCameras((prev) => prev.filter((c) => c.id !== data.id));
          } else if (data.type === "info") {
            if (data.message === "ESP32_STARTED" || data.message === "STARTED") {
              setIsRecording(true);
              if (data.session_id) setSessionId(data.session_id);
            } else if (data.message === "STOPPED") {
              setIsRecording(false);
            }
          }
        } catch {}
      };
    };

    connect();

    // Watchdog timer to remove phantom cameras
    const interval = setInterval(() => {
      const now = Date.now();
      setCameras((prev) => prev.filter((c) => now - c.lastSeen < 2500));
    }, 1000);

    return () => {
      wsRef.current?.close();
      clearInterval(interval);
    };
  }, []);

  const handleStart = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const sid = Date.now().toString();
      setSessionId(sid);
      setIsRecording(true);
      wsRef.current.send(JSON.stringify({ command: "start", session_id: sid }));
    }
  };

  const handleStop = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      setIsRecording(false);
      wsRef.current.send(JSON.stringify({ command: "stop" }));
    }
  };

  return (
    <>
      <Navbar />
      <main className="container" style={{ paddingTop: 40, minHeight: "100vh" }}>
        <div className="page-header" style={{ textAlign: "center", marginBottom: 20 }}>
          <h1 className="page-title">🎬 Master Control Dashboard</h1>
          <p className="page-subtitle">Real-time synchronized multi-camera control panel</p>
        </div>

        {/* Status bar */}
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 20, marginBottom: 24, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: wsConnected ? "#2ecc71" : "#e74c3c", display: "inline-block", boxShadow: wsConnected ? "0 0 8px #2ecc71" : "0 0 8px #e74c3c" }} />
            <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{wsConnected ? "Server connected" : "Reconnecting..."}</span>
          </div>
          {sessionId && (
            <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "monospace" }}>
              Session: <strong style={{ color: isRecording ? "#e74c3c" : "var(--text-secondary)" }}>{sessionId}</strong>
              {isRecording && <span style={{ marginLeft: 8 }}>🔴 Recording</span>}
            </div>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "center", gap: 20, marginBottom: 40 }}>
          <button
            onClick={handleStart}
            disabled={isRecording || !wsConnected}
            style={{
              padding: "15px 30px",
              fontSize: 18,
              cursor: isRecording || !wsConnected ? "not-allowed" : "pointer",
              borderRadius: 5,
              border: "none",
              background: isRecording ? "#7f1d1d" : "#e74c3c",
              color: "white",
              fontWeight: "bold",
              opacity: isRecording ? 0.6 : 1,
            }}
          >
            🔴 RECORD ALL
          </button>
          <button
            onClick={handleStop}
            disabled={!isRecording || !wsConnected}
            style={{
              padding: "15px 30px",
              fontSize: 18,
              cursor: !isRecording || !wsConnected ? "not-allowed" : "pointer",
              borderRadius: 5,
              border: "none",
              background: "#95a5a6",
              color: "white",
              fontWeight: "bold",
              opacity: !isRecording ? 0.6 : 1,
            }}
          >
            ⏹ STOP ALL
          </button>
        </div>

        <div
          className="camera-grid"
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: 20,
          }}
        >
          {cameras.length === 0 ? (
            <div style={{ color: "var(--text-secondary)", marginTop: 40 }}>
              Waiting for cameras to connect...
            </div>
          ) : (
            cameras.map((cam) => (
              <div
                key={cam.id}
                className="cam-view card"
                style={{
                  background: "#333",
                  padding: 10,
                  borderRadius: 8,
                  border: "2px solid #555",
                  textAlign: "center",
                }}
              >
                <h3 style={{ margin: "0 0 10px 0", color: "#fff", fontSize: 16 }}>
                  Camera: {cam.id}
                </h3>
                <img
                  src={cam.image}
                  alt={`Cam ${cam.id}`}
                  style={{
                    width: 320,
                    height: 240,
                    backgroundColor: "black",
                    borderRadius: 4,
                    objectFit: "cover",
                  }}
                />
              </div>
            ))
          )}
        </div>
      </main>
    </>
  );
}
