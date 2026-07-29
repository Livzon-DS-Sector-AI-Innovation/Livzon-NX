import { expect, test } from '@playwright/test'

const contractRecord = {
  id: '11111111-1111-1111-1111-111111111111',
  title: '7月耗材采购合同',
  category: 'consumables',
  contract_number: 'HT-202607-001',
  contract_date: '2026-07-06',
  seller_name: '杭州示例供应商有限公司',
  filename: '7月耗材采购合同.docx',
  file_path:
    'storage/procurement/contracts/11111111-1111-1111-1111-111111111111/7月耗材采购合同.docx',
  content_type:
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  file_size: 20480,
  payload: {},
  created_at: '2026-07-06T09:00:00Z',
  updated_at: '2026-07-06T09:00:00Z',
}

test.describe('采购合同汇总', () => {
  test('支持搜索合同、展示卡片并打开详情抽屉', async ({ page }) => {
    test.setTimeout(60_000)

    await page.route((url) => url.href.includes('/api/v1/procurement/contracts'), async (route) => {
      const url = new URL(route.request().url())

      if (url.pathname.endsWith('/file')) {
        await route.fulfill({
          status: 200,
          contentType:
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          headers: {
            'Content-Disposition':
              "attachment; filename*=utf-8''7%E6%9C%88%E8%80%97%E6%9D%90%E9%87%87%E8%B4%AD%E5%90%88%E5%90%8C.docx",
          },
          body: 'mock-docx',
        })
        return
      }

      if (url.pathname.endsWith(`/${contractRecord.id}`)) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            code: 200,
            message: 'success',
            data: contractRecord,
          }),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          message: 'success',
          data: [contractRecord],
          meta: { page: 1, page_size: 12, total: 1 },
        }),
      })
    })

    await page.goto('/purchasing/contract-summary', {
      waitUntil: 'domcontentloaded',
    })

    await expect(page.getByRole('heading', { name: '合同汇总' })).toBeVisible()
    await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})
    await page.waitForTimeout(500)

    const searchInput = page.getByPlaceholder('搜索合同标题、编号或卖方')
    await searchInput.fill('耗材')
    await searchInput.press('Enter')

    await expect(page.getByText('7月耗材采购合同')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('HT-202607-001')).toBeVisible()
    await expect(page.getByText('杭州示例供应商有限公司')).toBeVisible()

    await page.getByRole('button', { name: '详情' }).click()

    await expect(page.getByRole('dialog', { name: '7月耗材采购合同' })).toBeVisible()
    await expect(page.getByText('合同编号', { exact: true })).toBeVisible()
    await expect(page.getByText('下载合同')).toBeVisible()
  })
})
