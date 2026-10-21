import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

const task = 'a1000000-0000-0000-0000-000000000001'
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
    await expect(page.getByRole('button', { name: '新增计量点', exact: true })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
    await page.getByRole('tab', { name: '飞书机器人', exact: true }).click()
    await expect(page.getByRole('button', { name: '保存机器人配置', exact: true })).toBeVisible()
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`/energy/entry?task=${task}&source=feishu`, { waitUntil: 'domcontentloaded' })
  const mobileInput = page.getByRole('spinbutton', { name: '101车间水表本次填写' })
  await expect(mobileInput).toBeVisible()
  const bounds = await mobileInput.boundingBox()
  expect(bounds?.width).toBeGreaterThanOrEqual(150)
  expect((bounds?.x ?? 0) + (bounds?.width ?? 0)).toBeLessThanOrEqual(390)
  await expect(page.getByRole('complementary', { name: '能源管理侧边栏' })).toBeHidden()
  await expect(page.getByRole('button', { name: '保存草稿', exact: true })).toBeVisible()
  await mobileInput.fill('112.5')
  await page.getByRole('button', { name: '保存草稿', exact: true }).click()
  await expect(page.getByText('草稿已保存，正式报表未变更')).toBeVisible()
})
