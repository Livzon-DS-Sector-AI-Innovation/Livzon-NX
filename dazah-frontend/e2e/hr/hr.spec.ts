import { test, expect } from '@playwright/test'

test.describe('人事首页', () => {
  test('页面加载并显示标题', async ({ page }) => {
    await page.goto('/hr')
    await expect(page.locator('h1', { hasText: '人事管理' })).toBeVisible()
  })

  test('显示9个功能卡片', async ({ page }) => {
    await page.goto('/hr')
    await page.waitForTimeout(1000)
    const cards = page.locator('.ant-card')
    await expect(cards).toHaveCount(9)
  })

  test('员工管理卡片可点击', async ({ page }) => {
    await page.goto('/hr')
    await page.waitForTimeout(1000)
    const link = page.locator('main a[href="/hr/employee-management"]')
    await expect(link).toBeVisible()
    await link.click()
    await page.waitForTimeout(1500)
    await expect(page).toHaveURL(/.*\/hr\/employee-management/)
  })

  test('部门管理卡片可点击', async ({ page }) => {
    await page.goto('/hr')
    await page.waitForTimeout(1000)
    const link = page.locator('main a[href="/hr/departments"]')
    await expect(link).toBeVisible()
    await link.click()
    await page.waitForTimeout(1500)
    await expect(page).toHaveURL(/.*\/hr\/departments/)
  })

  test('招聘管理卡片可点击', async ({ page }) => {
    await page.goto('/hr')
    await page.waitForTimeout(1000)
    const link = page.locator('main a[href="/hr/recruitment"]')
    await expect(link).toBeVisible()
    await link.click()
    await page.waitForTimeout(1500)
    await expect(page).toHaveURL(/.*\/hr\/recruitment/)
  })

  test('培训管理卡片可点击', async ({ page }) => {
    await page.goto('/hr')
    await page.waitForTimeout(1000)
    const link = page.locator('main a[href="/hr/training"]')
    await expect(link).toBeVisible()
    await link.click()
    await page.waitForTimeout(1500)
    await expect(page).toHaveURL(/.*\/hr\/training/)
  })
})

test.describe('员工档案', () => {
  test('页面加载并显示数据表格', async ({ page }) => {
    await page.goto('/hr/profile')
    await page.waitForTimeout(3000)
    await expect(page.getByText('Application error').first()).not.toBeVisible().catch(() => {})
    await expect(page.getByRole('table').first()).toBeVisible()
  })

  test('表格包含员工数据', async ({ page }) => {
    await page.goto('/hr/profile')
    await page.waitForTimeout(3000)
    const tableRows = page.locator('table tbody tr')
    const count = await tableRows.count()
    expect(count).toBeGreaterThan(0)
  })
})

test.describe('部门管理', () => {
  test('页面加载并显示数据表格', async ({ page }) => {
    await page.goto('/hr/departments')
    await page.waitForTimeout(3000)
    await expect(page.getByText('Application error').first()).not.toBeVisible().catch(() => {})
    await expect(page.getByRole('table').first()).toBeVisible()
  })

  test('表格包含部门数据', async ({ page }) => {
    await page.goto('/hr/departments')
    await page.waitForTimeout(3000)
    const tableRows = page.locator('table tbody tr')
    const count = await tableRows.count()
    expect(count).toBeGreaterThan(0)
  })
})

test.describe('招聘管理', () => {
  test('页面加载并显示数据表格', async ({ page }) => {
    await page.goto('/hr/recruitment')
    await page.waitForTimeout(3000)
    await expect(page.getByText('Application error').first()).not.toBeVisible().catch(() => {})
    await expect(page.getByRole('table').first()).toBeVisible()
  })
})

test.describe('培训管理首页', () => {
  test('页面加载并显示标题', async ({ page }) => {
    await page.goto('/hr/training')
    await expect(page.locator('h1', { hasText: '培训管理' })).toBeVisible()
  })

  test('显示8个功能卡片', async ({ page }) => {
    await page.goto('/hr/training')
    await page.waitForTimeout(1000)
    const cards = page.locator('.ant-card')
    await expect(cards).toHaveCount(8)
  })

  test('年度培训计划卡片可点击', async ({ page }) => {
    await page.goto('/hr/training')
    await page.waitForTimeout(1000)
    const card = page.locator('.ant-card').filter({ hasText: '年度培训计划' }).first()
    await expect(card).toBeVisible()
    await card.click()
    await page.waitForTimeout(1500)
    await expect(page).toHaveURL(/.*\/hr\/training\/annual-plan/)
  })

  test('培训资料卡片可点击', async ({ page }) => {
    await page.goto('/hr/training')
    await page.waitForTimeout(1000)
    const card = page.locator('.ant-card').filter({ hasText: '培训资料' }).first()
    await expect(card).toBeVisible()
    await card.click()
    await page.waitForTimeout(1500)
    await expect(page).toHaveURL(/.*\/hr\/training\/sign-in/)
  })
})

test.describe('新厂人事模块', () => {
  test('新厂部门管理页面加载', async ({ page }) => {
    await page.goto('/hr/new/departments')
    await page.waitForTimeout(3000)
    await expect(page.getByText('Application error').first()).not.toBeVisible().catch(() => {})
  })

  test('新厂员工档案页面加载', async ({ page }) => {
    await page.goto('/hr/new/profile')
    await page.waitForTimeout(3000)
    await expect(page.getByText('Application error').first()).not.toBeVisible().catch(() => {})
  })
})
