import { expect, test, type Page } from '@playwright/test'

async function openAssistant(page: Page) {
  await page.goto('/settings')
  await page.getByRole('button', { name: '打开中枢助手' }).click()
  await expect(page.getByText('Livzon助手', { exact: true })).toBeVisible()
}

async function sendMessage(page: Page, message: string) {
  await page.getByLabel('中枢助手输入框').fill(message)
  await page.getByRole('button', { name: '发送' }).click()
}

test.describe('Livzon 助手关键交互', () => {
  test('可以停止仍在生成的请求并立即重新发送', async ({ page }) => {
    await openAssistant(page)
    await sendMessage(page, '停止生成测试')

    const stopButton = page.getByRole('button', { name: '停止' })
    await expect(stopButton).toBeVisible()
    await stopButton.click()
    await expect(page.getByRole('button', { name: '停止' })).toBeHidden()

    await sendMessage(page, '停止后重试')
    await expect(page.getByText('助手关键流程测试完成')).toBeVisible()
  })

  test('附件随请求发送且历史会话可以恢复', async ({ page }) => {
    await openAssistant(page)
    await page.locator('input[type="file"]').setInputFiles({
      name: '偏差说明.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('E2E attachment'),
    })

    await expect(page.getByLabel('待发送附件').getByText('偏差说明.txt')).toBeVisible()
    await sendMessage(page, '分析附件')
    await expect(page.getByText('已分析 1 个附件')).toBeVisible()

    await page.getByRole('button', { name: '查看历史会话' }).click()
    await expect(page.getByText('飞书历史会话')).toBeVisible()
    await page.getByRole('button', { name: '继续对话' }).click()
    await expect(page.getByText('历史恢复内容', { exact: true }).first()).toBeVisible()
  })

  test('展示多个确认项、部分成功后的后续确认，并自动移除过期项', async ({ page }) => {
    await openAssistant(page)
    await sendMessage(page, '多个确认测试')

    await expect(page.getByText('创建第一项偏差')).toBeVisible()
    await expect(page.getByText('创建第二项偏差')).toBeVisible()
    await page.getByRole('button', { name: '确认执行' }).first().click()
    await expect(page.getByText('确认后续通知', { exact: true })).toBeVisible()
    await expect(page.getByText(/自动化流程已暂停，等待确认/)).toBeVisible()

    await page.getByRole('button', { name: '开启新对话' }).click()
    await sendMessage(page, '过期确认测试')
    await expect(page.getByText('即将过期的操作')).toBeVisible()
    await expect(page.getByText('即将过期的操作')).toBeHidden({ timeout: 5_000 })
  })

  test('断线时展示可操作错误且后续请求可以恢复', async ({ page }) => {
    await openAssistant(page)
    await sendMessage(page, '断线恢复测试')

    await expect(
      page.getByText('Livzon Agent 连接已中断，未收到完整回复，请重试。'),
    ).toBeVisible()
    await sendMessage(page, '断线后恢复')
    await expect(page.getByText('助手关键流程测试完成')).toBeVisible()
  })
})
