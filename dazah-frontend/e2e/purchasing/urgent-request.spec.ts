import { expect, test } from '@playwright/test'

test.describe('加急采购申请', () => {
  test('初始不预置类型，可添加类型分组和附件说明', async ({ page }) => {
    await page.goto('/purchasing/request/urgent', { waitUntil: 'domcontentloaded' })

    await expect(page.getByRole('heading', { name: '加急单采购申请' })).toBeVisible()
    await expect(page.getByText('可添加多个申请类型，每类类型只能添加一个分组')).toBeVisible()
    await page.waitForTimeout(500)

    await page.getByRole('button', { name: '附件说明' }).click()
    const attachmentDialog = page.getByRole('dialog', { name: '附件说明' })
    await attachmentDialog.getByRole('textbox').fill('加急采购技术附件')
    await attachmentDialog.getByRole('button', { name: '保存说明' }).click()
    await expect(page.getByRole('button', { name: /附件说明（已填写）/ })).toBeVisible()

    await page.getByRole('button', { name: '添加申请类型' }).click()
    const categoryDialog = page.getByRole('dialog', { name: '添加申请类型' })
    await categoryDialog.locator('.ant-select').click()
    await page.getByText('五金材料', { exact: true }).last().click()
    await page
      .locator('.ant-modal-wrap:visible')
      .last()
      .locator('.ant-modal-footer .ant-btn-primary')
      .click()

    await expect(page.getByRole('columnheader', { name: '物料编码' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: '物料说明' })).toBeVisible()
  })
})
