import { expect, test } from '@playwright/test'

for (const colorScheme of ['light', 'dark'] as const) {
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
