import { expect, test } from '@playwright/test'
import { openCriticalBusinessSession } from '../critical-business-session'

const ledgerPath = '/safety/hazard-identification/ledger'
const detailPath = `${ledgerPath}/31000000-0000-4000-8000-000000000006`

for (const { width, appearance } of [
  { width: 390, appearance: 'dark' },
  { width: 1280, appearance: 'light' },
]) {
  test(`危险源辨识台账可点击查看并返回 ${width}px ${appearance}`, async ({ context, page, baseURL }) => {
    await page.setViewportSize({ width, height: 900 })
    await openCriticalBusinessSession(context, baseURL, 'safety-ledger-admin')
    await page.addInitScript((mode) => localStorage.setItem('dazah-appearance', mode), appearance)
    await page.goto(ledgerPath)
    await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)

    const department = page.getByRole('cell', { name: '危险源测试车间', exact: true })
    const row = page.getByRole('row').filter({ has: department })
    if (width === 1280) await expect(department).toHaveCSS('position', 'sticky')
    await row.getByRole('button', { name: '查看', exact: true }).click({ timeout: 10000 })
    await expect(page).toHaveURL(detailPath)
    await expect(page.getByRole('heading', { name: '危险源辨识详情' })).toBeVisible()
    await expect(page.getByText('编号：HI-E2E-001', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: '返回列表' }).click()
    await expect(page).toHaveURL(ledgerPath)
    await expect(row).toBeVisible()
  })
}
