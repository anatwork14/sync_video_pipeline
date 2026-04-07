const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Session {
  id: string;
  name: string;
  camera_count: number;
  status: "recording" | "processing" | "completed" | "failed";
  created_at: string;
  updated_at: string;
}

export interface Offset {
  cam_id: string;
  offset_seconds: number;
  computed_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Sessions ──────────────────────────────────────────────────────────────────

export const api = {
  sessions: {
    list: (skip = 0, limit = 20) =>
      apiFetch<Session[]>(`/api/sessions?skip=${skip}&limit=${limit}`),

    get: (id: string) => apiFetch<Session>(`/api/sessions/${id}`),

    create: (name: string, cameraCount: number) =>
      apiFetch<Session>("/api/sessions", {
        method: "POST",
        body: JSON.stringify({ name, camera_count: cameraCount }),
      }),

    delete: (id: string) =>
      apiFetch<void>(`/api/sessions/${id}`, { method: "DELETE" }),

    offsets: (id: string) => apiFetch<Offset[]>(`/api/sessions/${id}/offsets`),
  },

  health: () => apiFetch<{ status: string }>("/health"),
};
