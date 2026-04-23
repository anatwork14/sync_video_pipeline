"use client";

import { useEffect, useRef, useState } from "react";
import Navbar from "@/components/Navbar";

export default function CameraPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState("Connecting to server...");
  const [isRecording, setIsRecording] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const streamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const deviceIdRef = useRef<string>("");
  const sessionIdRef = useRef<string>("");
  const uploadQueueRef = useRef<Promise<Response | void>>(Promise.resolve());
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Camera setup ──────────────────────────────────────────────────────────
  const setupCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: true,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch (error: any) {
      const isHttps = window.location.protocol === "https:";
      setStatus(`❌ Camera error: ${error.name}`);
      alert(
        `Camera failed: ${error.name}\n${error.message}\n\n` +
          (!isHttps ? "⚠️ iOS Safari requires HTTPS. Use the https:// URL." : "Allow camera in Safari Settings.")
      );
    }
  };

  // ── WebSocket connect with auto-reconnect ─────────────────────────────────
  const connectWs = () => {
    const wsProtocol = window.location.protocol === "https:" ? "wss://" : "ws://";
    const wsHost = window.location.host;
    const ws = new WebSocket(`${wsProtocol}${wsHost}/ws/camera`);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      setStatus("✅ Connected. Waiting for record command...");
      // Announce presence
      ws.send(JSON.stringify({ type: "hello", id: deviceIdRef.current }));
    };

    ws.onclose = () => {
      setWsConnected(false);
      setStatus("⚠️ Disconnected. Reconnecting in 3s...");
      // Auto-reconnect
      reconnectTimer.current = setTimeout(connectWs, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.command === "start" && streamRef.current) {
          // Use the session_id sent from the dashboard — this is the key fix
          sessionIdRef.current = data.session_id ?? Date.now().toString();
          startRecording();
        } else if (data.command === "stop") {
          stopRecording();
        }
      } catch {
        // ignore parse errors
      }
    };
  };

  // ── Preview frame loop (independent of WS — uses latest ws ref) ──────────
  const previewIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startPreviewLoop = () => {
    previewIntervalRef.current = setInterval(() => {
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN && streamRef.current && videoRef.current) {
        const canvas = document.createElement("canvas");
        canvas.width = 320;
        canvas.height = 240;
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
          const base64Image = canvas.toDataURL("image/jpeg", 0.5);
          ws.send(JSON.stringify({ type: "preview", id: deviceIdRef.current, image: base64Image }));
        }
      }
    }, 500);
  };

  useEffect(() => {
    deviceIdRef.current = Math.random().toString(36).substring(2, 8);
    setupCamera();
    connectWs();
    startPreviewLoop();

    return () => {
      stopRecording();
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
      wsRef.current?.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (previewIntervalRef.current) clearInterval(previewIntervalRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Recording ─────────────────────────────────────────────────────────────
  const startRecording = () => {
    if (!streamRef.current) {
      setStatus("❌ Camera stream not ready");
      return;
    }
    if (mediaRecorderRef.current?.state === "recording") return; // already recording

    try {
      const mimeType = MediaRecorder.isTypeSupported("video/webm; codecs=vp8,opus")
        ? "video/webm; codecs=vp8,opus"
        : MediaRecorder.isTypeSupported("video/mp4")
        ? "video/mp4"
        : "";

      const mediaRecorder = new MediaRecorder(streamRef.current, mimeType ? { mimeType } : {});
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (!event.data || event.data.size === 0) return;

        // session_id must be set before we start recording — guaranteed because
        // we set it in the WS onmessage handler before calling startRecording()
        const sid = sessionIdRef.current;
        const did = deviceIdRef.current;
        if (!sid) {
          console.warn("No session_id yet — dropping chunk");
          return;
        }

        const formData = new FormData();
        const ext = mimeType.includes("mp4") ? "mp4" : "webm";
        formData.append("file", event.data, `stream.${ext}`);
        formData.append("device_id", did);
        formData.append("session_id", sid);

        uploadQueueRef.current = uploadQueueRef.current
          .then(() => fetch("/upload", { method: "POST", body: formData }))
          .then((res) => {
            if (!res.ok) console.error("Upload error:", res.status, res.statusText);
          })
          .catch((err) => console.error("Upload failed:", err));
      };

      mediaRecorder.start(2000); // 2-second chunks
      setIsRecording(true);
      setStatus(`🔴 RECORDING  (session: ${sessionIdRef.current})`);
    } catch (e) {
      console.error("Failed to start recording:", e);
      setStatus("❌ MediaRecorder failed. Check browser support.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    setStatus("⏹ Stopped. Waiting for command...");
  };

  return (
    <>
      <Navbar />
      <main className="container" style={{ paddingTop: 40, textAlign: "center", minHeight: "100vh" }}>
        <h2 className="page-title" style={{ marginBottom: 20 }}>📱 Camera Node</h2>

        {/* Connection status dot */}
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              backgroundColor: wsConnected ? "#2ecc71" : "#e74c3c",
              display: "inline-block",
              boxShadow: wsConnected ? "0 0 8px #2ecc71" : "0 0 8px #e74c3c",
            }}
          />
          <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {wsConnected ? `Server connected · Device ${deviceIdRef.current}` : "Not connected"}
          </span>
        </div>

        <div style={{ display: "flex", justifyContent: "center" }}>
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            style={{
              width: "100%",
              maxWidth: 400,
              backgroundColor: "black",
              borderRadius: 8,
              border: isRecording ? "4px solid #e74c3c" : "4px solid #333",
              transition: "border 0.3s",
            }}
          />
        </div>

        <div
          style={{
            marginTop: 20,
            fontSize: 18,
            fontWeight: "bold",
            color: isRecording ? "#e74c3c" : wsConnected ? "#2ecc71" : "#f39c12",
          }}
        >
          {status}
        </div>

        {sessionIdRef.current && (
          <div style={{ marginTop: 8, color: "var(--text-muted)", fontSize: 12 }}>
            Session: {sessionIdRef.current}
          </div>
        )}
      </main>
    </>
  );
}
