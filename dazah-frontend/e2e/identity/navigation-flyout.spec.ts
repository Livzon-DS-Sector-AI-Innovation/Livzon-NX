import { expect, test } from '@playwright/test'

test('module and flyout navigation reach a page without moving sidebar entries', async ({ context, page }) => {
  await context.addCookies([{ name: 'auth_token', value: 'admin-no-page-grants', url: 'http://127.0.0.1:3200' }])
  await page.goto('/production')

  await page.getByRole('navigation', { name: '业务模块' }).getByRole('link', { name: '质量管理' }).click()
  await expect(page).toHaveURL(/\/quality$/)

  const sidebar = page.locator('aside').first()
  const parent = sidebar.getByText('偏差管理', { exact: true })
  const position = await parent.boundingBox()
  expect(position).not.toBeNull()
  await parent.hover()
  const popup = page.locator('.sidebar-submenu-popup').filter({ hasText: '偏差台账' })
  await expect(popup).toBeVisible()
  expect((await parent.boundingBox())?.y).toBe(position?.y)

  await popup.getByText('偏差台账', { exact: true }).click()
  await expect(page).toHaveURL(/\/quality\/deviations\/ledger$/)
  await expect(popup).toBeHidden()
})
