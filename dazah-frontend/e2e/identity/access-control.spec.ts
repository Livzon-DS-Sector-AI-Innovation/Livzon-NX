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

    const purchasingResponse = await page.goto('/purchasing/supplier')

    expect(purchasingResponse?.status()).toBe(200)
    await expect(page).toHaveURL(`${applicationUrl}/purchasing/supplier`)
    await expect(page.getByRole('navigation', { name: '业务模块' }).getByRole('link', { name: '采购管理', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: '供应商管理' })).toBeVisible()
    await expect(page.getByRole('navigation', { name: '业务模块' }).getByRole('link', { name: '质量管理', exact: true })).toHaveCount(0)

    const qualityResponse = await page.goto('/quality')

    expect(qualityResponse?.status()).toBe(403)
    await expect(page.getByRole('heading', { name: '页面访问受限' })).toBeVisible()
    await expect(page.getByText('未获得本模块的任何页面访问权限。')).toBeVisible()
  })

  test('地址栏令牌会被移除且不能覆盖已有会话', async ({ context, page }) => {
    await useAuthToken(context, 'procurement-only')
    const response = await page.goto('/purchasing/supplier?auth_token=untrusted-value')

    expect(response?.status()).toBe(200)
    await expect(page).toHaveURL(`${applicationUrl}/purchasing/supplier`)
    await expect(page.getByRole('heading', { name: '供应商管理' })).toBeVisible()

    const authCookie = (await context.cookies()).find(
      (cookie) => cookie.name === 'auth_token',
    )
    expect(authCookie?.value).toBe('procurement-only')
  })
})
