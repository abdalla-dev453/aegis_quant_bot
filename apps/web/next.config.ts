import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@aegis-quant/contracts", "@aegis-quant/ui"],
};

export default nextConfig;
