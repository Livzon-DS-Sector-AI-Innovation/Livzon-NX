import { expect, test } from '@playwright/test'

test.describe('采购发票识别', () => {
  test('页面展示上传限制和识别结果表格', async ({ page }) => {
    test.setTimeout(60_000)

    await page.route('**/api/v1/procurement/invoices/recognition-records**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          message: 'success',
          data: [],
          meta: { page: 1, page_size: 20, total: 0 },
        }),
      })
    })

    await page.goto('/purchasing/invoice-recognition', { waitUntil: 'domcontentloaded' })

    await expect(page.getByRole('heading', { name: '发票识别' })).toBeVisible()
    await expect(page.getByText('单个文件不超过 50MB')).toBeVisible()
    await expect(page.getByRole('columnheader', { name: '发票号码' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: '数量总和' })).toHaveCount(2)
  })
})
