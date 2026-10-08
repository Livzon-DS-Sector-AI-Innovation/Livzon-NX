import { expect, test } from '@playwright/test'

test('预告允许保存，维护保留表单并阻止新请求，恢复后可继续', async ({ page }) => {
  test.setTimeout(90_000)
  await page.context().addCookies([{ name: 'auth_token', value: 'e2e-admin', url: 'http://127.0.0.1:3200' }])
  let phase = 'announced'
  await page.route('**/__dazah_maintenance_status', route => phase === 'maintenance'
    ? route.fulfill({ status: 503, headers: { 'X-Dazah-Maintenance': '1' } })
    : phase === 'normal' ? route.fulfill({ status: 204 })
      : route.fulfill({ json: { phase, starts_at: Date.now() / 1000 + 180 } }))
  await page.goto('/settings?auth_token=e2e-admin')
  const llmTab = page.getByRole('link', { name: 'LLM 模型配置', exact: true })
  await expect(async () => {
    await llmTab.click()
    await expect(llmTab).toHaveAttribute('aria-current', 'page')
  }).toPass({ timeout: 15_000 })
  await page.getByRole('button', { name: '新建配置' }).click()
  const form = page.getByRole('dialog', { name: '新建 LLM 配置' })
  await form.getByLabel('配置名称').fill('维护前未保存的工作')
  await expect(page.getByText(/请完成当前工作并停止操作/).first()).toBeVisible()
  const originalUrl = page.url()
  phase = 'maintenance'
  const maintenance = page.getByRole('dialog', { name: '系统更新维护' })
  await expect(maintenance).toBeVisible({ timeout: 10_000 })
  await maintenance.getByRole('button', { name: '我知道了，保留当前页面' }).click()
  await expect(form.getByLabel('配置名称')).toHaveValue('维护前未保存的工作')
  let businessRequests = 0
  page.on('request', request => { if (request.method() === 'POST') businessRequests++ })
  await form.getByRole('button', { name: '测试 URL' }).click()
  await expect(maintenance).toBeVisible()
  expect(businessRequests).toBe(0)
  expect(page.url()).toBe(originalUrl)
  phase = 'normal'
  await expect(maintenance).toBeHidden({ timeout: 10_000 })
  await expect(page.getByRole('button', { name: '查询操作结果' })).toHaveCount(0)
  await form.getByRole('button', { name: '测试 URL' }).click()
  await expect(form.getByText('请输入 API 地址')).toBeVisible()
  await expect(form.getByLabel('配置名称')).toHaveValue('维护前未保存的工作')
})
