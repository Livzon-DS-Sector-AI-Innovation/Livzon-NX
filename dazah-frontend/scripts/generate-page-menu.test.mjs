import assert from 'node:assert/strict'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

// The reviewed backend catalog keeps permission pages, while the frontend menu
// may group them behind a navigation-only console; regeneration is therefore a
// reviewed step, not a blanket equality check.
test('reviewed page menu catalog retains independent entry and report permission pages', () => {
  const catalog = JSON.parse(fs.readFileSync(new URL('../../dazah-backend/app/platform/identity/page_menu_catalog.json', import.meta.url), 'utf8'))
  const children = catalog.find(item => item.key === 'energy').children
  assert.equal(children.find(item => item.path === '/energy').name, '能源仪表盘')
  assert.equal(children.find(item => item.path === '/energy/entry').key, 'entry')
  assert.equal(children.find(item => item.path === '/energy/reports').key, 'reports')
  assert.ok(!children.some(item => item.key === 'history'), '退役的历史来源页不得回到目录中')
})
