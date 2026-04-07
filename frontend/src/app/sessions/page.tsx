"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import { api, Session } from "@/lib/api";

const fetcher = () => api.sessions.list();

const STATUS_LABELS: Record<string, string> = {
  recording:  "recording",
  processing: "processing",
  completed:  "completed",
  failed:     "failed",
};

export default function SessionsPage() {
  const { data: sessions, error, isLoading, mutate } = useSWR("sessions", fetcher, {
    refreshInterval: 5000,
  });

  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [camCount, setCamCount] = useState(3);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await api.sessions.create(newName.trim(), camCount);
      setNewName("");
      mutate();
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <Navbar />
      <main className="container" style={{ paddingTop: 40 }}>
        {/* Header */}
        <div className="page-header">
          <h1 className="page-title">Recording Sessions</h1>
          <p className="page-subtitle">
            Create sessions, monitor chunk uploads, and view synced outputs.
          </p>
        </div>

        {/* Create Session */}
        <div className="card fade-in" style={{ marginBottom: 32 }}>
          <h2 className="card-title" style={{ marginBottom: 16 }}>
            ➕ New Session
          </h2>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div style={{ flex: 2, minWidth: 200 }}>
              <label className="label">Session Name</label>
              <input
                className="input"
                placeholder="e.g. Graduation Ceremony 2026"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              />
            </div>
            <div style={{ width: 140 }}>
              <label className="label">Camera Count</label>
              <input
                className="input"
                type="number"
                min={1}
                max={10}
                value={camCount}
                onChange={(e) => setCamCount(Number(e.target.value))}
              />
            </div>
            <div style={{ display: "flex", alignItems: "flex-end" }}>
              <button
                className="btn btn-primary"
                onClick={handleCreate}
                disabled={creating || !newName.trim()}
              >
                {creating ? "Creating..." : "Create Session"}
              </button>
            </div>
          </div>
        </div>

        {/* Sessions List */}
        {isLoading && (
          <div style={{ color: "var(--text-muted)", textAlign: "center", padding: 40 }}>
            Loading sessions...
          </div>
        )}

        {error && (
          <div
            className="card badge-failed"
            style={{ padding: 20, textAlign: "center" }}
          >
            ⚠️ Failed to load sessions. Is the backend running?
          </div>
        )}

        {sessions && sessions.length === 0 && (
          <div
            style={{
              textAlign: "center",
              padding: 60,
              color: "var(--text-muted)",
            }}
          >
            <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
            <p>No sessions yet. Create one above to get started.</p>
          </div>
        )}

        <div className="grid-2">
          {sessions?.map((session: Session) => (
            <div key={session.id} className="card fade-in">
              <div className="card-header">
                <div>
                  <h3
                    style={{
                      fontSize: 16,
                      fontWeight: 600,
                      marginBottom: 4,
                    }}
                  >
                    {session.name}
                  </h3>
                  <span className="mono">{session.id.slice(0, 8)}…</span>
                </div>
                <span
                  className={`badge badge-${session.status}`}
                >
                  <span className={`badge-dot ${session.status === "recording" ? "pulse" : ""}`} />
                  {STATUS_LABELS[session.status]}
                </span>
              </div>

              <div
                style={{
                  display: "flex",
                  gap: 24,
                  marginBottom: 20,
                  color: "var(--text-secondary)",
                  fontSize: 14,
                }}
              >
                <span>📱 {session.camera_count} cameras</span>
                <span>
                  🕒{" "}
                  {new Date(session.created_at).toLocaleDateString("vi-VN", {
                    day: "2-digit",
                    month: "2-digit",
                    year: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>

              <Link
                href={`/sessions/${session.id}`}
                className="btn btn-ghost"
                style={{ width: "100%", justifyContent: "center" }}
              >
                View Details →
              </Link>
            </div>
          ))}
        </div>
      </main>
    </>
  );
}
