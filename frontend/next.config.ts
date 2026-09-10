import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  env: {
    MOCK_MODE: process.env.MOCK_MODE,
  },
};

export default nextConfig;
