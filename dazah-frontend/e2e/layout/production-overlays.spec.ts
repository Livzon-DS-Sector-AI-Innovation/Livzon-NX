import { randomUUID } from 'node:crypto'
import { expect, test, type Locator } from '@playwright/test'

for (const width of [1280, 768, 390, 320]) {
  for (const mode of ['light', 'dark'] as const) {
    test(`production overlays ${width}px ${mode}`, async ({ context, page, baseURL }) => {
      test.setTimeout(180_000)
      page.setDefaultTimeout(15_000)
      page.setDefaultNavigationTimeout(90_000)
      await page.setViewportSize({ width, height: 900 })
      await page.emulateMedia({ colorScheme: mode })
      await context.addCookies([{ name: 'auth_token', value: `production-overlays-${randomUUID()}`, url: baseURL! }])
      await page.route('**/__dazah_maintenance_status', route => route.fulfill({ json: { phase: 'normal' } }))
      const errors: string[] = []
      page.on('pageerror', error => errors.push(error.message))

      async function visit(path: string) {
        await page.goto(`/production${path}`, { waitUntil: 'load' })
        await page.getByTitle(mode === 'light' ? '浅色' : '深色', { exact: true }).click()
        await expect(page.locator('html')).toHaveAttribute('data-theme', mode)
        const collapse = page.getByRole('button', { name: '收起侧边栏', exact: true })
        if (width < 768 && await collapse.isVisible()) await collapse.click()
      }
      async function fits(layer: Locator, name: string, margin = 0) {
        await expect(layer).toBeVisible()
        // Ant Design begins entry motion after its first visible frame.
        await page.waitForTimeout(500)
        const box = await layer.boundingBox()
        expect(box, name).not.toBeNull()
        expect(box!.x, `${name} left`).toBeGreaterThanOrEqual(margin)
        expect(box!.x + box!.width, `${name} right`).toBeLessThanOrEqual(width - margin + 1)
        expect(box!.y, `${name} top`).toBeGreaterThanOrEqual(0)
        expect(box!.y + box!.height, `${name} bottom`).toBeLessThanOrEqual(901)
        await test.info().attach(`${name}-${mode}-${width}`, { body: await page.screenshot(), contentType: 'image/png' })
      }
      async function cancelConfirmation(trigger: Locator, name: string) {
        await trigger.click()
        const dialog = page.locator('.ant-modal[role="dialog"]')
        await fits(dialog, name, 15)
        for (const button of [dialog.getByRole('button', { name: /^取\s*消$/ }), dialog.getByRole('button', { name: /^(删\s*除|通\s*过)$/ })]) {
          const box = await button.boundingBox()
          expect(box!.x).toBeGreaterThanOrEqual(0)
          expect(box!.x + box!.width).toBeLessThanOrEqual(width)
        }
        await dialog.getByRole('button', { name: /^取\s*消$/ }).click()
        await expect(dialog).toBeHidden()
      }

      await visit('/scheduling')
      await cancelConfirmation(page.getByRole('button', { name: '删除排产存档', exact: true }), 'schedule-delete')
      await expect(page.getByText('LOCAL-OVERLAY-TEST.xlsx', { exact: true })).toBeVisible()

      await visit('')
      await page.getByText('L-苯丙氨酸', { exact: true }).click()
      await page.getByRole('button', { name: /历史数据/ }).click()
      await fits(page.locator('.ant-drawer-content-wrapper'), 'actual-history-drawer')
      await cancelConfirmation(page.getByRole('button', { name: /^删\s*除$/ }), 'actual-delete')

      await visit('/pressure/records')
      await cancelConfirmation(page.getByRole('button', { name: '删除压差记录', exact: true }), 'pressure-delete')
      await page.locator('tr[data-row-key] input[type="checkbox"]').check()
      await cancelConfirmation(page.getByRole('button', { name: /批量删除/ }), 'pressure-bulk-delete')

      await page.locator('.ant-picker-range input').first().click()
      const dates = page.locator('.ant-picker-dropdown:visible')
      await fits(dates, 'date-range')
      const dateScroll = dates.locator('.ant-picker-panel-container')
      if (width < 768) {
        expect(await dateScroll.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true)
        await dateScroll.evaluate(el => { el.scrollLeft = el.scrollWidth })
        await fits(dates, 'date-range-scrolled')
      }
      await page.keyboard.press('Escape')
      await page.locator('.ant-picker-range input').first().click()
      const days = dates.locator('.ant-picker-panel').first().locator('td.ant-picker-cell-in-view[title]')
      const start = await days.nth(9).getAttribute('title')
      const end = await days.nth(14).getAttribute('title')
      await days.nth(9).click()
      await days.nth(14).click()
      await expect(page.locator('.ant-picker-range input').first()).toHaveValue(start!)
      await expect(page.locator('.ant-picker-range input').last()).toHaveValue(end!)

      await visit('/pressure/audit')
      await cancelConfirmation(page.getByRole('button', { name: '通过记录', exact: true }), 'pressure-approve')
      await page.locator('tr[data-row-key] input[type="checkbox"]').check()
      await cancelConfirmation(page.getByRole('button', { name: /批量通过/ }), 'pressure-bulk-approve')
      await page.getByRole('button', { name: '驳回记录', exact: true }).click()
      await fits(page.locator('.ant-modal[role="dialog"]'), 'pressure-reject')
      await page.keyboard.press('Escape')

      await visit('/pressure/point-management')
      await cancelConfirmation(page.getByRole('button', { name: '删除压差位点', exact: true }), 'point-delete')
      await page.getByRole('button', { name: /新增位点/ }).click()
      await fits(page.locator('.ant-modal[role="dialog"]'), 'point-create')
      await page.keyboard.press('Escape')

      // Both full-page history popovers must retain all columns through scrolling.
      for (const workshop of ['201-2', '203']) {
        await visit(`/batches/workshop/${workshop}/traceability?stage=${workshop === '203' ? 'fermentation' : 'refinement'}&${workshop === '203' ? 'batchNo' : 'batch_no'}=LOCAL-OVERLAY-TEST`)
        if (workshop === '203') {
          await page.waitForTimeout(1000)
          const traced = page.waitForResponse(response => response.url().includes('/fa/lineage/trace') && response.status() === 200)
          await page.getByRole('button', { name: /追溯/ }).click()
          await traced
        }
        const history = page.getByRole('button', { name: workshop === '203' ? /分析历史/ : /历史记录/ })
        await history.click()
        const popup = page.locator('.ant-popover').filter({ hasText: '分析历史' })
        await expect(popup).toContainText('本地浮层验收记录')
        await fits(popup, `${workshop}-history`)
        if (width < 520) {
          const scroll = popup.locator('.ant-popover-content')
          expect(await scroll.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true)
          await scroll.evaluate(el => { el.scrollLeft = el.scrollWidth })
        }
        await history.click()
      }

      // Trace modal headers and their nested history popovers resize with the viewport.
      for (const [path, placeholder, historyName] of [
        ['/batches/workshop/201-2/extraction', '输入批号查询', '历史记录'],
        ['/batches/workshop/203/acidification', '输入批号追溯', '历史'],
        ['/batches/workshop/201-3/dr-refinement', '输入批号查询', ''],
      ]) {
        await visit(path)
        await page.waitForTimeout(1000)
        await page.getByPlaceholder(placeholder, { exact: true }).fill('LOCAL-OVERLAY-TEST')
        await page.getByTitle(path.includes('201-2') || path.includes('201-3') ? '追溯' : '批次追溯', { exact: true }).click()
        const dialog = page.locator('.ant-modal[role="dialog"]')
        await fits(dialog, `trace-${historyName || 'DR'}`, 15)
        if (historyName) {
          await dialog.getByRole('button', { name: new RegExp(historyName) }).click()
          const popup = page.locator('.ant-popover').filter({ hasText: '分析历史' })
          await expect(popup).toContainText('本地浮层验收记录')
          await fits(popup, `nested-${historyName}`)
        }
      }
      await visit('/batches/workshop/201-3/blending')
      await page.getByRole('button', { name: '查看备注', exact: true }).click()
      const remark = page.locator('.ant-popover:visible')
      await expect(remark).toContainText('本地验收备注')
      await fits(remark, 'DR-remark')
      expect(errors).toEqual([])
    })
  }
}
