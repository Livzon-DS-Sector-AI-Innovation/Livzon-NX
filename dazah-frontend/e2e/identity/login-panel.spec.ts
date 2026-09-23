import { expect, test } from '@playwright/test'

for (const width of [1280, 375]) {
  test(`登录入口在 ${width}px 下显示完整布局与错误恢复`, async ({ page, context }) => {
    await context.addCookies([{ name: 'auth_token', value: 'invalid-session', url: 'http://127.0.0.1:3200' }])
    await page.setViewportSize({ width, height: 850 })
    await page.goto('/login?error=access_denied')
    await expect(page.getByRole('heading', { name: '欢迎登录' })).toBeVisible()
    await expect(page.getByRole('alert').filter({ hasText: '你已取消飞书授权' })).toBeVisible()
    await expect(page.getByRole('list', { name: '登录流程' })).toBeVisible()
    const login = page.getByRole('button', { name: '使用飞书企业账号登录' })
    await expect(login).toBeVisible()
    await login.focus()
    await expect(login).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

test('认证入口未完成跳转时恢复操作', async ({ page, context }) => {
  await context.addCookies([{ name: 'auth_token', value: 'invalid-session', url: 'http://127.0.0.1:3200' }])
  // A no-content response retains the current page instead of completing navigation.
  await page.route('**/auth/login?**', route => route.fulfill({ status: 204 }))
  await page.goto('/login')
  await page.getByRole('button', { name: '使用飞书企业账号登录' }).click()
  await expect(page.getByRole('button', { name: '正在打开飞书认证…' })).toBeDisabled()
  await expect(page.getByRole('status')).toContainText('正在前往飞书')
  await expect(page.getByRole('alert').filter({ hasText: '检查网络后重试' })).toBeVisible({ timeout: 15000 })
  await expect(page.getByRole('button', { name: '使用飞书企业账号登录' })).toBeEnabled()
})
