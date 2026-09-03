import { expect, test, type BrowserContext } from '@playwright/test'

const applicationUrl = 'http://127.0.0.1:3200'

async function useAuthToken(context: BrowserContext, value: string) {
  await context.addCookies([
    {
      name: 'auth_token',
      value,
      url: applicationUrl,
    },
  ])
}

test.describe('身份认证与模块权限', () => {
  test('受保护的业务子页面路由可解析', async ({ page }) => {
    const response = await page.goto('/production/batches')

    expect(response).not.toBeNull()
    expect(response?.status()).toBeLessThan(400)
  })

  test('失效会话访问受保护页面时返回登录入口', async ({ context, page }) => {
    await useAuthToken(context, 'invalid-session')

    await page.goto('/purchasing')

    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByRole('heading', { name: '欢迎登录' })).toBeVisible()
    await expect(page.getByRole('button', { name: '使用飞书企业账号登录' })).toBeVisible()
  })

  test('模块授权同时约束导航入口和直接访问', async ({ context, page }) => {
    await useAuthToken(context, 'procurement-only')

    await page.goto('/purchasing')

    await expect(page.getByRole('heading', { name: '采购管理工作台' })).toBeVisible()
    await expect(page.getByRole('link', { name: '采购管理' })).toBeVisible()
    await expect(page.getByRole('link', { name: '质量管理' })).toHaveCount(0)

    await page.goto('/quality')

    await expect(page.getByRole('heading', { name: '暂无模块访问权限' })).toBeVisible()
    await expect(page.getByText('当前账号未获“质量管理”的查看权限')).toBeVisible()
    await expect(page.getByRole('heading', { name: '质量管理' })).toHaveCount(0)
  })

  test('兼容登录参数会从地址栏移除并写入安全 Cookie', async ({ context, page }) => {
    await page.goto('/purchasing?auth_token=procurement-only')

    await expect(page).toHaveURL(`${applicationUrl}/purchasing`)
    await expect(page.getByRole('heading', { name: '采购管理工作台' })).toBeVisible()

    const authCookie = (await context.cookies()).find(
      (cookie) => cookie.name === 'auth_token',
    )
    expect(authCookie).toMatchObject({
      value: 'procurement-only',
      httpOnly: true,
      sameSite: 'Lax',
    })
  })
})
