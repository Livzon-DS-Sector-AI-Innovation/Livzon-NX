import { fileURLToPath } from 'node:url';
import path from 'node:path';

export async function buildSingleHost(run = () => import('next/dist/bin/next')) {
  process.env.NODE_OPTIONS = '--max-old-space-size=1280';
  process.env.DAZAH_SINGLE_HOST_BUILD = '1';
  process.env.RAYON_NUM_THREADS = '1';
  process.env.UV_THREADPOOL_SIZE = '1';
  process.argv = [process.execPath, 'node_modules/next/dist/bin/next', 'build', '--webpack'];
  // Load the standard CLI in this process; do not retain another Node supervisor.
  // The CLI owns its exit status, and import errors remain unhandled failures.
  await run();
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await buildSingleHost();
}
