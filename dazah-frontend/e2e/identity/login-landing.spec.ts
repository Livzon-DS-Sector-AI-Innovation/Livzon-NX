import { expect, test } from '@playwright/test'

test('登录完成后直接进入已授权的采购子页面', async ({ context, page }) => {
  await context.addCookies([{ name: 'auth_token', value: 'page-query', url: 'http://127.0.0.1:3200' }])
  await page.goto('/login/complete?next=%2Fproduction')
  await expect(page).toHaveURL(/\/purchasing\/supplier$/)
  await expect(page.getByText('未获得批量导入权限，仅可查询供应商清单')).toBeVisible()
})

for (const token of ['restricted', 'page-denied']) {
  test(`${token} 登录后显示统一提示并支持重新检查授权`, async ({ context, page }) => {
    await context.addCookies([{ name: 'auth_token', value: token, url: 'http://127.0.0.1:3200' }])
    await page.goto('/login/complete')
    await expect(page).toHaveURL(/\/no-access$/)
    await expect(page.getByRole('heading', { name: '账号已登录，暂未分配可访问的业务页面' })).toBeVisible()
    await expect(page.getByText('请联系管理员为你分配模块和页面权限。授权完成后，可重新检查权限进入系统。')).toBeVisible()
    await page.setViewportSize({ width: 375, height: 812 })
    await expect(page.getByRole('link', { name: '退出登录' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await context.addCookies([{ name: 'auth_token', value: 'page-query', url: 'http://127.0.0.1:3200' }])
    await page.getByRole('button', { name: '重新检查权限' }).click()
    await expect(page).toHaveURL(/\/purchasing\/supplier$/)
  })
}

test('已授权用户访问提示页会进入业务页面，失效登录返回登录页', async ({ context, page }) => {
  await context.addCookies([{ name: 'auth_token', value: 'page-query', url: 'http://127.0.0.1:3200' }])
  await page.goto('/no-access')
  await expect(page).toHaveURL(/\/purchasing\/supplier$/)
  await context.addCookies([{ name: 'auth_token', value: 'invalid-session', url: 'http://127.0.0.1:3200' }])
  await page.goto('/no-access')
  await expect(page).toHaveURL(/\/login$/)
})
