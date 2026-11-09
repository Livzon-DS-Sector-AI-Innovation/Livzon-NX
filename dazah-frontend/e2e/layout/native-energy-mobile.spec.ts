import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/__dazah_maintenance_status', route => route.fulfill({ json: { phase: 'normal' } }))
  page.on('dialog', dialog => dialog.accept())
})
test('native energy settings and mobile forms render in both appearance modes', async ({ context, page }) => {
  await context.addCookies([{ name: 'auth_token', value: `energy-${randomUUID()}`, url: 'http://127.0.0.1:3200' }])
  for (const appearance of ['light', 'dark']) {
    const optionsReady = page.waitForResponse(response => response.url().includes('/api/v1/energy/ledger-options') && response.status() === 200)
    await page.goto('/energy/settings', { waitUntil: 'domcontentloaded' })
    await optionsReady
    await page.getByTitle(appearance === 'light' ? '浅色' : '深色', { exact: true }).click()
    await expect(page.getByRole('tab', { name: '飞书机器人', exact: true })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'Excel 导入', exact: true })).toBeVisible()
    await expect(page.getByRole('tab', { name: '待确认复核', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '保存机器人配置', exact: true })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
    await page.getByRole('tab', { name: '飞书机器人', exact: true }).click()
    await expect(page.getByRole('button', { name: '保存机器人配置', exact: true })).toBeVisible()
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/energy/reports?year=2026&month=7&dataset=饮用水码', { waitUntil: 'domcontentloaded' })
  const cell = page.locator('[data-grid-row="0"][data-grid-column="1"]')
  await expect(cell).toHaveAttribute('aria-readonly', 'false')
  await cell.dblclick()
  const mobileInput = page.getByRole('spinbutton', { name: '单元格数值' })
  await expect(mobileInput).toBeVisible()
  await expect(mobileInput).toBeEnabled()
  await mobileInput.fill('112.5')
  await mobileInput.press('Enter')
  await page.getByRole('button', { name: '撤销', exact: true }).click()
  await expect(mobileInput).toHaveCount(0)
})
