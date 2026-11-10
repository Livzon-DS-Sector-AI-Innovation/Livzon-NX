import { expect, test } from '@playwright/test'
import { openCriticalBusinessSession } from '../critical-business-session'

test('设备台账只列出授权车间，切换和刷新保持当前台账及记录', async ({ context, page, baseURL }) => {
  await openCriticalBusinessSession(context, baseURL, 'equipment-reader')
  await page.goto('/equipment?workshop=201-1')
  await expect(page).toHaveURL(/workshop=201-1&module=assets$/)
  await expect(page.getByRole('row', { name: /一车间测试真空泵/ })).toBeVisible()
  await expect(page.getByTitle('切换到 设备测试一车间')).toBeVisible()
  await expect(page.getByTitle('切换到 设备受限车间')).toHaveCount(0)
  await page.getByTitle('切换到 设备测试二车间').click()
  await expect(page).toHaveURL(/workshop=201-2&module=assets$/)
  await expect(page.getByRole('row', { name: /二车间测试反应釜/ })).toBeVisible()
  await expect(page.getByRole('row', { name: /一车间测试真空泵/ })).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('row', { name: /二车间测试反应釜/ })).toBeVisible()
})

test('手动访问无权车间时显示拒绝状态，不显示设备记录', async ({ context, page, baseURL }) => {
  await openCriticalBusinessSession(context, baseURL, 'equipment-reader')
  await page.goto('/equipment?workshop=203&module=assets')
  await expect(page.getByText('没有执行此操作的权限，请联系管理员', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: '返回平台' })).toBeVisible()
  await expect(page.getByRole('table')).toHaveCount(0)
})

test('设备统计接口暂不可用时台账仍显示该车间的设备', async ({ context, page, baseURL }) => {
  await openCriticalBusinessSession(context, baseURL, 'equipment-partial')
  await page.goto('/equipment?workshop=201-1&module=assets')
  await expect(page.getByRole('row', { name: /E2E-201-1.*一车间测试真空泵/ })).toBeVisible()
  await expect(page.getByRole('row', { name: /二车间测试反应釜/ })).toHaveCount(0)
})
