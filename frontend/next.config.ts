import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
