import { tmpdir } from 'node:os'
import path from 'node:path'
import { readFileSync, writeFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'

const fixture = path.join(tmpdir(), 'dazah-energy-db-e2e')

test('original workbook imports through browser, calculates and displays all 21 datasets', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'energy-postgres', 'Requires the explicit dedicated database configuration')
  const serverErrors: string[] = []
  // The deployment maintenance probe belongs to the ingress, absent in this
  // isolated dev server. Energy and identity requests all use the real backend.
  await page.route('**/__dazah_maintenance_status', route => route.fulfill({ status: 204 }))
  page.on('dialog', dialog => dialog.accept())
  page.on('response', response => {
    if (response.url().includes('/api/v1/energy/') && response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`)
  })
  page.on('pageerror', error => console.error(error.message))
  const options = page.waitForResponse(response => response.url().includes('/api/v1/energy/ledger-options') && response.ok(), { timeout: 120_000 })
  await page.goto('/energy/settings', { waitUntil: 'domcontentloaded' })
  await options
  await expect(page.getByRole('cell', { name: '西循环水补水', exact: true }).first()).toBeVisible()
  await page.getByRole('tab', { name: '历史导入', exact: true }).click()
  await expect(page.getByRole('tab', { name: '历史导入', exact: true })).toHaveAttribute('aria-selected', 'true')
  await page.getByLabel('选择能源 Excel').setInputFiles(path.join(fixture, 'download.xlsx'))
  await page.getByLabel('导入年份').fill('2026')
  await page.getByLabel('有效开始日期').fill('2026-06-27')
  await page.getByLabel('有效结束日期').fill('2026-07-29')
  await page.getByRole('button', { name: '预览文件', exact: true }).click()
  await expect(page.getByText('文件未保留公式', { exact: false }).first()).toBeVisible()
  await expect(page.getByText('人工覆盖值候选', { exact: false })).toHaveCount(0)
  await page.getByLabel('历史导入原因').fill('独立测试库核验原始输入、自动计算和缺失值')
  await page.getByRole('button', { name: '确认导入已映射数据', exact: true }).click()
  await page.getByRole('dialog', { name: '确认导入历史原始数据' }).getByRole('button', { name: '确 定' }).click()
  await expect(page.getByText('历史原始数据已导入；重复数据不会重复入账', { exact: true })).toBeVisible({ timeout: 120_000 })
  await expect(page.getByText(/状态：已导入/)).toBeVisible()

  const headers = { 'X-Dazah-Page-Key': 'energy:reports' }
  const response = await page.request.get('/api/v1/energy/reporting/datasets', { headers })
  expect(response.ok()).toBeTruthy()
  const datasets: { name: string }[] = (await response.json()).data
  const expected: { readings: Record<string, Record<string, string>>; electric_totals: Record<string, string> } = JSON.parse(readFileSync(path.join(fixture, 'expected.json'), 'utf8'))
  function delta(sheet: string, date: string, column: number) {
    const next = new Date(`${date}T00:00:00Z`)
    next.setUTCDate(next.getUTCDate() + 1)
    const first = expected.readings[sheet][`${date}:${column}`]
    const second = expected.readings[sheet][`${next.toISOString().slice(0, 10)}:${column}`]
    return first === undefined || second === undefined || Number(second) < Number(first) ? null : Number(second) - Number(first)
  }
  let checkedReadings = 0
  let checkedZeros = 0
  expect(datasets).toHaveLength(21)
  for (const { name } of datasets) {
    const loaded = page.waitForResponse(res => res.url().includes('/api/v1/energy/reporting/workbook?') && new URL(res.url()).searchParams.get('dataset') === name && res.ok(), { timeout: 120_000 })
    if (name === datasets[0].name) {
      await page.goto(`/energy/reports?year=2026&month=7&dataset=${encodeURIComponent(name)}`, { waitUntil: 'domcontentloaded' })
    } else {
      await page.getByRole('combobox', { name: '数据表', exact: true }).click()
      await page.locator('.ant-select-dropdown').filter({ visible: true }).getByText(name, { exact: true }).click()
      await page.getByRole('button', { name: /查\s*询/, exact: true }).click()
    }
    const data: { rows: { date: string; cells: Record<string, { value: string | null; status: string }> }[] } = (await (await loaded).json()).data
    for (const row of data.rows) {
      for (const [column, cell] of Object.entries(row.cells)) {
        const raw = expected.readings[name]?.[`${row.date}:${column}`]
        if (raw !== undefined) {
          expect(Number(cell.value), `${name} ${row.date} column ${column}`).toBe(Number(raw))
          expect(cell.status).toBe('complete')
          checkedReadings++
          if (Number(raw) === 0) checkedZeros++
        } else if (expected.readings[name] && (name !== '电量' || !['2', '41', '42', '43'].includes(column))) {
          expect(cell.value, `${name} ${row.date} column ${column} missing`).toBeNull()
        }
      }
      if (name === '电量' && expected.electric_totals[row.date] !== undefined) {
        expect(Number(row.cells['2'].value)).toBe(Number(expected.electric_totals[row.date]))
        expect(row.cells['2'].status).toBe('complete')
        // Blank manual source columns must keep dependent sums missing.
        expect(row.cells['41'].value).toBeNull()
        expect(row.cells['42'].value).toBeNull()
        expect(row.cells['43'].value).toBeNull()
      }
      const counter = name === '饮用水量' ? { source: '饮用水码', column: 2, output: '4' }
        : name === '冰水量' ? { source: '冰水码', column: 4, output: '18' }
          : name === '201-2车间' ? { source: '冰水码', column: 4, output: '6' } : null
      if (counter) {
        const amount = delta(counter.source, row.date, counter.column)
        if (amount === null) expect(row.cells[counter.output].value).toBeNull()
        else {
          expect(row.cells[counter.output].value).not.toBeNull()
          expect(Number(row.cells[counter.output].value)).toBeCloseTo(amount, 3)
        }
      }
      if (name === '101车间') {
        const sameDay = expected.readings['电量'][`${row.date}:14`]
        if (sameDay === undefined) expect(row.cells['3'].value).toBeNull()
        else expect(Number(row.cells['3'].value)).toBe(Number(sameDay))
      }
      if (name === '201-2车间') {
        expect(row.cells['3'].value).toBeNull()
        expect(row.cells['3'].status).toBe('unconfigured')
      }
    }
    await expect(page.getByText(`${name} · 2026年7月 · 已取得`, { exact: false })).toBeVisible()
    await expect(page.getByRole('row').filter({ has: page.getByRole('cell', { name: '2026-07-31', exact: true }) })).toBeVisible()
  }
  expect(checkedReadings).toBeGreaterThan(3000)
  expect(checkedZeros).toBeGreaterThan(0)
  for (const theme of ['light', 'dark']) {
    await page.evaluate(mode => localStorage.setItem('dazah-appearance', mode), theme)
    const themedReport = page.waitForResponse(response => response.url().includes('/api/v1/energy/reporting/workbook?') && response.ok(), { timeout: 120_000 })
    await page.goto('/energy/reports?year=2026&month=7&dataset=饮用水码')
    await themedReport
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
    const missing = page.getByRole('row').filter({ has: page.getByRole('cell', { name: '2026-07-30', exact: true }) })
    await expect(missing.getByText('缺少读数', { exact: true }).first()).toBeVisible()
    await page.screenshot({ path: path.join('..', 'outputs', 'energy-audit-20261016', `database-${theme}.png`), fullPage: true })
  }
  const exported = await page.request.get('/api/v1/energy/reporting/workbook/export?year=2026&month=7', { headers, timeout: 120_000 })
  expect(exported.status()).toBe(200)
  expect(exported.headers()['content-type']).toContain('spreadsheetml')
  writeFileSync(path.join(fixture, 'export.xlsx'), await exported.body())
  writeFileSync(path.join('..', 'outputs', 'energy-audit-20261016', 'browser-evidence.json'), JSON.stringify({
    datasets: datasets.map(item => item.name), checkedReadings, checkedZeros,
    themes: ['light', 'dark'], serverErrors,
  }, null, 2))
  expect(serverErrors).toEqual([])
})
