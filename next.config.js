/** @type {import('next').NextConfig} */
const nextConfig = {
  // Phase 2: uncomment when backend is ready
  // async rewrites() {
  //   return [
  //     {
  //       source: '/api/:path*',
  //       destination: `${process.env.BACKEND_URL || 'http://localhost:8000'}/api/:path*`,
  //     },
  //   ];
  // },
};

module.exports = nextConfig;
