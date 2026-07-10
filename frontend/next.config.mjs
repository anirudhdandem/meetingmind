/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emits .next/standalone with a self-contained server.js and only the node_modules it
  // actually imports, so the production image doesn't ship the whole dependency tree.
  output: "standalone",
};

export default nextConfig;
