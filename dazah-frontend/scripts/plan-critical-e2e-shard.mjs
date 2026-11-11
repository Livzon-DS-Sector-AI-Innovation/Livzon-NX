import { readFileSync, writeFileSync } from 'node:fs'
import { isDeepStrictEqual } from 'node:util'

const shardCount = 4
const productionOverlays = 'layout/production-overlays.spec.ts'

// Seconds per case, rounded from the local Chromium run against the standalone build.
const secondsPerCase = {
  [productionOverlays]: 28,
  'layout/critical-module-overlays.spec.ts': 10,
}
const defaultSecondsPerCase = 4

function collectCases(suite, ancestors = []) {
  return [
    ...(suite.specs ?? []).map(spec => ({
      file: spec.file,
      selector: [spec.file, ...ancestors, spec.title].join(' > '),
      ids: spec.tests.map(run => `${run.projectId}:${spec.id}`),
    })),
    ...(suite.suites ?? []).flatMap(child => collectCases(child, [...ancestors, child.title])),
  ]
}

const [inventoryPath, shardArgument, outputPath, resultPath] = process.argv.slice(2)
const shardNumber = Number(shardArgument)
if (!inventoryPath || !outputPath || !Number.isInteger(shardNumber) || shardNumber < 1 || shardNumber > shardCount) {
  throw new Error('Usage: node scripts/plan-critical-e2e-shard.mjs <inventory JSON> <shard 1–4> <exclusion list> [result JSON]')
}

const { suites } = JSON.parse(readFileSync(inventoryPath, 'utf8'))
const groups = suites.flatMap(suite => {
  const cases = collectCases(suite)
  const seconds = secondsPerCase[suite.file] ?? defaultSecondsPerCase
  if (suite.file === productionOverlays) {
    // Each viewport and appearance case creates its own browser context and mock data.
    return cases.map(testCase => ({
      name: testCase.selector,
      selectors: [testCase.selector],
      ids: testCase.ids,
      seconds: seconds * testCase.ids.length,
    }))
  }
  const ids = cases.flatMap(testCase => testCase.ids)
  return [{
    name: suite.file,
    // Tests registered in a helper match its source location in Playwright's test list.
    selectors: cases.every(testCase => testCase.file === suite.file)
      ? [suite.file]
      : cases.map(testCase => testCase.selector),
    ids,
    seconds: seconds * ids.length,
  }]
})

const shards = Array.from({ length: shardCount }, () => ({ selectors: [], ids: [], seconds: 0 }))
const selectors = groups.flatMap(group => group.selectors)
if (new Set(selectors).size !== selectors.length) {
  throw new Error('Stable E2E inventory contains ambiguous test-list selectors')
}
groups.sort((a, b) => b.seconds - a.seconds || a.name.localeCompare(b.name))
for (const group of groups) {
  const shard = shards.reduce((lightest, current) => current.seconds < lightest.seconds ? current : lightest)
  shard.selectors.push(...group.selectors)
  shard.ids.push(...group.ids)
  shard.seconds += group.seconds
}

const shard = shards[shardNumber - 1]
if (shard.ids.length === 0) {
  throw new Error(`No tests assigned to stable E2E shard ${shardNumber}/${shardCount}`)
}
if (resultPath) {
  const result = JSON.parse(readFileSync(resultPath, 'utf8'))
  const actualIds = result.suites.flatMap(suite => collectCases(suite).flatMap(testCase => testCase.ids))
  if (!isDeepStrictEqual(actualIds.sort(), shard.ids.sort())) {
    throw new Error(`Stable E2E shard ${shardNumber}/${shardCount} ran a different test set than planned (expected ${shard.ids.length}, reported ${actualIds.length})`)
  }
} else {
  // An inclusion list filters spec files before loading them. Exclude the other
  // shards after discovery so specs that register cases through helpers still load.
  const excluded = shards.filter(other => other !== shard).flatMap(other => other.selectors)
  writeFileSync(outputPath, `${excluded.join('\n')}\n`)
  process.stdout.write(`Stable E2E shard ${shardNumber}/${shardCount} plans ${shard.ids.length} cases in about ${shard.seconds}s.\n`)
}
