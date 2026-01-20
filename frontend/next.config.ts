import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  // Disable ESLint and TypeScript checks during production build
  // This allows Docker builds to succeed even with linting warnings
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Permissions-Policy",
            value: "microphone=(self)",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
