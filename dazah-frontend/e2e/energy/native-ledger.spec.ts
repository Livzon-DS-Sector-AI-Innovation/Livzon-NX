import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/__dazah_maintenance_status', route => route.fulfill({ json: { phase: 'normal' } }))
  page.on('dialog', dialog => dialog.accept())
})

test('direct original-sheet entry preserves failures and updates readings without assignments', async ({ context, page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await context.addCookies([{ name: 'auth_token', value: `energy-${randomUUID()}`, url: 'http://127.0.0.1:3200' }])
  await page.goto('/energy/entry?date=2026-07-02&dataset=饮用水码&source=feishu', { waitUntil: 'domcontentloaded' })
  const water = page.getByRole('spinbutton', { name: '101车间水表本次填写' })
  await expect(water).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('button', { name: '生成该日清单' })).toHaveCount(0)
  await expect(water).toHaveValue('')
  await water.fill('999')
  await page.getByRole('button', { name: '提交生效', exact: true }).click()
  const confirmation = page.getByRole('dialog', { name: '确认保存原始数据' })
  await confirmation.getByRole('button', { name: /确\s*定/ }).click()
  await expect(page.getByText('模拟能源服务暂不可用，输入已保留').first()).toBeVisible()
  await expect(water).toHaveValue(/^999(?:\.0+)?$/)
  await confirmation.getByRole('button', { name: /取\s*消/ }).click()
  await water.fill('110')
  await page.getByRole('button', { name: '保存草稿', exact: true }).click()
  await expect(page.getByText('草稿已保存', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '提交生效', exact: true }).click()
  await expect(confirmation).toContainText('本次保存 1 项')
  await confirmation.getByRole('button', { name: /确\s*定/ }).click()
  await expect(page.getByText('原始数据已保存，关联台账已更新', { exact: true })).toBeVisible()
  const result = await page.request.get('/api/v1/energy/e2e-state')
  expect((await result.json()).data.task.items[0].value).toBe('110')
  await page.goto('/energy/reports?year=2026&month=7&dataset=饮用水量')
  await expect(page.getByRole('heading', { name: '能源台账', exact: true })).toBeVisible()
  await expect(page.getByText('10', { exact: true })).toBeVisible()
  await expect(page.getByText('大罐数量')).toHaveCount(0)
  expect(errors).toEqual([])
})
