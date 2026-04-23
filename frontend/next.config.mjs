/** @type {import('next').NextConfig} */
const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    return [
      // REST API
      { source: "/api/:path*",        destination: `${BACKEND}/api/:path*` },
      { source: "/upload",            destination: `${BACKEND}/upload` },
      { source: "/esp32-trigger",     destination: `${BACKEND}/esp32-trigger` },
      // WebSocket endpoints (proxied in Next.js dev via http-proxy)
      { source: "/ws/:path*",         destination: `${BACKEND}/ws/:path*` },
      // Health
      { source: "/health",            destination: `${BACKEND}/health` },
      // Static synced videos
      { source: "/static/:path*",     destination: `${BACKEND}/static/:path*` },
    ];
  },
};

export default nextConfig;
