import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const voltAgentUrl = process.env.VOLTAGENT_URL ?? "http://localhost:3141";
    return [
      {
        source: "/agents/:path*",
        destination: `${voltAgentUrl}/agents/:path*`,
      },
    ];
  },
};

export default nextConfig;
