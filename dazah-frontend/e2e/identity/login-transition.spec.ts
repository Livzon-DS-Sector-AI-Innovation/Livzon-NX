import { expect, test } from '@playwright/test'

for (const colorScheme of ['light', 'dark'] as const) {
  for (const reducedMotion of ['no-preference', 'reduce'] as const) {
    test(`${colorScheme} 外观和 ${reducedMotion} 动效下从验证成功页面揭开工作台`, async ({ context, page, baseURL }) => {
      await page.emulateMedia({ colorScheme, reducedMotion })
      await page.setViewportSize({ width: reducedMotion === 'reduce' ? 375 : 1280, height: 850 })
      await context.addCookies([{ name: 'auth_token', value: 'page-query', url: baseURL! }])
      let releaseRoute = () => {}
      const routeReady = new Promise<void>((resolve) => { releaseRoute = resolve })
      await page.route('**/purchasing/supplier?*', async (route) => {
        await routeReady
        await route.continue()
      })

      try {
        await page.goto('/login/complete?next=%2Fproduction')
        const cover = page.locator('[data-phase="waiting"]')
        await expect(cover.locator('h2')).toHaveText('身份验证成功')
        await expect(cover.locator('[aria-label="身份认证"]')).toBeVisible()
        await expect(cover.getByRole('status')).toContainText('身份验证成功')
        await expect(page.locator('[aria-busy="true"]')).toHaveCount(1)
        await expect(cover).toHaveAttribute('data-appearance', 'fixed-light')
        await expect(cover).toHaveCSS('animation-name', 'none')
        await expect(page.getByText('正在打开工作台', { exact: true })).toHaveCount(0)
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
        // Keep the existing authentication screen intact until the route is ready.
        await page.waitForTimeout(500)
        await expect(cover).toBeVisible()
        releaseRoute()
        await expect(page).toHaveURL(/\/purchasing\/supplier$/)
        if (reducedMotion === 'no-preference') {
          await expect(page.locator('[data-phase="revealing"] > [aria-hidden="true"]')).toHaveCSS('animation-name', /workspace-unveil/)
        }
        await expect(page.locator('[data-phase]')).toHaveCount(0)
        await expect(page.locator('[inert]')).toHaveCount(0)
        await expect(page.getByText('未获得批量导入权限，仅可查询供应商清单')).toBeVisible()
      } finally {
        releaseRoute()
      }
    })
  }

  for (const scenario of ['normal', 'skipped', 'start-failed'] as const) {
    test(`${colorScheme} 外观下浏览器动画 API ${scenario} 时正常进入授权页面`, async ({ context, page, baseURL }) => {
      const errors: string[] = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.emulateMedia({ colorScheme })
      await context.addCookies([{ name: 'auth_token', value: 'page-query', url: baseURL! }])
      if (scenario !== 'normal') {
        await page.addInitScript((mode) => {
          const start = document.startViewTransition.bind(document)
          document.startViewTransition = (callback) => {
            if (mode === 'start-failed') throw new DOMException('Document hidden', 'InvalidStateError')
            const transition = start(callback)
            // Exercise the browser's real rejected ready promise, as happens
            // when a tab becomes hidden while the transition is being captured.
            transition.skipTransition()
            return transition
          }
        }, scenario)
      }

      await page.goto('/login/complete?next=%2Fproduction')
      await expect(page).toHaveURL(/\/purchasing\/supplier$/)
      await expect(page.getByText('未获得批量导入权限，仅可查询供应商清单')).toBeVisible()
      expect(errors).toEqual([])
    })
  }
}
