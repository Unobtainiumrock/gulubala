import type { NextConfig } from "next";

const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/calltree/:path*", destination: `${apiTarget}/calltree/:path*` },
      { source: "/health", destination: `${apiTarget}/health` },
    ];
  },
};

export default nextConfig;
