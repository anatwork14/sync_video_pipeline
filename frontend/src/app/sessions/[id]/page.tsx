"use client";

import { useEffect, useState, useMemo } from "react";
import useSWR from "swr";
import { useParams, useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import { api, Session, Offset } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import SyncedPlayer from "@/components/SyncedPlayer";

const fetcher = (id: string) => api.sessions.get(id);
const offsetFetcher = (id: string) => api.sessions.offsets(id);

export default function SessionDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();

  const { data: session, error, isLoading, mutate } = useSWR(id ? `session-${id}` : null, () => fetcher(id));
  const { data: offsets } = useSWR(id ? `offsets-${id}` : null, () => offsetFetcher(id));
  const { events, connected } = useWebSocket(id);

  const [currentVideoUrl, setCurrentVideoUrl] = useState<string | null>(null);
  const [processedChunks, setProcessedChunks] = useState<number[]>([]);

  // Update processed chunks when a new "chunk_done" event arrives
  useEffect(() => {
    const lastEvent = events[events.length - 1];
    if (lastEvent?.type === "chunk_done" && lastEvent.chunk_index !== undefined) {
      setProcessedChunks((prev) => {
        if (!prev.includes(lastEvent.chunk_index!)) {
          const next = [...prev, lastEvent.chunk_index!].sort((a, b) => a - b);
          // Auto-play the latest chunk if not already playing
          if (!currentVideoUrl && lastEvent.url) {
            setCurrentVideoUrl(lastEvent.url);
          }
          return next;
        }
        return prev;
      });
    }
  }, [events, currentVideoUrl]);

  if (isLoading) {
    return (
      <>
        <Navbar />
        <div className="container" style={{ padding: 100, textAlign: "center", color: "var(--text-muted)" }}>
          Loading session details...
        </div>
      </>
    );
  }

  if (error || !session) {
    return (
      <>
        <Navbar />
        <div className="container" style={{ padding: 100, textAlign: "center" }}>
          <div className="card badge-failed" style={{ padding: 40 }}>
            Session not found or server error.
            <br />
            <button className="btn btn-ghost" style={{ marginTop: 20 }} onClick={() => router.push("/sessions")}>
              Back to Sessions
            </button>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Navbar />
      <main className="container" style={{ paddingTop: 40, paddingBottom: 80 }}>
        {/* Header Section */}
        <div className="grid-2" style={{ marginBottom: 32, alignItems: "flex-end" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
              <span className={`badge badge-dot ${session.status === "recording" ? "pulse" : ""}`} style={{ background: "transparent", color: "initial" }} />
              <h1 className="page-title" style={{ fontSize: 24 }}>{session.name}</h1>
            </div>
            <p className="mono" style={{ fontSize: 13, color: "var(--text-muted)" }}>
              {session.id} • {session.camera_count} CAMERAS ONLINE
            </p>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
            <span className={`badge badge-${session.status}`} style={{ padding: "8px 16px", fontSize: 13 }}>
              {session.status.toUpperCase()}
            </span>
            <div className={`badge ${connected ? "badge-completed" : "badge-failed"}`} style={{ fontSize: 11 }}>
              {connected ? "LIVE WS CONNECTED" : "WS DISCONNECTED"}
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 32 }}>
          {/* Left Column: Player & History */}
          <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
            {/* Player */}
            <SyncedPlayer
              url={currentVideoUrl ? `http://localhost:8000${currentVideoUrl}` : ""}
              title={`Synced Live Stream — Chunk #${processedChunks[processedChunks.length - 1] ?? 0}`}
            />

            {/* Chunk History Grid */}
            <div className="card">
              <h3 className="card-title" style={{ marginBottom: 20 }}>📦 Chunk History</h3>
              {processedChunks.length === 0 ? (
                <div style={{ color: "var(--text-muted)", fontSize: 14, textAlign: "center", padding: 40 }}>
                  No synced chunks yet. Uploading started?
                </div>
              ) : (
                <div className="grid-4">
                  {processedChunks.map((idx) => (
                    <button
                      key={idx}
                      className={`card fade-in ${currentVideoUrl?.includes(`synced_chunk_${idx}.mp4`) ? "active" : ""}`}
                      onClick={() => setCurrentVideoUrl(`/static/synced/${session.id}/synced_chunk_${idx}.mp4`)}
                      style={{
                        padding: 12,
                        textAlign: "center",
                        cursor: "pointer",
                        background: currentVideoUrl?.includes(`synced_chunk_${idx}.mp4`) ? "rgba(59,130,246,0.1)" : "var(--bg-secondary)",
                        borderColor: currentVideoUrl?.includes(`synced_chunk_${idx}.mp4`) ? "var(--accent-blue)" : "var(--border)",
                      }}
                    >
                      <div style={{ fontSize: 20, marginBottom: 8 }}>🧩</div>
                      <div style={{ fontSize: 12, fontWeight: 700 }}>CHUNK #{idx}</div>
                      <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>SYNCED</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right Column: Metadata & Offsets */}
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            {/* Offset Data */}
            <div className="card">
              <h3 className="card-title" style={{ marginBottom: 16 }}>⏱️ Camera Offsets</h3>
              <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 16 }}>
                Computed via audio cross-correlation on Chunk #0.
              </p>
              {offsets && offsets.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {offsets.map((off: Offset) => (
                    <div key={off.cam_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                      <span className="mono" style={{ fontSize: 13, color: "var(--accent-cyan)" }}>{off.cam_id}</span>
                      <span className="mono" style={{ fontSize: 13, color: off.offset_seconds >= 0 ? "var(--accent-amber)" : "var(--accent-cyan)" }}>
                        {off.offset_seconds >= 0 ? "+" : ""}{off.offset_seconds.toFixed(3)}s
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: 13, color: "var(--text-muted)", textAlign: "center", padding: 20 }}>
                  Computing... (Waiting for Chunk 0)
                </div>
              )}
            </div>

            {/* Event log */}
            <div className="card">
              <h3 className="card-title" style={{ marginBottom: 16 }}>🚀 Event Feed</h3>
              <div style={{ height: 300, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8, paddingRight: 4 }}>
                {events.slice().reverse().map((ev, i) => (
                  <div key={i} style={{ fontSize: 11, padding: "8px 12px", background: "var(--bg-secondary)", borderRadius: 6, borderLeft: "2px solid var(--accent-blue)" }}>
                    <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{ev.type.toUpperCase()}</div>
                    {ev.message && <div style={{ color: "var(--text-secondary)", marginTop: 2 }}>{ev.message}</div>}
                    {ev.cam_id && <div style={{ color: "var(--text-muted)", marginTop: 2 }}>CAM: {ev.cam_id} | CHUNK: {ev.chunk_index}</div>}
                    {!ev.cam_id && ev.chunk_index !== undefined && <div style={{ color: "var(--text-muted)", marginTop: 2 }}>CHUNK: {ev.chunk_index}</div>}
                  </div>
                ))}
                {events.length === 0 && (
                  <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", paddingTop: 40 }}>
                    Listening for sync events...
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
