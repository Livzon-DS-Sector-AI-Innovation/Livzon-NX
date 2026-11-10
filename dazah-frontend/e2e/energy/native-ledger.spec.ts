import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/__dazah_maintenance_status', route => route.fulfill({ json: { phase: 'normal' } }))
  page.on('dialog', dialog => dialog.accept())
})

test('original entry redirects to the editable report with undo and retained failures', async ({ context, page }) => {
  test.setTimeout(90_000)
  await context.addCookies([{ name: 'auth_token', value: `energy-${randomUUID()}`, url: 'http://127.0.0.1:3200' }])
  await page.goto('/energy/entry?date=2026-07-02&dataset=饮用水码', { waitUntil: 'domcontentloaded' })
  await expect(page).toHaveURL(/energy\/reports\?.*year=2026/)
  await expect(page.getByText('原始数据填写', { exact: true })).toHaveCount(0)
  const cell = page.locator('[data-grid-row="0"][data-grid-column="1"]')
  await expect(cell).toHaveAttribute('aria-readonly', 'false')
  await cell.dblclick()
  const input = page.getByRole('spinbutton', { name: '单元格数值' })
  await expect(input).toBeEnabled()
  await input.fill('123')
  await input.press('Enter')
  await page.getByRole('button', { name: '撤销', exact: true }).click()
  await expect(input).toHaveCount(0)
  expect((await (await page.request.get('/api/v1/energy/e2e-state')).json()).data.task.items[0].value).toBeNull()
  await cell.dblclick(); await expect(input).toBeEnabled(); await input.fill('999'); await input.press('Enter')
  await expect(page.getByText('模拟能源服务暂不可用，输入已保留').first()).toBeVisible({ timeout: 15000 })
  await expect(input).toHaveValue('999')
  await input.fill('110'); await input.press('Enter')
  await expect(page.getByText('数据已保存，关联报表已更新').first()).toBeVisible({ timeout: 15000 })
  expect((await (await page.request.get('/api/v1/energy/e2e-state')).json()).data.task.items[0].value).toBe('110')
})

test('energy reports query all 21 worksheets with web filters and copy in both appearances', async ({ context, page }, testInfo) => {
  test.setTimeout(120_000)
  await context.addCookies([{ name: 'auth_token', value: `energy-${randomUUID()}`, url: 'http://127.0.0.1:3200' }])
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/v1/energy/reporting/workbook?*', route => {
    const params = new URL(route.request().url()).searchParams
    return route.fulfill({ json: { code: 200, data: {
      year: Number(params.get('year')), month: Number(params.get('month')), dataset: params.get('dataset'),
      available_count: 804, expected_count: 806,
      columns: [
        { key: 'water', label: '饮用水', unit: 'm³', value_kind: 'usage', quantity_kind: 'volume' },
        { key: 'power', label: '用电量', unit: 'kWh', value_kind: 'usage', quantity_kind: 'electricity' },
        ...Array.from({ length: 24 }, (_, index) => ({ key: `meter-${index}`, label: `${101 + index}车间水表`, unit: 'm³', value_kind: 'reading', quantity_kind: 'volume' })),
      ],
      rows: [
        { date: '2026-07-01', cells: { ...Object.fromEntries(Array.from({ length: 24 }, (_, index) => [`meter-${index}`, { value: String(7352 + index * 10000), status: 'complete' }])), water: { value: '0', status: 'complete', provenance: { formula: '1 × 日总量', calculation_policy: 'system' } }, power: { value: '12.5000', status: 'complete' } } },
        { date: '2026-07-02', cells: { ...Object.fromEntries(Array.from({ length: 24 }, (_, index) => [`meter-${index}`, { value: String(7780 + index * 10000), status: 'complete' }])), water: { value: null, status: 'missing_reading' }, power: { value: null, status: 'not_applicable' } } },
        ...Array.from({ length: 29 }, (_, day) => ({ date: `2026-07-${String(day + 3).padStart(2, '0')}`, cells: { water: { value: String(7965 + day * 165), status: 'complete' }, power: { value: String(100005 + day * 211), status: 'complete' }, ...Object.fromEntries(Array.from({ length: 24 }, (_, index) => [`meter-${index}`, { value: String(7965 + day * 165 + index * 10000), status: 'complete' }])) } })),
      ],
    } } })
  })
  await page.goto('/energy/reports?year=2026&month=7&dataset=日总量', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: '能源报表', exact: true })).toBeVisible()
  const sheets = page.getByRole('navigation', { name: '报表工作表' })
  await expect(sheets.getByRole('link')).toHaveCount(21, { timeout: 60_000 })
  const names = await sheets.getByRole('link').allTextContents()
  for (const name of names) {
    const response = name === '日总量' ? Promise.resolve() : page.waitForResponse(result => {
      const url = new URL(result.url())
      return url.pathname.endsWith('/reporting/workbook') && url.searchParams.get('dataset') === name && result.ok()
    })
    await sheets.getByRole('link', { name, exact: true }).click()
    await response
    await expect(page.locator('[role="group"]').filter({ has: page.locator('[data-grid-row="0"]') })).toHaveAttribute('aria-label', `${name}数据表`)
    await expect(sheets.locator('[aria-current="page"]')).toHaveText(name)
    const bounds = await sheets.boundingBox()
    const active = await sheets.locator('[aria-current="page"]').boundingBox()
    expect(active?.x).toBeGreaterThanOrEqual(bounds?.x ?? 0)
    expect((active?.x ?? 0) + (active?.width ?? 0)).toBeLessThanOrEqual((bounds?.x ?? 0) + (bounds?.width ?? 0) + 1)
    expect(new URL(page.url()).searchParams.get('month')).toBe('7')
  }
  for (const appearance of ['light', 'dark']) {
    await page.getByTitle(appearance === 'light' ? '浅色' : '深色', { exact: true }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
    await page.getByRole('button', { name: '重置视图', exact: true }).click()
    const first = page.locator('[data-grid-row="0"][data-grid-column="1"]')
    await first.hover()
    await expect(page.getByRole('tooltip')).toHaveCount(0)
    await first.click()
    await page.keyboard.press('Shift+ArrowRight')
    await page.keyboard.press('Shift+ArrowDown')
    await expect(page.locator('td[aria-selected="true"]')).toHaveCount(4)
    const copied = await page.locator('[data-grid-row="1"][data-grid-column="2"]').evaluate(element => {
      const clipboardData = new DataTransfer()
      element.dispatchEvent(new ClipboardEvent('copy', { bubbles: true, cancelable: true, clipboardData }))
      return clipboardData.getData('text/plain')
    })
    expect(copied).toBe('0\t12.5\n待补数\t不适用')
    await page.getByPlaceholder('开始日期', { exact: true }).click()
    await page.locator('.ant-picker-dropdown').filter({ visible: true }).getByTitle('2026-07-03', { exact: true }).first().click()
    await page.locator('.ant-picker-dropdown').filter({ visible: true }).getByTitle('2026-07-05', { exact: true }).first().click()
    await expect(page.locator('tr[data-row-key]')).toHaveCount(3)
    await expect(page.locator('tr[data-row-key]').first()).toHaveAttribute('data-row-key', '2026-07-03')
    await page.getByRole('button', { name: '重置视图', exact: true }).click()
    const comfortableRow = await page.locator('tr[data-row-key]').first().boundingBox()
    await page.getByText('紧凑', { exact: true }).click()
    await expect(page.locator('.ant-table-small')).toBeVisible()
    expect((await page.locator('tr[data-row-key]').first().boundingBox())?.height).toBeLessThan(comfortableRow?.height ?? 0)
    await expect(page.getByRole('button', { name: '显示字段 26/26' })).toBeVisible()
    await expect(page.getByRole('button', { name: '下一组字段', exact: true })).toHaveCount(0)
    const scrollArea = page.locator('.ant-table-content')
    expect(await scrollArea.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true)
    await scrollArea.evaluate(element => { element.scrollLeft = element.scrollWidth })
    expect(await scrollArea.evaluate(element => element.scrollLeft)).toBeGreaterThan(0)
    await expect(page.getByRole('columnheader').filter({ hasText: '124车间水表' })).toBeVisible()
    await scrollArea.evaluate(element => { element.scrollLeft = 0 })
    await page.getByRole('textbox', { name: '搜索报表字段', exact: true }).fill('124车间')
    await expect(page.getByRole('columnheader')).toHaveCount(2)
    await page.getByRole('checkbox', { name: '仅看当前字段异常', exact: true }).check()
    await expect(page.getByText('当前筛选没有匹配的日期', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '重置视图', exact: true }).click()
    await page.getByRole('columnheader').filter({ hasText: '饮用水' }).click()
    await expect(page.locator('tr[data-row-key]').first()).toHaveAttribute('data-row-key', '2026-07-01')
    await page.getByRole('button', { name: '重置视图', exact: true }).click()
    await page.screenshot({ path: testInfo.outputPath(`reports-${appearance}.png`), fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    await expect(page.locator('[data-grid-row="0"][data-grid-column="0"]')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`reports-${appearance}-mobile.png`) })
    await page.setViewportSize({ width: 1280, height: 900 })
  }
  expect(errors).toEqual([])
})
