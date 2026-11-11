import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const planner = fileURLToPath(new URL('./plan-critical-e2e-shard.mjs', import.meta.url))

function spec(file, title) {
  return { file, title, id: `${file}:${title}`, tests: [{ projectId: 'chromium' }] }
}

test('distributes independent overlay cases while keeping other specs intact', t => {
  const directory = mkdtempSync(join(tmpdir(), 'critical-e2e-shards-'))
  t.after(() => rmSync(directory, { recursive: true, force: true }))
  const inventory = join(directory, 'inventory.json')
  const output = join(directory, 'shard.txt')
  const overlay = 'layout/production-overlays.spec.ts'
  const files = ['identity/one.spec.ts', 'layout/two.spec.ts', 'purchasing/new.spec.ts']
  const cases = Array.from({ length: 8 }, (_, index) => spec(overlay, `viewport ${index}`))
  writeFileSync(inventory, JSON.stringify({
    suites: [
      { file: overlay, specs: cases },
      ...files.map(file => ({ file, suites: [{ title: 'group', specs: [spec(file, 'case')] }] })),
      {
        file: 'layout/helper-registration.spec.ts',
        suites: [{
          title: 'helper suite',
          specs: [spec('layout/helper.ts', 'registered case')],
        }],
      },
    ],
  }))

  const exclusions = []
  for (const shard of ['1', '2', '3', '4']) {
    execFileSync(process.execPath, [planner, inventory, shard, output])
    const selectors = readFileSync(output, 'utf8').trim().split('\n')
    assert.equal(selectors.filter(selector => selector.startsWith(`${overlay} > `)).length, 6)
    exclusions.push(...selectors)
  }

  const selectors = [
    ...files,
    'layout/helper.ts > helper suite > registered case',
    ...cases.map(testCase => `${overlay} > ${testCase.title}`),
  ]
  assert.deepEqual(exclusions.sort(), [...selectors, ...selectors, ...selectors].sort())

  const result = join(directory, 'result.json')
  writeFileSync(result, '{"suites":[]}')
  assert.throws(
    () => execFileSync(process.execPath, [planner, inventory, '1', output, result], { stdio: 'pipe' }),
    /ran a different test set than planned/,
  )
})
