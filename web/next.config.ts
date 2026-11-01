import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Sortie autonome pour l'image Docker (voir Dockerfile).
  output: "standalone",
};

export default nextConfig;
