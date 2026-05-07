"use client";

import { useEffect, useRef, useState } from "react";
import Navbar from "@/components/Navbar";

export default function CameraPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState("Connecting to server...");
  const [isRecording, setIsRecording] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");
  const streamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const deviceIdRef = useRef<string>("");
  const sessionIdRef = useRef<string>("");
  const uploadQueueRef = useRef<Promise<Response | void>>(Promise.resolve());
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Camera setup ──────────────────────────────────────────────────────────
  const setupCamera = async (deviceId?: string) => {
    // Stop any existing tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
    }

    try {
      const constraints: MediaStreamConstraints = {
        video: deviceId
          ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
          : { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: true,
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      // After getting permission, enumerate devices to get labels
      const allDevices = await navigator.mediaDevices.enumerateDevices();
      const videoDevices = allDevices.filter((d) => d.kind === "videoinput");
      setDevices(videoDevices);

      // If we didn't have a selected ID, pick the one we just got
      if (!deviceId && videoDevices.length > 0) {
        const currentTrack = stream.getVideoTracks()[0];
        const currentId = currentTrack.getSettings().deviceId;
        if (currentId) {
          setSelectedDeviceId(currentId);
        }
      }
    } catch (error: any) {
      const isHttps = window.location.protocol === "https:";
      setStatus(`❌ Camera error: ${error.name}`);
      console.error("Camera setup failed:", error);
      if (error.name !== "AbortError") {
        alert(
          `Camera failed: ${error.name}\n${error.message}\n\n` +
            (!isHttps ? "⚠️ iOS Safari requires HTTPS. Use the https:// URL." : "Allow camera in Safari Settings.")
        );
      }
    }
  };

  // ── WebSocket connect with auto-reconnect ─────────────────────────────────
  const connectWs = () => {
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    
    const wsProtocol = window.location.protocol === "https:" ? "wss://" : "ws://";
    let wsHost = window.location.host;
    
    // If accessing frontend directly on port 3000, route WS to backend port 8000
    if (window.location.port === "3000") {
      wsHost = `${window.location.hostname}:8000`;
    }
    
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

    ws.onerror = (err) => {
      console.error("WebSocket error details:", err);
      ws.close();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.command === "start" && streamRef.current) {
          // Use the session_id sent from the dashboard
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

  const handleManualReconnect = () => {
    setStatus("🔄 Reconnecting manually...");
    if (wsRef.current) {
      wsRef.current.onclose = null; // Prevent the auto-reconnect from firing again
      wsRef.current.close();
    }
    connectWs();
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
    
    // Check for saved device ID
    const savedDeviceId = localStorage.getItem("preferred_camera_id");
    if (savedDeviceId) {
      setSelectedDeviceId(savedDeviceId);
      setupCamera(savedDeviceId);
    } else {
      setupCamera();
    }
    
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
          .then(() => fetch("/api/live/upload", { method: "POST", body: formData }))
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
          {!window.isSecureContext && window.location.hostname !== "localhost" && (
            <div style={{ 
              fontSize: 11, 
              color: "#f1c40f", 
              backgroundColor: "rgba(241, 196, 15, 0.1)", 
              padding: "2px 8px", 
              borderRadius: 4,
              border: "1px solid #f1c40f"
            }}>
              ⚠️ Insecure Context (Camera may fail)
            </div>
          )}
          {!wsConnected && (
            <button
              onClick={handleManualReconnect}
              style={{
                marginLeft: 8,
                padding: "4px 12px",
                borderRadius: 20,
                backgroundColor: "rgba(231, 76, 60, 0.2)",
                border: "1px solid #e74c3c",
                color: "#e74c3c",
                fontSize: 11,
                fontWeight: "bold",
                cursor: "pointer",
                transition: "all 0.2s",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "rgba(231, 76, 60, 0.3)")}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "rgba(231, 76, 60, 0.2)")}
            >
              RECONNECT NOW
            </button>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "center", flexDirection: "column", alignItems: "center", gap: 16 }}>
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

          {/* Camera Selection Dropdown */}
          {!isRecording && devices.length > 1 && (
            <div style={{ width: "100%", maxWidth: 400, textAlign: "left" }}>
              <label style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4, display: "block" }}>
                Select Camera
              </label>
              <select
                value={selectedDeviceId}
                onChange={(e) => {
                  const newId = e.target.value;
                  setSelectedDeviceId(newId);
                  localStorage.setItem("preferred_camera_id", newId);
                  setupCamera(newId);
                }}
                style={{
                  width: "100%",
                  padding: "12px 16px",
                  borderRadius: 12,
                  backgroundColor: "rgba(255, 255, 255, 0.05)",
                  backdropFilter: "blur(10px)",
                  color: "white",
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                  fontSize: 15,
                  outline: "none",
                  cursor: "pointer",
                  appearance: "none",
                  backgroundImage: `url("data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2212%22%20height%3D%2212%22%20viewBox%3D%220%200%2012%2012%22%3E%3Cpath%20fill%3D%22white%22%20d%3D%22M10.293%203.293L6%207.586%201.707%203.293A1%201%200%2000.293%201.707l5%205a1%201%200%20001.414%200l5-5a1%201%200%2010-1.414-1.414z%22%2F%3E%3C%2Fsvg%3E")`,
                  backgroundRepeat: "no-repeat",
                  backgroundPosition: "right 16px center",
                  boxShadow: "0 4px 20px rgba(0, 0, 0, 0.2)",
                  transition: "all 0.2s ease",
                }}
              >
                {devices.map((device, idx) => (
                  <option key={device.deviceId} value={device.deviceId} style={{ backgroundColor: "#1c1c1e" }}>
                    {device.label || `Camera ${idx + 1}`}
                  </option>
                ))}
              </select>
            </div>
          )}
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
