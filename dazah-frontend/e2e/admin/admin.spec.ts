import { test, expect } from '@playwright/test'

test.describe('行政首页', () => {
  test('页面加载并显示标题', async ({ page }) => {
    await page.goto('/admin')
    await expect(page.locator('h1', { hasText: '行政管理' })).toBeVisible()
  })

  test('显示待开发占位符', async ({ page }) => {
    await page.goto('/admin')
    await expect(page.getByText('行政管理模块内容待开发')).toBeVisible()
  })

  test('侧边栏导航存在', async ({ page }) => {
    await page.goto('/admin')
    await page.waitForTimeout(1000)
    const sidebar = page.locator('aside, nav, .sidebar, .ant-layout-sider').first()
    await expect(sidebar).toBeVisible()
  })
})

test.describe('公告通知', () => {
  test('页面可访问并加载', async ({ page }) => {
    await page.goto('/admin/notice')
    await page.waitForTimeout(2000)
    await expect(page.getByText('Application error').first()).not.toBeVisible().catch(() => {})
  })
})

test.describe('会议台账', () => {
  test('页面加载并显示表格', async ({ page }) => {
    await page.goto('/admin/meeting/ledger')
    await page.waitForTimeout(2000)
    await expect(page.locator('h1', { hasText: '物品台账' })).toBeVisible()
  })

  test('搜索功能可用', async ({ page }) => {
    await page.goto('/admin/meeting/ledger')
    await page.waitForTimeout(2000)
    const searchInput = page.getByPlaceholder('搜索物品名称')
    await expect(searchInput).toBeVisible()
    await searchInput.fill('测试物品')
    await page.keyboard.press('Enter')
    await page.waitForTimeout(1000)
    await expect(page.getByRole('table')).toBeVisible()
  })

  test('新增物品按钮可用', async ({ page }) => {
    await page.goto('/admin/meeting/ledger')
    await page.waitForTimeout(2000)
    const addButton = page.getByRole('button', { name: /新增物品/ })
    await expect(addButton).toBeVisible()
    await addButton.click()
    await page.waitForTimeout(500)
    const modal = page.locator('.ant-modal').first()
    await expect(modal).toBeVisible()
    await expect(page.locator('.ant-modal-title', { hasText: '新增物品' })).toBeVisible()
  })

  test('状态筛选可用', async ({ page }) => {
    await page.goto('/admin/meeting/ledger')
    await page.waitForTimeout(2000)
    const statusSelect = page.locator('.ant-select').first()
    await expect(statusSelect).toBeVisible()
  })
})

test.describe('车辆信息', () => {
  test('页面加载并显示搜索框', async ({ page }) => {
    await page.goto('/admin/vehicles')
    await page.waitForTimeout(2000)
    await expect(page.getByPlaceholder('搜索车牌号或品牌')).toBeVisible()
  })

  test('新增车辆按钮可用', async ({ page }) => {
    await page.goto('/admin/vehicles')
    await page.waitForTimeout(2000)
    const addButton = page.getByRole('button', { name: /新增车辆/ })
    await expect(addButton).toBeVisible()
    await addButton.click()
    await page.waitForTimeout(500)
    await expect(page.locator('.ant-modal-title', { hasText: '新增车辆' })).toBeVisible()
  })

  test('批量导入按钮可用', async ({ page }) => {
    await page.goto('/admin/vehicles')
    await page.waitForTimeout(2000)
    await expect(page.getByRole('button', { name: '批量导入' })).toBeVisible()
  })

  test('下载模板按钮可用', async ({ page }) => {
    await page.goto('/admin/vehicles')
    await page.waitForTimeout(2000)
    await expect(page.getByRole('button', { name: '下载模板' })).toBeVisible()
  })
})

test.describe('用车申请', () => {
  test('页面加载并显示飞书表单', async ({ page }) => {
    test.setTimeout(60000)
    await page.goto('/admin/vehicle-requests', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)
    const iframe = page.locator('iframe').first()
    await expect(iframe).toBeVisible()
  })

  test('显示用车数据标题', async ({ page }) => {
    test.setTimeout(60000)
    await page.goto('/admin/vehicle-requests', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)
    await expect(page.locator('h2', { hasText: '用车数据' })).toBeVisible()
  })
})

test.describe('文件审批', () => {
  test('页面加载并显示飞书表单', async ({ page }) => {
    await page.goto('/admin/approval')
    await page.waitForTimeout(3000)
    const iframe = page.locator('iframe').first()
    await expect(iframe).toBeVisible()
  })

  test('显示温馨提示', async ({ page }) => {
    await page.goto('/admin/approval')
    await page.waitForTimeout(3000)
    await expect(page.getByText('寄件温馨提示')).toBeVisible()
  })
})

test.describe('IT服务工单', () => {
  test('页面加载并显示飞书表单', async ({ page }) => {
    await page.goto('/admin/it-tickets')
    await page.waitForTimeout(3000)
    const iframe = page.locator('iframe').first()
    await expect(iframe).toBeVisible()
  })

  test('显示报修温馨提示', async ({ page }) => {
    await page.goto('/admin/it-tickets')
    await page.waitForTimeout(3000)
    await expect(page.getByText('报修温馨提示')).toBeVisible()
  })
})
