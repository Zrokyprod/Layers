import type { NextConfig } from "next";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-XSS-Protection", value: "0" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://checkout.razorpay.com",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self'",
      "connect-src 'self' https://api.zroky.com https://api.razorpay.com https://checkout.razorpay.com",
      "frame-src 'self' https://api.razorpay.com https://checkout.razorpay.com",
      "frame-ancestors 'none'",
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  reactCompiler: true,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
  async redirects() {
    return [
      {
        source: "/account",
        destination: "/settings/profile",
        permanent: true,
      },
      {
        source: "/notifications",
        destination: "/issues",
        permanent: true,
      },
      {
        source: "/calibration",
        destination: "/settings/evaluation",
        permanent: true,
      },
      {
        source: "/judge",
        destination: "/settings/evaluation",
        permanent: true,
      },
      {
        source: "/reliability",
        destination: "/agents",
        permanent: true,
      },
      {
        source: "/outcomes",
        destination: "/cost",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
