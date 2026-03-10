/** @type {import('next').NextConfig} */
const nextConfig = {
  // Wymuszenie importowania globalnego css z odpowiedniego pliku
  // Kiedy backend będzie gotowy, odkomentuj poniższy blok:
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