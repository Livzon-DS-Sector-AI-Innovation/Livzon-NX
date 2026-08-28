import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { parse } from 'dotenv';
import type { NextConfig } from 'next';

// The workspace root is the only owner of runtime environment files. Next's
// default loader searches relative to the frontend directory, so load only
// the explicitly selected root file here.
const workspaceRoot = path.resolve(__dirname, '..');
const isProduction =
  process.env.NODE_ENV === 'production' ||
  process.env.APP_ENV?.trim().toLowerCase() === 'production';
const selectedEnvFile = isProduction ? '.env' : '.env.local';

const selectedEnvPath = path.join(workspaceRoot, selectedEnvFile);
if (existsSync(selectedEnvPath)) {
  const selectedEnvValues = parse(readFileSync(selectedEnvPath));
  for (const [key, value] of Object.entries(selectedEnvValues)) {
    if (!Object.prototype.hasOwnProperty.call(process.env, key)) {
      process.env[key] = value;
    }
  }
}

const extraDevOrigins =
  process.env.NEXT_ALLOWED_DEV_ORIGINS?.split(',')
    .map((origin) => origin.trim())
    .filter(Boolean) ?? [];

const nextConfig: NextConfig = {
  output: 'standalone',
  reactCompiler: false,
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
