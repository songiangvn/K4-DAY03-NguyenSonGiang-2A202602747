/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: { ignoreBuildErrors: true },
  images: { unoptimized: true },
  // Chuyển tiếp mọi lời gọi /api/* sang API server Python của Agent
  async rewrites() {
    const target = process.env.AGENT_API_URL || 'http://localhost:8080'
    return [{ source: '/api/:path*', destination: `${target}/api/:path*` }]
  },
}

export default nextConfig
