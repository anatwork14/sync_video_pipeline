"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";

export default function SimulatePage() {
  const router = useRouter();
  const [sessionName, setSessionName] = useState("");
  const [syncStrategy, setSyncStrategy] = useState("multividsynch");
  const [cam1File, setCam1File] = useState<File | null>(null);
  const [cam2File, setCam2File] = useState<File | null>(null);
  const [cam3File, setCam3File] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [status, setStatus] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sessionName || !cam1File) {
      setStatus("Session Name and at least Camera 1 are required.");
      return;
    }

    setIsUploading(true);
    setStatus("Creating session...");

    try {
      // Create session
      let cameraCount = 1;
      if (cam2File) cameraCount++;
      if (cam3File) cameraCount++;

      const res = await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: sessionName,
          camera_count: cameraCount,
          sync_strategy: syncStrategy,
        }),
      });

      if (!res.ok) throw new Error("Failed to create session");
      const session = await res.json();

      setStatus("Uploading videos for simulation (this may take a while)...");

      const formData = new FormData();
      formData.append("session_id", session.id);
      
      formData.append("cam1_id", "cam1");
      formData.append("cam1_file", cam1File);

      if (cam2File) {
        formData.append("cam2_id", "cam2");
        formData.append("cam2_file", cam2File);
      }
      if (cam3File) {
        formData.append("cam3_id", "cam3");
        formData.append("cam3_file", cam3File);
      }

      const uploadRes = await fetch("/api/simulate/upload", {
        method: "POST",
        body: formData,
      });

      if (!uploadRes.ok) {
        const errorText = await uploadRes.text();
        throw new Error(`Upload failed: ${errorText}`);
      }

      setStatus("Simulation started! Redirecting...");
      setTimeout(() => {
        router.push(`/sessions/${session.id}`);
      }, 1000);

    } catch (err: any) {
      console.error(err);
      setStatus(`Error: ${err.message}`);
      setIsUploading(false);
    }
  };

  return (
    <>
      <Navbar />
      <main className="container" style={{ paddingTop: 40, paddingBottom: 60 }}>
        <h2 className="page-title">🎬 Simulate Upload</h2>
        <p style={{ color: "var(--text-secondary)", marginBottom: 30 }}>
          Upload full pre-recorded videos (e.g., from multiple POVs of the same landscape) to simulate a live multi-camera sync session.
        </p>

        <form onSubmit={handleSubmit} style={{ maxWidth: 600, display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="card">
            <h3>Session Configuration</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
              <label>Session Name</label>
              <input
                type="text"
                placeholder="e.g. Landscape Demo"
                value={sessionName}
                onChange={(e) => setSessionName(e.target.value)}
                required
                style={{ padding: 10, borderRadius: 6, border: "1px solid #444", background: "#2a2a2a", color: "white" }}
              />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 16 }}>
              <label>Sync Strategy</label>
              <select
                value={syncStrategy}
                onChange={(e) => setSyncStrategy(e.target.value)}
                style={{ padding: 10, borderRadius: 6, border: "1px solid #444", background: "#2a2a2a", color: "white" }}
              >
                <option value="multividsynch">MultiVidSynch (Visual Features)</option>
                <option value="audio">Audio Cross-Correlation</option>
              </select>
            </div>
          </div>

          <div className="card">
            <h3>Camera Inputs</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 12 }}>
              <div>
                <label>Camera 1 (Required)</label>
                <input
                  type="file"
                  accept="video/mp4,video/webm,video/quicktime"
                  onChange={(e) => setCam1File(e.target.files?.[0] || null)}
                  required
                  style={{ display: "block", marginTop: 8 }}
                />
              </div>
              <div>
                <label>Camera 2 (Optional)</label>
                <input
                  type="file"
                  accept="video/mp4,video/webm,video/quicktime"
                  onChange={(e) => setCam2File(e.target.files?.[0] || null)}
                  style={{ display: "block", marginTop: 8 }}
                />
              </div>
              <div>
                <label>Camera 3 (Optional)</label>
                <input
                  type="file"
                  accept="video/mp4,video/webm,video/quicktime"
                  onChange={(e) => setCam3File(e.target.files?.[0] || null)}
                  style={{ display: "block", marginTop: 8 }}
                />
              </div>
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={isUploading}
            style={{ padding: "14px", fontSize: 16, marginTop: 10 }}
          >
            {isUploading ? "Processing..." : "Start Simulation"}
          </button>

          {status && (
            <div style={{ 
              marginTop: 10, 
              padding: 12, 
              borderRadius: 6, 
              backgroundColor: status.includes("Error") ? "#4a1c1c" : "#1c3a27",
              color: status.includes("Error") ? "#ff6b6b" : "#4ade80" 
            }}>
              {status}
            </div>
          )}
        </form>
      </main>
    </>
  );
}
