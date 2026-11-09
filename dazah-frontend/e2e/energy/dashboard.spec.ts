import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

test('workbook distinguishes missing, not applicable and zero in both appearances', async ({ page, context, baseURL }) => {
  await context.addCookies([{ name: 'auth_token', value: `energy-${randomUUID()}`, url: baseURL! }])
  await page.route('**/__dazah_maintenance_status', route => route.fulfill({ json: { phase: 'normal' } }))
  await page.route('**/api/v1/energy/reporting/workbook?*', route => route.fulfill({ json: { data: {
    year: 2028, month: 1, dataset: '日总量', available_count: 1, expected_count: 2,
    columns: [{ key: '5', label: '外供蒸汽占比', unit: '比例', quantity_kind: 'ratio', value_kind: 'usage' }],
    rows: [
      { date: '2028-01-01', cells: { '5': { value: null, status: 'missing_dependency' } } },
      { date: '2028-01-02', cells: { '5': { value: null, status: 'not_applicable' } } },
      { date: '2028-01-03', cells: { '5': { value: '0', status: 'complete', provenance: { calculation_policy: 'same-day-formulas-v1', formula: '分子 / 分母', reference: { reported_value: '999' } } } } },
    ],
  } } }))
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/energy/reports?year=2028&month=1&dataset=日总量')
  for (const appearance of ['light', 'dark']) {
    await page.getByTitle(appearance === 'light' ? '浅色' : '深色', { exact: true }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
    await expect(page.getByRole('row').filter({ hasText: '2028-01-01' }).locator('td').nth(1)).toHaveText('待补数')
    await expect(page.getByRole('row').filter({ hasText: '2028-01-02' }).locator('td').nth(1)).toHaveText('不适用')
    await expect(page.getByRole('row').filter({ hasText: '2028-01-03' }).locator('td').nth(1)).toHaveText('0')
    await page.getByRole('row').filter({ hasText: '2028-01-03' }).locator('u').hover()
    await expect(page.getByRole('tooltip')).toContainText('系统公式：分子 / 分母')
    await expect(page.getByRole('tooltip')).toContainText('参考表手填值：999（仅留痕，不参与计算）')
    await page.mouse.move(0, 0)
    await page.waitForTimeout(1200)
    await page.screenshot({ path: test.info().outputPath(`workbook-${appearance}.png`), fullPage: true, animations: 'disabled' })
  }
  expect(errors).toEqual([])
})

test('dashboard keeps two focused charts and supports metric, month, appearance and mobile viewing', async ({ page, context, baseURL }) => {
  const errors: string[] = []
  const requested: URL[] = []
  page.on('pageerror', error => errors.push(error.message))
  await context.addCookies([{ name: 'auth_token', value: `energy-${randomUUID()}`, url: baseURL! }])
  await page.route('**/__dazah_maintenance_status', route => route.fulfill({ json: { phase: 'normal' } }))
  await page.route('**/api/v1/energy/reporting/workbook?*', route => {
    const url = new URL(route.request().url())
    requested.push(url)
    const year = Number(url.searchParams.get('year'))
    const month = Number(url.searchParams.get('month'))
    const days = new Date(year, month, 0).getDate()
    const dataset = url.searchParams.get('dataset')!
    return route.fulfill({ json: { data: {
      year, month, dataset, available_count: days, expected_count: days,
      columns: ['4', '6', '7', '8', '9', '10'].map(key => ({ key, label: key === '6' ? '电日用量' : '原表字段', unit: '待确认', quantity_kind: 'volume', value_kind: dataset.endsWith('码') ? 'reading' : 'usage' })),
      rows: Array.from({ length: days }, (_, index) => ({ date: `${year}-${String(month).padStart(2, '0')}-${String(index + 1).padStart(2, '0')}`, cells: Object.fromEntries(['4', '6', '7', '8', '9', '10'].map(key => [key, { value: String((index + 1) * 100 + (2026 - year) * 10), status: 'complete', provenance: {} }])) })),
    } } })
  })
  await page.setViewportSize({ width: 1280, height: 1000 })
  await page.goto('/energy?year=2026&month=7')
  await expect(page.getByRole('combobox', { name: '年份', exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: '月份', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '7 月能源概览' })).toBeVisible()
  await expect(page.locator('button[aria-pressed]')).toHaveCount(6)
  await expect(page.locator('.echarts-for-react')).toHaveCount(2)
  await expect(page.getByRole('button', { name: /查\s*询/, exact: true })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '能源仪表盘', exact: true })).toHaveCount(1)
  const metricRows = await page.locator('button[aria-pressed]').evaluateAll(nodes => nodes.map(node => Math.round(node.getBoundingClientRect().top)))
  expect(new Set(metricRows).size).toBe(1)
  const trendCard = await page.locator('.ant-card').filter({ has: page.getByText('电量每日趋势', { exact: true }) }).boundingBox()
  if (!trendCard) throw new Error('每日趋势卡片不存在')
  expect(trendCard.y + trendCard.height).toBeLessThanOrEqual(await page.evaluate(() => window.innerHeight))
  expect(requested).toHaveLength(4)
  expect(requested.every(url => !url.searchParams.has('baseline'))).toBe(true)
  await page.getByRole('button', { name: /饮用水/ }).click()
  await expect(page.getByText('饮用水每日趋势', { exact: true })).toBeVisible()
  await page.getByText('日均', { exact: true }).first().click()
  await page.getByText('查看月度数值', { exact: true }).click()
  await expect(page.getByRole('columnheader', { name: '有效天数' })).toBeVisible()
  await page.getByText('查看月度数值', { exact: true }).click()
  await page.getByRole('combobox', { name: '月份', exact: true }).click()
  await expect(page.getByText('7—10 月连续数据', { exact: true })).toHaveCount(0)
  await page.locator('.ant-select-item-option[title="9月"]').click()
  await expect(page.getByRole('heading', { name: '9 月能源概览' })).toBeVisible()
  await expect(page.getByText('饮用水每日趋势', { exact: true })).toBeVisible()
  await expect(page).toHaveURL(/year=2026&month=9/)
  for (const appearance of ['light', 'dark']) {
    await page.getByTitle(appearance === 'light' ? '浅色' : '深色', { exact: true }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
    // Let the appearance reveal and ECharts canvas animation finish for visual QA.
    await page.waitForTimeout(1200)
    for (const width of [1280, 390]) {
      await page.setViewportSize({ width, height: 1000 })
      await expect(page.locator('.echarts-for-react')).toHaveCount(2)
      await expect.poll(() => page.locator('.echarts-for-react').evaluateAll(nodes => nodes.every(node => {
        const bounds = node.getBoundingClientRect()
        const canvas = node.querySelector('canvas')?.getBoundingClientRect()
        return canvas !== undefined && Math.abs(canvas.width - bounds.width) < 2
      }))).toBe(true)

      const button = page.locator('button[aria-pressed]').first()
      const bounds = await button.boundingBox()
      expect(bounds!.width).toBeGreaterThan(100)
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      await page.screenshot({ path: test.info().outputPath(`dashboard-${appearance}-${width}.png`), fullPage: true, animations: 'disabled' })
    }
    await page.setViewportSize({ width: 1280, height: 1000 })
  }
  await page.getByText('查看分类用量、车间与原始表码', { exact: true }).click()
  await expect(page.getByRole('combobox', { name: '明细数据表' })).toBeVisible()
  await expect(page.locator('.echarts-for-react')).toHaveCount(3)
  await page.getByRole('combobox', { name: '明细数据表' }).click()
  await page.getByRole('combobox', { name: '明细数据表' }).fill('饮用水码')
  await page.locator('.ant-select-item-option').filter({ hasText: /^饮用水码$/ }).click()
  await expect(page.getByText('原始累计表码，不做期间求和', { exact: false })).toBeVisible()
  await page.getByRole('combobox', { name: '年份', exact: true }).fill('2025')
  await page.locator('.ant-select-item-option[title="2025年"]').click()
  await expect(page).toHaveURL(/year=2025&month=9/)
  await expect(page.getByRole('heading', { name: '9 月能源概览' })).toBeVisible()
  await expect(page.getByText('饮用水每日趋势', { exact: true })).toBeVisible()
  await expect(page.locator('.echarts-for-react')).toHaveCount(3)
  await expect.poll(() => requested.some(url => url.searchParams.get('year') === '2025')).toBe(true)
  await expect(page.locator('button[aria-pressed="true"]')).toContainText('46,800')
  expect(errors).toEqual([])
})
