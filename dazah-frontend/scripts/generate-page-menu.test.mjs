import assert from 'node:assert/strict'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { spawnSync } from 'node:child_process'

// The reviewed backend catalog keeps permission pages, while the frontend menu
// may group them behind a navigation-only console; regeneration is therefore a
// reviewed step, not a blanket equality check.
test('reviewed page menu catalog retains independent entry and report permission pages', () => {
  const catalog = JSON.parse(fs.readFileSync(new URL('../../dazah-backend/app/platform/identity/page_menu_catalog.json', import.meta.url), 'utf8'))
  const children = catalog.find(item => item.key === 'energy').children
  assert.equal(children.find(item => item.path === '/energy').name, '能源仪表盘')
  assert.equal(children.find(item => item.path === '/energy/entry').key, 'entry')
  assert.equal(children.find(item => item.path === '/energy/reports').key, 'reports')
  assert.equal(children.find(item => item.path === '/energy/reports').name, '能源报表')
  assert.ok(!children.some(item => item.key === 'history'), '退役的历史来源页不得回到目录中')
})

test('scoped energy generation preserves reviewed catalog and rejects unknown modules', () => {
  const script = fileURLToPath(new URL('./generate-page-menu.mjs', import.meta.url))
  const catalog = fileURLToPath(new URL('../../dazah-backend/app/platform/identity/page_menu_catalog.json', import.meta.url))
  const before = fs.readFileSync(catalog, 'utf8')
  const checked = spawnSync(process.execPath, [script, '--module', 'energy', '--check'], { encoding: 'utf8' })
  assert.equal(checked.status, 0, checked.stderr)
  const invalid = spawnSync(process.execPath, [script, '--module', 'unknown'], { encoding: 'utf8' })
  assert.notEqual(invalid.status, 0)
  assert.equal(fs.readFileSync(catalog, 'utf8'), before)
})
