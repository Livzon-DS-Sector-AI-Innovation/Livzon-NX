import type { NextConfig } from 'next';

const singleHostBuild = process.env.DAZAH_SINGLE_HOST_BUILD === '1';
const isDev = process.env.NODE_ENV === 'development';

const extraDevOrigins =
  process.env.NEXT_ALLOWED_DEV_ORIGINS?.split(',')
    .map((origin) => origin.trim())
    .filter(Boolean) ?? [];

const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ''}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://*.feishucdn.com https://*.feishu.cn https://*.larksuitecdn.com https://*.larksuite.com",
  "font-src 'self' data:",
  `connect-src 'self'${isDev ? ' ws: wss:' : ''}`,
  "frame-src 'self' blob:",
  "worker-src 'self' blob:",
  "manifest-src 'self'",
].join('; ');

const securityHeaders = [
  { key: 'Content-Security-Policy', value: contentSecurityPolicy },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  {
    key: 'Permissions-Policy',
    value: 'camera=(self), microphone=(self), geolocation=(self), payment=()',
  },
  {
    key: 'Strict-Transport-Security',
    value: 'max-age=31536000; includeSubDomains',
  },
  { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
  { key: 'X-DNS-Prefetch-Control', value: 'off' },
];

const nextConfig: NextConfig = {
  output: 'standalone',
  poweredByHeader: false,
  reactCompiler: false,
  // 开发错误仍输出到终端和浏览器控制台，仅隐藏页面左下角的 Next.js 悬浮入口。
  devIndicators: false,
  allowedDevOrigins: [
    '172.28.215.130',
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
    ...extraDevOrigins,
  ],

  // 生产构建不输出浏览器 source map，避免源码与内部路径随 .map 泄露。
  productionBrowserSourceMaps: false,
  typescript: singleHostBuild ? { tsconfigPath: 'tsconfig.build.json' } : undefined,
  webpack: singleHostBuild
    ? (config) => {
        config.cache = false;
        config.parallelism = 1;
        return config;
      }
    : undefined,

  // 记录 fetch 请求详情，方便排查后端接口问题；只记录路径，避免查询参数入日志。
  logging: {
    fetches: {
      fullUrl: false,
    },
  },

  async headers() {
    return [
      {
        source: '/(.*)',
        headers: securityHeaders,
      },
    ];
  },

  experimental: {
    cpus: singleHostBuild ? 1 : undefined,
    serverSourceMaps: singleHostBuild ? false : undefined,
    webpackBuildWorker: singleHostBuild ? true : undefined,
    // Keep Webpack development compilations within Docker Desktop's memory budget.
    webpackMemoryOptimizations: true,
    preloadEntriesOnStart: false,
    serverActions: {
      bodySizeLimit: '50mb',
    },
    proxyClientMaxBodySize: '50mb',
  },
};

export default nextConfig;
