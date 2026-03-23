import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for Puppeteer/Chromium in API routes — keep these out of the bundle
  serverExternalPackages: ["puppeteer-core", "@sparticuz/chromium"],

  async rewrites() {
    return [
      {
        source: "/pipeline/:path*",
        destination: `${process.env.PIPELINE_URL ?? "http://localhost:8000"}/:path*`,
      },
    ];
  },
};

export default nextConfig;
