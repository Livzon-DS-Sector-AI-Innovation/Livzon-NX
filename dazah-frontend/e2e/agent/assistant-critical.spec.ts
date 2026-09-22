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
  test('展示 Agent 欢迎页并可从常用任务发起对话', async ({ page }) => {
    await openAssistant(page)
    await expect(page.getByRole('heading', { name: '你好，我是 Livzon 助手' })).toBeVisible()
    await expect(page.getByText('创建、同步、发送等写操作会先请你确认')).toBeVisible()
    const safetyAlignment = await page.locator('.agent-welcome-safety').evaluate((row) => {
      const icon = row.querySelector('.anticon')?.getBoundingClientRect()
      const text = row.querySelector('span:not(.anticon)')?.getBoundingClientRect()
      if (!icon || !text) return null
      return Math.abs(icon.top + icon.height / 2 - text.top - text.height / 2)
    })
    if (safetyAlignment === null) throw new Error('确认提示未完成布局')
    expect(safetyAlignment).toBeLessThanOrEqual(1)
    await expect(page.getByRole('button', { name: /质量偏差/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /采购审批/ })).toBeInViewport({ ratio: 1 })
    await expect(page.getByLabel('中枢助手输入框')).toBeVisible()

    await page.getByRole('button', { name: /质量偏差/ }).click()
    await expect(page.getByText('查询质量偏差报告记录', { exact: true }).last()).toBeVisible()
  })

  test('窄屏仍能使用窗口操作和输入区', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await openAssistant(page)
    await expect(page.getByRole('button', { name: '查看历史会话' })).toBeInViewport()
    await expect(page.getByRole('button', { name: '关闭中枢助手' })).toBeInViewport()
    await expect(page.getByLabel('中枢助手输入框')).toBeInViewport()
    await expect(page.getByRole('heading', { name: '你好，我是 Livzon 助手' })).toBeInViewport()
  })

  test('悬浮入口默认收起并在悬停时向左展开', async ({ page }) => {
    await page.goto('/settings')
    const entry = page.getByRole('button', { name: '打开中枢助手' })

    await expect(entry).toHaveCSS('width', '64px')
    await entry.hover()
    await expect(entry).toHaveCSS('width', '174px')
    await expect(entry.getByText('智能助手')).toBeVisible()

    await page.mouse.move(0, 0)
    await expect(entry).toHaveCSS('width', '64px')
    await entry.click()
    await expect(page.getByText('Livzon助手', { exact: true })).toBeVisible()
  })

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
