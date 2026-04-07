import Navbar from "@/components/Navbar";
import Link from "next/link";

export default function HomePage() {
  return (
    <>
      <Navbar />
      <main className="container" style={{ paddingTop: 40 }}>
        {/* Hero */}
        <div
          className="card fade-in"
          style={{
            marginBottom: 32,
            background:
              "linear-gradient(135deg, rgba(59,130,246,0.1), rgba(139,92,246,0.1))",
            borderColor: "rgba(59,130,246,0.3)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
            <div
              style={{
                width: 64,
                height: 64,
                background:
                  "linear-gradient(135deg, var(--accent-blue), var(--accent-purple))",
                borderRadius: 16,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 32,
                flexShrink: 0,
              }}
            >
              🎥
            </div>
            <div>
              <h1
                style={{
                  fontSize: 24,
                  fontWeight: 700,
                  marginBottom: 6,
                  background:
                    "linear-gradient(135deg, #f1f5f9, #94a3b8)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                }}
              >
                VideoSync Pipeline
              </h1>
              <p style={{ color: "var(--text-secondary)", fontSize: 15 }}>
                Multi-camera video ingestion, audio-based synchronization, and
                real-time stitching dashboard.
              </p>
            </div>
          </div>
        </div>

        {/* Stats Row */}
        <div className="grid-4" style={{ marginBottom: 32 }}>
          {[
            { label: "Active Sessions", value: "—", icon: "📡", color: "var(--accent-blue)" },
            { label: "Chunks Processed", value: "—", icon: "🧩", color: "var(--accent-cyan)" },
            { label: "Cameras Online", value: "—", icon: "📱", color: "var(--accent-green)" },
            { label: "Sync Accuracy", value: "< 50ms", icon: "⏱️", color: "var(--accent-amber)" },
          ].map((stat) => (
            <div className="stat-card" key={stat.label}>
              <div style={{ fontSize: 24, marginBottom: 4 }}>{stat.icon}</div>
              <div className="stat-value" style={{ color: stat.color }}>
                {stat.value}
              </div>
              <div className="stat-label">{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Quick Access */}
        <div className="grid-3" style={{ marginBottom: 32 }}>
          {[
            {
              title: "📁 Sessions",
              desc: "View and manage all recording sessions. Monitor chunk upload progress in real-time.",
              href: "/sessions",
              cta: "View Sessions",
            },
            {
              title: "🔴 Live Stream",
              desc: "Phase 2: Live multi-camera synchronized stream view using RTMP/HLS.",
              href: "/live",
              cta: "Go Live",
              badge: "Phase 2",
            },
            {
              title: "📖 API Docs",
              desc: "Explore the FastAPI interactive documentation for all backend endpoints.",
              href: "http://localhost:8000/docs",
              cta: "Open Docs",
              external: true,
            },
          ].map((item) => (
            <div className="card" key={item.title}>
              <div className="card-header">
                <h2 className="card-title">{item.title}</h2>
                {item.badge && (
                  <span
                    className="badge badge-processing"
                    style={{ fontSize: 11 }}
                  >
                    {item.badge}
                  </span>
                )}
              </div>
              <p
                style={{
                  color: "var(--text-secondary)",
                  fontSize: 14,
                  marginBottom: 20,
                  lineHeight: 1.7,
                }}
              >
                {item.desc}
              </p>
              <Link
                href={item.href}
                target={item.external ? "_blank" : undefined}
                className="btn btn-ghost"
                style={{ width: "100%", justifyContent: "center" }}
              >
                {item.cta} {item.external ? "↗" : "→"}
              </Link>
            </div>
          ))}
        </div>

        {/* Pipeline Diagram */}
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">🔄 Processing Pipeline</h2>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            {[
              { step: "📱 Upload", desc: "Phones push chunks via POST /upload-chunk" },
              { step: "→" },
              { step: "📂 Ingest", desc: "Validate & store in storage/raw/{session_id}/chunk_N/" },
              { step: "→" },
              { step: "🎵 Offset", desc: "Audio cross-correlation (chunk_0 only)" },
              { step: "→" },
              { step: "✂️ Align", desc: "FFmpeg trim by offset.json" },
              { step: "→" },
              { step: "🖼️ Stitch", desc: "FFmpeg hstack/vstack/grid" },
              { step: "→" },
              { step: "✅ Output", desc: "storage/synced/synced_chunk_N.mp4" },
            ].map((item, i) =>
              item.step === "→" ? (
                <span
                  key={i}
                  style={{ color: "var(--text-muted)", fontSize: 20 }}
                >
                  →
                </span>
              ) : (
                <div
                  key={i}
                  style={{
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    padding: "12px 16px",
                    flex: 1,
                    minWidth: 120,
                  }}
                >
                  <div
                    style={{
                      fontSize: 14,
                      fontWeight: 600,
                      marginBottom: 4,
                    }}
                  >
                    {item.step}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--text-muted)",
                      lineHeight: 1.5,
                    }}
                  >
                    {item.desc}
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      </main>
    </>
  );
}
