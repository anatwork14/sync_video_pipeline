"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { useParams, useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import { api, Session, Offset } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import SyncedPlayer from "@/components/SyncedPlayer";
import { useToast } from "@/components/Toast";

const fetcher = (id: string) => api.sessions.get(id);
const offsetFetcher = (id: string) => api.sessions.offsets(id);

export default function SessionDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();
  const { addToast } = useToast();

  const { data: session, error, isLoading, mutate } = useSWR(id ? `session-${id}` : null, () => fetcher(id));
  const { data: offsets } = useSWR(id ? `offsets-${id}` : null, () => offsetFetcher(id));
  const { events, connected } = useWebSocket(id);

  const [currentVideoUrl, setCurrentVideoUrl] = useState<string | null>(null);
  const [processedChunks, setProcessedChunks] = useState<number[]>([]);
  const [deleting, setDeleting] = useState(false);

  // Monitor events for toast notifications and player updates
  useEffect(() => {
    const lastEvent = events[events.length - 1];
    if (!lastEvent) return;

    if (lastEvent.type === "chunk_done" && lastEvent.chunk_index !== undefined) {
      if (!processedChunks.includes(lastEvent.chunk_index)) {
        addToast({ type: "success", title: "Chunk Synced", message: `Chunk #${lastEvent.chunk_index} is ready for playback.` });
        
        setProcessedChunks((prev) => {
          const next = [...prev, lastEvent.chunk_index!].sort((a, b) => a - b);
          // Auto-play the newest chunk if nothing is playing
          if (!currentVideoUrl && lastEvent.url) {
            setCurrentVideoUrl(lastEvent.url);
          }
          return next;
        });
      }
    } else if (lastEvent.type === "processing_started") {
      addToast({ type: "info", title: "Processing Started", message: `Syncing Chunk #${lastEvent.chunk_index}...` });
    } else if (lastEvent.type === "error") {
      addToast({ type: "error", title: "Sync Error", message: lastEvent.message || "Pipeline encountered an error." });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  const handleDelete = async () => {
    if (!session) return;
    if (!confirm(`Permanently delete "${session.name}"? All raw and synced files will be lost.`)) return;
    
    setDeleting(true);
    try {
      await api.sessions.delete(session.id);
      addToast({ type: "success", title: "Deleted", message: "Session removed successfully." });
      router.push("/sessions");
    } catch (err: any) {
      addToast({ type: "error", title: "Failed to delete", message: err.message });
      setDeleting(false);
    }
  };

  if (isLoading) {
    return (
      <>
        <Navbar />
        <main className="container" style={{ paddingTop: 60 }}>
          <div className="skeleton" style={{ height: 100, marginBottom: 32 }} />
          <div className="grid-2" style={{ gridTemplateColumns: "1fr 340px", gap: 32 }}>
            <div className="skeleton" style={{ height: 500 }} />
            <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
              <div className="skeleton" style={{ height: 200 }} />
              <div className="skeleton" style={{ height: 300 }} />
            </div>
          </div>
        </main>
      </>
    );
  }

  if (error || !session) {
    return (
      <>
        <Navbar />
        <main className="container" style={{ paddingTop: 100, textAlign: "center" }}>
          <div className="card badge-failed fade-in-up" style={{ padding: "40px", maxWidth: 400, margin: "0 auto", background: "rgba(239, 68, 68, 0.1)" }}>
            <div style={{ fontSize: 40, marginBottom: 16 }}>⚠️</div>
            <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>Session Not Found</h2>
            <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>The session may have been deleted or the server is unreachable.</p>
            <button className="btn btn-ghost" onClick={() => router.push("/sessions")}>
              ← Back to Sessions
            </button>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <Navbar />
      <main className="container" style={{ paddingTop: 40, paddingBottom: 80 }}>
        {/* Header Section */}
        <div className="fade-in-up" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", borderBottom: "1px solid var(--border)", paddingBottom: 24, marginBottom: 32 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
              <button 
                className="btn btn-ghost" 
                style={{ padding: "6px", width: 32, height: 32, borderRadius: "50%" }}
                onClick={() => router.push("/sessions")}
                title="Back to Sessions"
              >
                ←
              </button>
              <h1 className="page-title" style={{ fontSize: 28, margin: 0 }}>{session.name}</h1>
              <span className={`badge badge-${session.status}`} style={{ margin: 0, padding: "2px 8px", fontSize: 11 }}>
                {session.status}
              </span>
            </div>
            <p className="mono" style={{ fontSize: 13, color: "var(--text-muted)", margin: "8px 0 0 44px" }}>
              ID: {session.id} • {session.camera_count} CAMERAS CONFIGURED
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div 
              className={`badge ${connected ? "badge-completed" : "badge-failed"}`} 
              style={{ fontSize: 11, padding: "6px 12px", background: connected ? "rgba(16, 185, 129, 0.1)" : "rgba(239, 68, 68, 0.1)" }}
            >
              <span className={`badge-dot ${connected ? "pulse" : ""}`} />
              {connected ? "LIVE FEED ACTIVE" : "DISCONNECTED (RETRYING)"}
            </div>
            <button 
              className="btn btn-danger" 
              onClick={handleDelete}
              disabled={deleting}
              style={{ padding: "8px 16px", fontSize: 13 }}
            >
              {deleting ? "Deleting..." : "🗑️ Delete Session"}
            </button>
          </div>
        </div>

        <div className="grid-2 fade-in-up stagger-1" style={{ gridTemplateColumns: "1fr 340px", gap: 32 }}>
          {/* Left Column: Player & History */}
          <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
            <SyncedPlayer
              url={currentVideoUrl ? `http://localhost:8000${currentVideoUrl}` : ""}
              title={`Live Monitor — Chunk #${processedChunks[processedChunks.length - 1] ?? "..."}`}
            />

            <div className="card">
              <div className="card-header">
                <h3 className="card-title"><span style={{ fontSize: 20, marginRight: 8 }}>📦</span> Synced Chunks</h3>
                <span className="badge badge-uploaded" style={{ background: "transparent", border: "none" }}>
                  {processedChunks.length} Total
                </span>
              </div>
              
              {processedChunks.length === 0 ? (
                <div style={{ color: "var(--text-muted)", fontSize: 14, textAlign: "center", padding: "60px 20px", border: "1px dashed var(--border)", borderRadius: "var(--radius-sm)" }}>
                  <div style={{ fontSize: 32, marginBottom: 12 }}>⏳</div>
                  No synced chunks yet.<br/>Ensure capture nodes are actively uploading.
                </div>
              ) : (
                <div className="grid-4">
                  {processedChunks.map((idx) => {
                    const isActive = currentVideoUrl?.includes(`synced_chunk_${idx}.mp4`);
                    return (
                      <button
                        key={idx}
                        className={`card interactive ${isActive ? "active" : ""}`}
                        onClick={() => setCurrentVideoUrl(`/static/synced/${session.id}/synced_chunk_${idx}.mp4`)}
                        style={{
                          padding: 16,
                          textAlign: "center",
                          background: isActive ? "rgba(59,130,246,0.15)" : "rgba(0,0,0,0.2)",
                          borderColor: isActive ? "var(--accent-blue)" : "var(--border)",
                          boxShadow: isActive ? "var(--shadow-glow)" : "none",
                        }}
                      >
                        <div style={{ fontSize: 24, marginBottom: 8, opacity: isActive ? 1 : 0.7 }}>🎞️</div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: isActive ? "var(--text-primary)" : "var(--text-secondary)" }}>
                          CHUNK #{idx}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Right Column: Metadata & Offsets */}
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            {/* Offset Data */}
            <div className="card">
              <h3 className="card-title" style={{ marginBottom: 8 }}>⏱️ Camera Alignments</h3>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 20, lineHeight: 1.5 }}>
                Computed via audio cross-correlation against the reference node.
              </p>
              
              {offsets && offsets.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {offsets.map((off: Offset) => (
                    <div key={off.cam_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px", background: "rgba(0,0,0,0.2)", borderRadius: 6, border: "1px solid var(--border)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 16 }}>📸</span>
                        <span className="mono" style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{off.cam_id}</span>
                      </div>
                      <span className="mono" style={{ fontSize: 13, padding: "4px 8px", borderRadius: 4, background: off.offset_seconds >= 0 ? "rgba(245, 158, 11, 0.1)" : "rgba(6, 182, 212, 0.1)", color: off.offset_seconds >= 0 ? "var(--accent-amber)" : "var(--accent-cyan)" }}>
                        {off.offset_seconds > 0 ? "+" : ""}{off.offset_seconds.toFixed(3)}s
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: 13, color: "var(--text-muted)", textAlign: "center", padding: "30px 20px", background: "rgba(0,0,0,0.2)", borderRadius: 6 }}>
                  <div className="skeleton" style={{ width: 24, height: 24, borderRadius: "50%", margin: "0 auto 12px", animation: "pulse 1.5s infinite" }} />
                  Computing...<br/>Waiting for Chunk #0 from all cameras.
                </div>
              )}
            </div>

            {/* Event Feed */}
            <div className="card" style={{ flexGrow: 1, display: "flex", flexDirection: "column" }}>
              <div className="card-header" style={{ marginBottom: 12, borderBottom: "1px solid var(--border)", paddingBottom: 16 }}>
                <h3 className="card-title">🚀 Real-Time Logs</h3>
              </div>
              <div style={{ flexGrow: 1, maxHeight: 380, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8, paddingRight: 8 }}>
                {events.slice().reverse().map((ev, i) => {
                  let accent = "var(--border)";
                  if (ev.type === "chunk_done") accent = "var(--accent-green)";
                  if (ev.type === "error") accent = "var(--accent-red)";
                  if (ev.type === "processing_started") accent = "var(--accent-amber)";
                  if (ev.type === "chunk_uploaded") accent = "var(--accent-blue)";

                  return (
                    <div key={i} className="fade-in-up" style={{ padding: "10px 12px", background: "rgba(0,0,0,0.2)", borderRadius: "var(--radius-sm)", borderLeft: `3px solid ${accent}`, fontSize: 12 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                        <span className="mono" style={{ fontWeight: 700, color: "var(--text-primary)" }}>{ev.type.toUpperCase()}</span>
                        <span style={{ color: "var(--text-muted)", fontSize: 10 }}>Just now</span>
                      </div>
                      {ev.message && <div style={{ color: "var(--text-secondary)", marginTop: 4, lineHeight: 1.4 }}>{ev.message}</div>}
                      <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
                        {ev.cam_id && <span className="badge" style={{ fontSize: 9, padding: "2px 6px", background: "rgba(255,255,255,0.05)", border: "1px solid var(--border)" }}>CAM: {ev.cam_id}</span>}
                        {ev.chunk_index !== undefined && <span className="badge" style={{ fontSize: 9, padding: "2px 6px", background: "rgba(255,255,255,0.05)", border: "1px solid var(--border)" }}>CHUNK: {ev.chunk_index}</span>}
                      </div>
                    </div>
                  );
                })}
                {events.length === 0 && (
                  <div style={{ fontSize: 13, color: "var(--text-muted)", textAlign: "center", margin: "auto", padding: 20 }}>
                    Listening for telemetry on <span className="mono" style={{ color: "var(--accent-cyan)" }}>ws://</span>...
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
