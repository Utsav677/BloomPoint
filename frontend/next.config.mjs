/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config) => {
    // jsPDF has optional peer deps (canvg, html2canvas, dompurify) that aren't needed for our PDF generation
    config.resolve.fallback = {
      ...config.resolve.fallback,
      canvg: false,
      html2canvas: false,
      dompurify: false,
    };
    return config;
  },
};

export default nextConfig;
