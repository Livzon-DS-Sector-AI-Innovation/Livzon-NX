import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

for (const mode of ['light', 'dark'] as const) {
  test(`production overlay content remains scrollable at 320px ${mode}`, async ({ context, page, baseURL }) => {
    await page.setViewportSize({ width: 320, height: 900 })
    await context.addCookies([{ name: 'auth_token', value: `production-overlays-${randomUUID()}`, url: baseURL! }])
    await page.goto('/production/batches/workshop/201-2/traceability?stage=refinement&batch_no=LOCAL-OVERLAY-TEST')
    await page.getByTitle(mode === 'light' ? '浅色' : '深色', { exact: true }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', mode)
    await page.getByRole('button', { name: '收起侧边栏', exact: true }).click()
    await page.waitForTimeout(500)
    await page.getByRole('button', { name: /历史记录/ }).click()
    const content = page.locator('.ant-popover:visible .ant-popover-content')
    await expect(content).toContainText('本地浮层验收记录')
    await expect(content).toHaveCSS('overflow-x', 'auto')
    await content.evaluate(el => { el.scrollLeft = el.scrollWidth })
    expect(await content.evaluate(el => el.scrollLeft)).toBeGreaterThan(0)
    await page.waitForTimeout(500)
    await test.info().attach(`history-scrolled-${mode}-320`, { body: await page.screenshot(), contentType: 'image/png' })

    await page.goto('/production/batches/workshop/201-3/blending')
    await page.getByRole('button', { name: '收起侧边栏', exact: true }).click()
    await page.waitForTimeout(500)
    const remarkButton = page.getByRole('button', { name: '查看备注', exact: true })
    await remarkButton.focus()
    await expect(remarkButton).toBeFocused()
    await remarkButton.press('Space')
    await expect(content).toContainText('本地验收备注')
    await expect(content).toHaveCSS('overflow-y', 'auto')
    await content.evaluate(el => { el.scrollTop = el.scrollHeight })
    expect(await content.evaluate(el => el.scrollTop)).toBeGreaterThan(0)
    await page.waitForTimeout(500)
    await test.info().attach(`remark-scrolled-${mode}-320`, { body: await page.screenshot(), contentType: 'image/png' })
  })
}
