import type { NextConfig } from 'next';

const extraDevOrigins =
  process.env.NEXT_ALLOWED_DEV_ORIGINS?.split(',')
    .map((origin) => origin.trim())
    .filter(Boolean) ?? [];

const nextConfig: NextConfig = {
  output: 'standalone',
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

  // 内部部署阶段：启用 sourcemap 方便定位错误
  productionBrowserSourceMaps: true,

  // 记录 fetch 请求详情，方便排查后端接口问题
  logging: {
    fetches: {
      fullUrl: true,
    },
  },

  experimental: {
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
