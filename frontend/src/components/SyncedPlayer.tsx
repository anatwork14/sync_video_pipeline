"use client";

import { useEffect, useRef } from "react";

interface SyncedPlayerProps {
  url: string;
  title?: string;
  onEnded?: () => void;
}

/**
 * A sleek, custom video player for synced outputs.
 * In Phase 1, it plays static synced_chunk_N.mp4 files.
 * In Phase 2, this will be upgraded to an HLS.js player.
 */
export default function SyncedPlayer({ url, title, onEnded }: SyncedPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  // Auto-play when the URL changes (e.g. next chunk is ready)
  useEffect(() => {
    if (videoRef.current && url) {
      videoRef.current.load();
      videoRef.current.play().catch(() => {
        // Handle autoplay block by browser
        console.log("Autoplay blocked, user interaction required");
      });
    }
  }, [url]);

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden", position: "relative" }}>
      <div
        style={{
          padding: "12px 16px",
          background: "rgba(0,0,0,0.4)",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          zIndex: 10,
          backdropFilter: "blur(4px)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 14 }}>📺</span>
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
            {title || "Synced Output Preview"}
          </span>
        </div>
        <div className="badge badge-completed" style={{ fontSize: 10 }}>
          LIVE SYNC
        </div>
      </div>

      <video
        ref={videoRef}
        controls
        playsInline
        onEnded={onEnded}
        style={{
          width: "100%",
          display: "block",
          aspectRatio: "16/9",
          background: "#000",
        }}
      >
        <source src={url} type="video/mp4" />
        Your browser does not support the video tag.
      </video>

      {!url && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--bg-secondary)",
            color: "var(--text-muted)",
            gap: 12,
          }}
        >
          <div style={{ fontSize: 32 }}>💤</div>
          <p style={{ fontSize: 14 }}>Waiting for first chunk to be processed...</p>
        </div>
      )}
    </div>
  );
}
