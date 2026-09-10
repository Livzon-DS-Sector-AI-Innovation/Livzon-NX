import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import ts from 'typescript';
import { buildSingleHost } from './build-single-host.mjs';

test('single-host compiler bounds module concurrency while retaining optimizations', async () => {
  const previous = process.env.DAZAH_SINGLE_HOST_BUILD;
  try {
    process.env.DAZAH_SINGLE_HOST_BUILD = '1';
    const compiled = ts.transpileModule(readFileSync('next.config.ts', 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.ESNext },
    }).outputText;
    const { default: config } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
    const input = { parallelism: 100, cache: true, optimization: { minimize: true } };
    const result = config.webpack(input);
    assert.equal(result.parallelism, 1);
    assert.equal(result.cache, false);
    assert.equal(result.optimization.minimize, true);
    assert.equal(config.typescript.ignoreBuildErrors, undefined);
  } finally {
    if (previous === undefined) delete process.env.DAZAH_SINGLE_HOST_BUILD;
    else process.env.DAZAH_SINGLE_HOST_BUILD = previous;
  }
});

test('bounded build configures the standard CLI and does not swallow failures', async () => {
  const argv = process.argv;
  const nodeOptions = process.env.NODE_OPTIONS;
  const profile = process.env.DAZAH_SINGLE_HOST_BUILD;
  const rayon = process.env.RAYON_NUM_THREADS;
  const uvThreads = process.env.UV_THREADPOOL_SIZE;
  try {
    const pkg = JSON.parse(readFileSync('package.json', 'utf8'));
    assert.ok(pkg.scripts['build:single-host'].startsWith('node --max-old-space-size=1280 '));
    await assert.rejects(buildSingleHost(async () => {
      assert.deepEqual(process.argv.slice(-2), ['build', '--webpack']);
      assert.equal(process.env.DAZAH_SINGLE_HOST_BUILD, '1');
      assert.equal(process.env.NODE_OPTIONS, '--max-old-space-size=1280');
      assert.equal(process.env.RAYON_NUM_THREADS, '1');
      assert.equal(process.env.UV_THREADPOOL_SIZE, '1');
      throw new Error('build failed');
    }), /build failed/);
  } finally {
    process.argv = argv;
    if (nodeOptions === undefined) delete process.env.NODE_OPTIONS;
    else process.env.NODE_OPTIONS = nodeOptions;
    if (profile === undefined) delete process.env.DAZAH_SINGLE_HOST_BUILD;
    else process.env.DAZAH_SINGLE_HOST_BUILD = profile;
    if (rayon === undefined) delete process.env.RAYON_NUM_THREADS;
    else process.env.RAYON_NUM_THREADS = rayon;
    if (uvThreads === undefined) delete process.env.UV_THREADPOOL_SIZE;
    else process.env.UV_THREADPOOL_SIZE = uvThreads;
  }
});

test('production type check includes all runtime source and retains strict checking', () => {
  const root = process.cwd();
  const config = ts.readConfigFile('tsconfig.build.json', ts.sys.readFile);
  assert.equal(config.error, undefined);
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, root);
  assert.deepEqual(parsed.errors, []);
  assert.equal(parsed.options.strict, true);
  assert.equal(parsed.options.noEmit, true);
  const included = new Set(parsed.fileNames.map((file) => path.resolve(file)));
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) visit(file);
      else if (/\.tsx?$/.test(file) && !/\.(test|spec)\.tsx?$/.test(file)) {
        assert.ok(included.has(path.resolve(file)), `unchecked production source: ${file}`);
      }
    }
  };
  visit(path.join(root, 'src'));
  // Full CI type checking must continue to cover the test source too.
  const full = ts.readConfigFile('tsconfig.json', ts.sys.readFile);
  const fullParsed = ts.parseJsonConfigFileContent(full.config, ts.sys, root);
  assert.ok(fullParsed.fileNames.some((file) => /\.test\.tsx?$/.test(file)));
});
