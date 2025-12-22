/** @type {import('next').NextConfig} */
// Prefer internal API host for proxying; fallback to localhost so dev host works.
const apiTarget = process.env.API_INTERNAL_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://api:8000";

const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiTarget}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
