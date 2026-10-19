import { randomUUID } from 'node:crypto'
import { expect, test, type Locator } from '@playwright/test'

export function registerModuleOverlayTests(module: 'quality' | 'hr' | 'warehouse' | 'registration') {
  for (const width of [1280, 768, 390, 320]) {
    for (const mode of ['light', 'dark'] as const) {
      test(`${module} overlays ${width}px ${mode}`, async ({ context, page, baseURL }) => {
        test.setTimeout(240_000)
        page.setDefaultTimeout(15_000)
        page.setDefaultNavigationTimeout(90_000)
        const height = width === 320 ? 568 : width === 390 ? 700 : 900
        const token = `module-overlays-${randomUUID()}`
        await context.addCookies([{ name: 'auth_token', value: token, url: baseURL! }])
        await page.setViewportSize({ width, height })
        await page.emulateMedia({ colorScheme: mode })
        await page.route('**/__dazah_maintenance_status', route => route.fulfill({ json: { phase: 'normal' } }))
        const errors: string[] = []
        page.on('pageerror', error => errors.push(error.message))

        async function visit(path: string, ready: Locator) {
          await page.goto(path, { waitUntil: 'load' })
          await expect(ready).toBeVisible()
          await page.getByTitle(mode === 'light' ? '浅色' : '深色', { exact: true }).click()
          await expect(page.locator('html')).toHaveAttribute('data-theme', mode)
          const collapse = page.getByRole('button', { name: '收起侧边栏', exact: true })
          if (width < 768 && await collapse.isVisible()) await collapse.click()
          await page.waitForTimeout(500)
        }
        async function fits(layer: Locator, name: string) {
          await expect(layer).toBeVisible()
          await page.waitForTimeout(500)
          const box = await layer.boundingBox()
          expect(box, name).not.toBeNull()
          expect(box!.x, `${name} left`).toBeGreaterThanOrEqual(0)
          expect(box!.x + box!.width, `${name} right`).toBeLessThanOrEqual(width + 1)
          expect(box!.y, `${name} top`).toBeGreaterThanOrEqual(0)
          expect(box!.y + box!.height, `${name} bottom`).toBeLessThanOrEqual(height + 1)
          await test.info().attach(`${name}-${mode}-${width}`, { body: await page.screenshot(), contentType: 'image/png' })
        }
        async function cancelPopup(trigger: Locator, name: string) {
          await trigger.click()
          const popup = page.locator('.ant-popconfirm:visible')
          await fits(popup, name)
          for (const button of await popup.getByRole('button').all()) {
            const box = await button.boundingBox()
            expect(box!.x).toBeGreaterThanOrEqual(0)
            expect(box!.x + box!.width).toBeLessThanOrEqual(width)
          }
          await popup.getByRole('button', { name: /^取\s*消$/ }).click()
          await expect(popup).toBeHidden()
        }
        const dialog = page.locator('.ant-modal[role="dialog"]:visible')

        if (module === 'hr') {
          await visit('/hr/settings/dept-mapping', page.getByRole('tab', { name: '人员归属' }))
          await page.getByRole('tab', { name: '人员归属' }).click()
          await cancelPopup(page.getByRole('button', { name: /^删\s*除$/ }), 'hr-long-delete')
          await page.getByRole('button', { name: /^编\s*辑$/ }).click()
          await fits(dialog, 'hr-edit')
          await page.keyboard.press('Escape')

          await visit('/hr/contracts', page.getByRole('button', { name: /续签/ }))
          await page.getByRole('button', { name: /详\s*情/ }).click()
          await fits(page.locator('.ant-drawer-content-wrapper'), 'hr-contract-detail')
          await page.keyboard.press('Escape')
          await expect(page.locator('.ant-drawer-content-wrapper')).toBeHidden()
          await page.getByRole('button', { name: /续签/ }).click()
          await fits(dialog, 'hr-renewal')
          await dialog.locator('.ant-picker input').first().click()
          await fits(page.locator('.ant-picker-dropdown:visible'), 'hr-renewal-date')
          expect(await page.locator('.ant-picker-dropdown:visible').evaluate(el => el.closest('.ant-modal-body'))).toBeNull()
          await page.keyboard.press('Escape')
          await page.keyboard.press('Escape')

          await visit('/hr/contracts/approval-results', page.locator('.ant-picker-range'))
          await page.locator('.ant-picker-range input').first().click()
          const range = page.locator('.ant-picker-dropdown:visible')
          await fits(range, 'hr-date-range')
          if (width < 768) {
            const panel = range.locator('.ant-picker-panel-container')
            expect(await panel.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true)
            await panel.evaluate(el => { el.scrollLeft = el.scrollWidth })
            await fits(range, 'hr-date-range-scrolled')
        }
        await page.keyboard.press('Escape')
        await page.locator('.ant-picker-range input').first().click()
        const days = range.locator('.ant-picker-panel').first().locator('td.ant-picker-cell-in-view[title]')
        const start = await days.nth(9).getAttribute('title')
        const end = await days.nth(14).getAttribute('title')
        await days.nth(9).click()
        await days.nth(14).click()
        await expect(page.locator('.ant-picker-range input').first()).toHaveValue(start!)
        await expect(page.locator('.ant-picker-range input').last()).toHaveValue(end!)

        }

        if (module === 'registration') {
          await visit('/registration/fees/contacts', page.getByText('浮层验收项目', { exact: true }))
          await page.locator('tr[data-row-key] input[type="radio"]').check()
          await cancelPopup(page.getByRole('button', { name: /删除/ }), 'registration-delete')
          await page.getByRole('button', { name: /新\s*增/ }).click()
          await fits(dialog, 'registration-form')
          await page.keyboard.press('Escape')

        }

        if (module === 'warehouse') {
          await visit('/warehouse/materials/raw-ledger', page.getByRole('button', { name: '同步最新数据' }))
          await cancelPopup(page.getByRole('button', { name: '同步最新数据' }), 'warehouse-sync')
          await page.getByRole('button', { name: /详\s*情/ }).click()
          await expect(dialog).toContainText('浮层验收物料')
          await fits(dialog, 'warehouse-detail')
          await cancelPopup(dialog.getByRole('button', { name: '删除记录' }), 'warehouse-nested-delete')
          await dialog.getByRole('button', { name: /^编\s*辑$/ }).click()
          await fits(dialog, 'warehouse-edit-footer')
          if (width < 576) {
            const input = await dialog.locator('textarea').first().boundingBox()
            expect(input!.width, 'editable value must remain readable').toBeGreaterThanOrEqual(120)
          }
          for (const button of await dialog.locator('.ant-modal-footer').getByRole('button').all()) {
            const box = await button.boundingBox()
            expect(box!.x + box!.width).toBeLessThanOrEqual(width)
        }
        await page.keyboard.press('Escape')

        }

        if (module === 'quality') {
          await visit('/quality/return-recalls/return-application', page.getByText('浮层验收退货', { exact: true }))
          await cancelPopup(page.getByRole('button', { name: /^删\s*除$/ }), 'quality-delete')
          await page.getByRole('button', { name: /新\s*增/ }).click()
          await fits(dialog, 'quality-return-sheet')
          const person = dialog.getByRole('combobox').filter({ visible: true }).first()
          await person.click()
          await fits(page.locator('.ant-select-dropdown:visible'), 'quality-sheet-person')
          expect(await page.locator('.ant-select-dropdown:visible').evaluate(el => el.closest('.ant-modal-body'))).toBeNull()
          await page.getByText('浮层验收联系人', { exact: true }).click()
          await expect(dialog.locator('.ant-select').first()).toContainText('浮层验收联系人')
          await dialog.locator('.ant-picker input').first().click()
          await fits(page.locator('.ant-picker-dropdown:visible'), 'quality-sheet-date')
          await page.keyboard.press('Escape')
          await page.keyboard.press('Escape')

          await visit('/quality/validation/equipment-qualification', page.getByRole('button', { name: /新\s*增/ }).first())
          await page.getByRole('button', { name: /新\s*增/ }).first().click()
          await fits(dialog, 'quality-validation-form')
          await dialog.getByRole('combobox', { name: '任务状态' }).click()
          await fits(page.locator('.ant-select-dropdown:visible'), 'quality-validation-status')
          expect(await page.locator('.ant-select-dropdown:visible').evaluate(el => el.closest('.ant-modal-body'))).toBeNull()
          await page.getByText('未完成', { exact: true }).last().click()
          await expect(dialog.locator('.ant-select').filter({ hasText: '未完成' })).toBeVisible()
          await page.keyboard.press('Escape')

          for (const [path, trigger, title] of [
            ['/quality/capas/ledger', /导\s*入$/, '导入CAPA数据'],
            ['/quality/oos-oot/oot-limits', /导入告知单/, '导入OOT限度告知单'],
          ] as const) {
            await visit(path, page.getByRole('button', { name: trigger }))
            await page.getByRole('button', { name: trigger }).click()
            const drawer = page.locator('.ant-drawer-content-wrapper')
            await expect(drawer).toContainText(title)
            await fits(drawer, title === '导入CAPA数据' ? 'quality-import-preview' : 'quality-oot-import')
            await drawer.getByRole('button', { name: /^取\s*消$/ }).click()
            await expect(drawer).toBeHidden()
          }

        }

        const writes = await context.request.get('/api/v1/quality/__test/module-overlay-writes', { headers: { Authorization: `Bearer ${token}` } })
        expect((await writes.json()).data).toBe(0)
        expect(errors).toEqual([])
      })
    }
  }
}
