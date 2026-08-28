import { expect, test, type Page } from '@playwright/test'

async function openLLMSettings(page: Page) {
  await page.goto('/settings?auth_token=e2e-admin')
  await page.waitForLoadState('networkidle')
  const llmTab = page.getByRole('tab', { name: 'LLM 模型配置' })
  await expect(async () => {
    await llmTab.click()
    await expect(llmTab).toHaveAttribute('aria-selected', 'true')
  }).toPass({ timeout: 15_000 })
  await expect(page.getByText('现有测试配置')).toBeVisible()
}

function rowFor(page: Page, name: string) {
  return page.getByRole('row').filter({ hasText: name })
}

test.describe('LLM 模型配置', () => {
  test('真实点击覆盖新建、探测、温度、激活、编辑和删除', async ({ page }) => {
    test.setTimeout(90_000)
    const browserErrors: string[] = []
    const failedResponses: string[] = []
    page.on('pageerror', (error) => browserErrors.push(error.message))
    page.on('console', (message) => {
      if (message.type() === 'error') browserErrors.push(message.text())
    })
    page.on('response', (response) => {
      if (response.status() >= 400) {
        failedResponses.push(`${response.status()} ${response.url()}`)
      }
    })

    await openLLMSettings(page)
    await expect(rowFor(page, '现有测试配置')).toContainText('模型默认')

    await page.getByRole('button', { name: '新建配置' }).click()
    const createDialog = page.getByRole('dialog', { name: '新建 LLM 配置' })
    await expect(createDialog).toBeVisible()

    const temperatureSwitch = createDialog.locator('.ant-switch').nth(0)
    const activeSwitch = createDialog.locator('.ant-switch').nth(1)
    await expect(temperatureSwitch).toHaveAttribute('aria-checked', 'false')
    await expect(activeSwitch).toHaveAttribute('aria-checked', 'true')
    await expect(createDialog.getByLabel('Temperature')).toHaveCount(0)
    await expect(createDialog.getByLabel('API 密钥')).toHaveAttribute('type', 'password')
    await createDialog.getByRole('button', { name: '显示' }).click()
    await expect(createDialog.getByLabel('API 密钥')).toHaveAttribute('type', 'text')
    await createDialog.getByRole('button', { name: '隐藏' }).click()
    await activeSwitch.click()
    await expect(activeSwitch).toHaveAttribute('aria-checked', 'false')
    await activeSwitch.click()
    await expect(activeSwitch).toHaveAttribute('aria-checked', 'true')

    await createDialog.locator('.ant-modal-footer .ant-btn-default').click()
    await expect(createDialog).toBeHidden()
    await page.getByRole('button', { name: '新建配置' }).click()
    await expect(createDialog).toBeVisible()

    await createDialog.getByLabel('配置名称').fill('新建端到端配置')
    await createDialog.getByRole('button', { name: '测试 URL' }).click()
    await expect(createDialog.getByText('请输入 API 地址')).toBeVisible()
    await expect(createDialog.getByText('请输入 API 密钥')).toBeVisible()

    await createDialog.getByLabel('API 基础 URL').fill('https://fail.example/v1')
    await createDialog.getByLabel('API 密钥').fill('e2e-key')
    await createDialog.getByLabel('模型名称').fill('e2e-model')

    await createDialog.getByRole('button', { name: '测试 URL' }).click()
    await expect(page.getByText('模拟连通性失败')).toBeVisible()
    await expect(createDialog.getByLabel('配置名称')).toHaveValue('新建端到端配置')
    browserErrors.length = 0
    failedResponses.length = 0

    await createDialog.getByLabel('API 基础 URL').fill('https://llm.example/v1')
    await createDialog.getByRole('button', { name: '测试 URL' }).click()
    await expect(page.getByText('API URL 与密钥连通正常')).toBeVisible()
    await createDialog.getByRole('button', { name: '测试模型' }).click()
    await expect(page.getByText(/模型连通正常/)).toBeVisible()

    await temperatureSwitch.click()
    await expect(temperatureSwitch).toHaveAttribute('aria-checked', 'true')
    await createDialog.getByLabel('Temperature').fill('0.7')
    await createDialog.locator('.ant-modal-footer .ant-btn-primary').click()

    const createdRow = rowFor(page, '新建端到端配置')
    await expect(createdRow).toBeVisible()
    await expect(createdRow).toContainText('当前使用')
    await expect(createdRow).toContainText('0.7')

    await page.getByRole('button', { name: '测试连接' }).click()
    await expect(page.getByText('当前激活模型连接正常')).toBeVisible()

    const existingRow = rowFor(page, '现有测试配置')
    await existingRow.getByRole('button').nth(0).click()
    await expect(page.getByText('能力检测通过并已激活')).toBeVisible()
    await expect(existingRow).toContainText('当前使用')

    await existingRow.getByRole('button').nth(0).click()
    await expect(page.getByText('已重新检测模型能力')).toBeVisible()

    await existingRow.getByRole('button').nth(1).click()
    const editDialog = page.getByRole('dialog', { name: '编辑 LLM 配置' })
    await editDialog.getByLabel('配置名称').fill('现有测试配置（已编辑）')
    await editDialog.locator('.ant-modal-footer .ant-btn-primary').click()
    await expect(rowFor(page, '现有测试配置（已编辑）')).toBeVisible()

    const editedRow = rowFor(page, '现有测试配置（已编辑）')
    await editedRow.getByRole('button').nth(2).click()
    const confirm = page.getByRole('tooltip').filter({ hasText: '确定删除此配置？' })
    await expect(confirm).toBeVisible()
    await confirm.locator('.ant-popconfirm-buttons .ant-btn-primary').click()
    await expect(rowFor(page, '现有测试配置（已编辑）')).toHaveCount(0)

    expect(browserErrors).toEqual([])
    expect(failedResponses).toEqual([])
  })
})
