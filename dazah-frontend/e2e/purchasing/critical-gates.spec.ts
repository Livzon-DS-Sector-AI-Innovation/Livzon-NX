import { expect, test } from '@playwright/test'

test.describe('采购高风险操作门禁', () => {
  test('无模块权限时显示明确拒绝状态', async ({ context, page }) => {
    await context.addCookies([
      {
        name: 'auth_token',
        value: 'restricted',
        url: 'http://127.0.0.1:3200',
      },
    ])

    await page.goto('/purchasing/invoice-recognition')

    await expect(page.getByRole('heading', { name: '暂无模块访问权限' })).toBeVisible()
    await expect(page.getByText('请联系管理员调整模块授权')).toBeVisible()
  })

  test('驳回必须确认、填写原因，并显示后端失败', async ({ page }) => {
    await page.goto('/purchasing/approval/hardware/hardware-warehouse')

    await expect(page.getByText('工程设备部')).toBeVisible()
    const rejectButton = page.getByRole('button', { name: '驳回' })
    await expect(rejectButton).toBeEnabled()
    await rejectButton.click()

    const dialog = page.getByRole('dialog', { name: '驳回采购申请' })
    await expect(dialog).toBeVisible()
    const opinion = dialog.getByLabel('审批意见')
    await expect(opinion).toHaveAttribute('aria-required', 'true')
    await opinion.fill('预算资料不完整')
    await dialog.getByRole('button', { name: '确认驳回' }).click()

    await expect(page.getByText('模拟审批服务暂时不可用')).toBeVisible()
    await expect(dialog).toBeVisible()
  })
})
