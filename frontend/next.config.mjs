/** @type {import('next').NextConfig} */

// Inside Docker, the backend is always at http://backend:8000 (service name).
// This is a SERVER-SIDE rewrite, so we use the internal Docker hostname.
// For local dev outside Docker, fall back to localhost:8000.
const BACKEND_INTERNAL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    return [
      // REST API
      { source: "/api/:path*",        destination: `${BACKEND_INTERNAL}/api/:path*` },
      { source: "/upload",            destination: `${BACKEND_INTERNAL}/upload` },
      { source: "/esp32-trigger",     destination: `${BACKEND_INTERNAL}/esp32-trigger` },
      // WebSocket — Note: Next.js rewrites do NOT upgrade WS connections.
      // WS goes directly to Nginx via window.location.host in useWebSocket.ts
      { source: "/ws/:path*",         destination: `${BACKEND_INTERNAL}/ws/:path*` },
      // Health
      { source: "/health",            destination: `${BACKEND_INTERNAL}/health` },
      // Static synced videos
      { source: "/static/:path*",     destination: `${BACKEND_INTERNAL}/static/:path*` },
    ];
  },
};

export default nextConfig;
