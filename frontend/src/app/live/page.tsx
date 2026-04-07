import Navbar from "@/components/Navbar";

export default function LivePage() {
  return (
    <>
      <Navbar />
      <main className="container" style={{ paddingTop: 40 }}>
        <div className="page-header">
          <h1 className="page-title">Live Stream Viewer</h1>
          <p className="page-subtitle">
            Phase 2: Real-time synchronized multi-camera stream via RTMP → HLS.
          </p>
        </div>

        <div
          className="card"
          style={{
            textAlign: "center",
            padding: "80px 40px",
            borderStyle: "dashed",
            borderColor: "rgba(139,92,246,0.3)",
            background: "rgba(139,92,246,0.04)",
          }}
        >
          <div style={{ fontSize: 64, marginBottom: 20 }}>🎬</div>
          <h2
            style={{
              fontSize: 22,
              fontWeight: 700,
              marginBottom: 12,
              background: "linear-gradient(135deg, var(--accent-blue), var(--accent-purple))",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Live Streaming — Coming in Phase 2
          </h2>
          <p
            style={{
              color: "var(--text-secondary)",
              maxWidth: 480,
              margin: "0 auto 32px",
              lineHeight: 1.7,
            }}
          >
            Phase 2 will add real-time RTMP ingest from mobile phones via{" "}
            <strong style={{ color: "var(--text-primary)" }}>MediaMTX</strong>,
            synchronized HLS output, and a multi-camera grid player using{" "}
            <strong style={{ color: "var(--text-primary)" }}>hls.js</strong>.
          </p>

          <div
            style={{
              display: "flex",
              gap: 12,
              justifyContent: "center",
              flexWrap: "wrap",
            }}
          >
            {["📡 RTMP Ingest", "🔄 Real-time Sync", "📺 HLS Delivery", "🎛️ Multi-cam Grid"].map(
              (f) => (
                <span
                  key={f}
                  style={{
                    background: "rgba(139,92,246,0.1)",
                    border: "1px solid rgba(139,92,246,0.2)",
                    color: "var(--accent-purple)",
                    padding: "6px 14px",
                    borderRadius: "999px",
                    fontSize: 13,
                    fontWeight: 500,
                  }}
                >
                  {f}
                </span>
              )
            )}
          </div>
        </div>
      </main>
    </>
  );
}
