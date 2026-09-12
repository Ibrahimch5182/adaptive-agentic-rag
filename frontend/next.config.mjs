/** @type {import('next').NextConfig} */
const nextConfig = {
  // Next's built-in gzip buffers the response to compress it, which defeats real-time
  // delivery of the SSE query-progress stream (the browser's fetch always sends
  // Accept-Encoding, so compression silently re-enables buffering per-request otherwise).
  compress: false,
  // Default dev rewrite proxy timeout is 30s (next/dist/server/lib/router-utils/proxy-request.js).
  // Adaptive queries chain retrieval + multiple sequential Groq calls (assessor/generation/
  // verification) and can exceed that on a cold model/process start, which the proxy reports
  // as a client-side "socket hang up"/ECONNRESET even though the backend keeps running.
  experimental: {
    proxyTimeout: 360_000,
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      // Backend liveness lives at root /health (not under /api) — exposed to the
      // frontend under /api/health so the sidebar can show a real status indicator
      // without a cross-origin request. Pure proxy wiring, no backend change.
      {
        source: "/api/health",
        destination: `${backendUrl}/health`,
      },
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
