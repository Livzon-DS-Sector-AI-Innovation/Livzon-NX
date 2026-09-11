import type { NextConfig } from 'next';

const singleHostBuild = process.env.DAZAH_SINGLE_HOST_BUILD === '1';

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

  // 单机发布优先控制构建峰值；常规构建仍保留现有 source map 行为。
  productionBrowserSourceMaps: !singleHostBuild,
  typescript: singleHostBuild ? { tsconfigPath: 'tsconfig.build.json' } : undefined,
  webpack: singleHostBuild
    ? (config) => {
        config.cache = false;
        config.parallelism = 1;
        return config;
      }
    : undefined,

  // 记录 fetch 请求详情，方便排查后端接口问题
  logging: {
    fetches: {
      fullUrl: true,
    },
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
