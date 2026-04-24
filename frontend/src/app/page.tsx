import Navbar from "@/components/Navbar";
import Link from "next/link";

export default function HomePage() {
  return (
    <>
      <Navbar />
      <main className="container" style={{ paddingTop: 60, paddingBottom: 80 }}>
        {/* Hero Section */}
        <div
          className="card fade-in-up"
          style={{
            marginBottom: 40,
            padding: "40px 32px",
            border: "1px solid var(--border-highlight)",
            background: "linear-gradient(145deg, rgba(30, 41, 59, 0.4), rgba(15, 23, 42, 0.6))",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 32 }}>
            <div
              style={{
                width: 80,
                height: 80,
                background: "linear-gradient(135deg, var(--accent-blue), var(--accent-fuchsia))",
                borderRadius: "20px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 36,
                flexShrink: 0,
                boxShadow: "0 12px 32px rgba(139, 92, 246, 0.4)",
              }}
            >
              🎥
            </div>
            <div>
              <h1 className="page-title" style={{ marginBottom: 12, fontSize: 36 }}>
                VideoSync Pipeline
              </h1>
              <p style={{ color: "var(--text-secondary)", fontSize: 16, maxWidth: 600, lineHeight: 1.6 }}>
                High-performance multi-camera video ingestion, precision audio-based synchronization, and
                real-time stitching command center.
              </p>
            </div>
          </div>
        </div>

        {/* Stats Row */}
        <div className="grid-4 fade-in-up stagger-1" style={{ marginBottom: 40 }}>
          {[
            { label: "Active Sessions", value: "—", icon: "📡", color: "var(--accent-blue)" },
            { label: "Chunks Processed", value: "—", icon: "🧩", color: "var(--accent-cyan)" },
            { label: "Cameras Online", value: "—", icon: "📱", color: "var(--accent-green)" },
            { label: "Sync Accuracy", value: "< 50ms", icon: "⏱️", color: "var(--accent-fuchsia)" },
          ].map((stat) => (
            <div className="card interactive card-hover" key={stat.label}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>{stat.icon}</div>
              <div style={{ fontSize: 32, fontWeight: 800, color: stat.color, letterSpacing: "-0.02em" }}>
                {stat.value}
              </div>
              <div style={{ fontSize: 13, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginTop: 4 }}>
                {stat.label}
              </div>
            </div>
          ))}
        </div>

        {/* Quick Access */}
        <div className="grid-3 fade-in-up stagger-2" style={{ marginBottom: 40 }}>
          {[
            {
              title: "📁 Sessions",
              desc: "View and manage all recording sessions. Monitor chunk upload progress in real-time.",
              href: "/sessions",
              cta: "View Sessions",
            },
            {
              title: "🎬 Simulate",
              desc: "Upload pre-recorded videos to simulate multi-camera live sync.",
              href: "/simulate",
              cta: "Upload Videos",
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
            <div className="card interactive" key={item.title} style={{ display: 'flex', flexDirection: 'column' }}>
              <div className="card-header">
                <h2 className="card-title">{item.title}</h2>
                {item.badge && (
                  <span className="badge badge-processing" style={{ fontSize: 10 }}>
                    {item.badge}
                  </span>
                )}
              </div>
              <p
                style={{
                  color: "var(--text-secondary)",
                  fontSize: 14,
                  marginBottom: 24,
                  lineHeight: 1.7,
                  flexGrow: 1,
                }}
              >
                {item.desc}
              </p>
              <Link
                href={item.href}
                target={item.external ? "_blank" : undefined}
                className="btn btn-ghost"
                style={{ width: "100%" }}
              >
                {item.cta} {item.external ? "↗" : "→"}
              </Link>
            </div>
          ))}
        </div>

        {/* Pipeline Diagram */}
        <div className="card fade-in-up stagger-3">
          <div className="card-header">
            <h2 className="card-title"><span className="text-gradient">🔄 Processing Pipeline</span></h2>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              flexWrap: "wrap",
            }}
          >
            {[
              { step: "📱 Upload", desc: "POST /upload-chunk" },
              { step: "→" },
              { step: "📂 Ingest", desc: "Store /raw/chunk_N/" },
              { step: "→" },
              { step: "🎵 Offset", desc: "Cross-correlation" },
              { step: "→" },
              { step: "✂️ Align", desc: "FFmpeg trim" },
              { step: "→" },
              { step: "🖼️ Stitch", desc: "FFmpeg layout" },
              { step: "→" },
              { step: "✅ Output", desc: "/synced/chunk_N" },
            ].map((item, i) =>
              item.step === "→" ? (
                <span
                  key={i}
                  style={{ color: "var(--text-muted)", fontSize: 24 }}
                >
                  →
                </span>
              ) : (
                <div
                  key={i}
                  style={{
                    background: "rgba(0,0,0,0.2)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    padding: "16px",
                    flex: 1,
                    minWidth: 140,
                    boxShadow: "inset 0 2px 4px rgba(0,0,0,0.1)",
                  }}
                >
                  <div
                    style={{
                      fontSize: 15,
                      fontWeight: 700,
                      marginBottom: 6,
                      color: "var(--text-primary)"
                    }}
                  >
                    {item.step}
                  </div>
                  <div
                    className="mono"
                    style={{
                      fontSize: 11,
                      color: "var(--text-secondary)",
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
