import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

test('generated dashboard naming retains independent entry and report permission pages', () => {
  execFileSync(process.execPath, [fileURLToPath(new URL('./generate-page-menu.mjs', import.meta.url)), '--check'])
  const catalog = JSON.parse(fs.readFileSync(new URL('../../dazah-backend/app/platform/identity/page_menu_catalog.json', import.meta.url), 'utf8'))
  const children = catalog.find(item => item.key === 'energy').children
  assert.equal(children.find(item => item.path === '/energy').name, '能源仪表盘')
  assert.equal(children.find(item => item.path === '/energy/entry').key, 'entry')
  assert.equal(children.find(item => item.path === '/energy/reports').key, 'reports')
})
