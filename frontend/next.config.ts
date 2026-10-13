import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The Docker image runs Next's minimal standalone server; local
  // `next start` keeps the regular output.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "**.immobiliare.it" },
      { protocol: "https", hostname: "**.idealista.it" },
      { protocol: "https", hostname: "**.casa.it" },
      { protocol: "https", hostname: "pwm.im-cdn.it" },
    ],
  },
};

export default nextConfig;
