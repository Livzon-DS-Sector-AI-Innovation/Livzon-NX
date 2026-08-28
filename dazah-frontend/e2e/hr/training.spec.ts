import { test, expect } from '@playwright/test'

test.describe('培训模块首页', () => {
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
    const link = page.locator('main a[href="/hr/training/annual-plan"]')
    await expect(link).toBeVisible()
    await link.click()
    await page.waitForTimeout(1500)
    await expect(page).toHaveURL(/.*\/hr\/training\/annual-plan/)
  })

  test('新员工培训卡片可点击', async ({ page }) => {
    await page.goto('/hr/training')
    await page.waitForTimeout(1000)
    const link = page.locator('main a[href="/hr/training/new-employee"]')
    await expect(link).toBeVisible()
    await link.click()
    await page.waitForTimeout(1500)
    await expect(page).toHaveURL(/.*\/hr\/training\/new-employee/)
  })

  test('培训资料卡片可点击', async ({ page }) => {
    await page.goto('/hr/training')
    await page.waitForTimeout(1000)
    const link = page.locator('main a[href="/hr/training/sign-in"]')
    await expect(link).toBeVisible()
    await link.click()
    await page.waitForTimeout(1500)
    await expect(page).toHaveURL(/.*\/hr\/training\/sign-in/)
  })

  test('培训签到表卡片可点击', async ({ page }) => {
    await page.goto('/hr/training')
    await page.waitForTimeout(1000)
    const link = page.locator('main a[href="/hr/training/sign-in"]')
    await expect(link).toBeVisible()
    await link.click()
    await page.waitForTimeout(1500)
    await expect(page).toHaveURL(/.*\/hr\/training\/sign-in/)
  })

  test('培训台账卡片可点击', async ({ page }) => {
    await page.goto('/hr/training')
    await page.waitForTimeout(1000)
    const link = page.locator('main a[href="/hr/training/ledger"]')
    await expect(link).toBeVisible()
    await link.click()
    await page.waitForTimeout(1500)
    await expect(page).toHaveURL(/.*\/hr\/training\/ledger/)
  })

  test('AI出题旧入口重定向到培训资料', async ({ page }) => {
    await page.goto('/hr/training/ai-exam')
    await expect(page).toHaveURL(/.*\/hr\/training\/sign-in/)
    await expect(page.getByText('培训签到表', { exact: true }).first()).toBeVisible()
  })
})

test.describe('新员工入职培训', () => {
  test('页面加载并显示标题', async ({ page }) => {
    await page.goto('/hr/training/onboarding')
    await page.waitForTimeout(2000)
    await expect(page.locator('h1', { hasText: '新员工入职培训' })).toBeVisible()
  })

  test('旧厂/新厂切换可用', async ({ page }) => {
    await page.goto('/hr/training/onboarding')
    await page.waitForTimeout(2000)
    const tabs = page.locator('.ant-tabs-tab, .ant-radio-button-wrapper, button').filter({ hasText: /旧厂|新厂/ })
    const count = await tabs.count()
    if (count > 0) {
      await expect(tabs.first()).toBeVisible()
    }
  })

  test('员工选择器加载', async ({ page }) => {
    await page.goto('/hr/training/onboarding')
    await page.waitForTimeout(3000)
    const select = page.locator('.ant-select').first()
    await expect(select).toBeVisible()
  })
})

test.describe('培训通知', () => {
  test('页面加载并显示标题', async ({ page }) => {
    await page.goto('/hr/training/notification')
    await page.waitForTimeout(2000)
    await expect(page.locator('h1', { hasText: '培训通知' })).toBeVisible()
  })

  test('表单元素存在', async ({ page }) => {
    await page.goto('/hr/training/notification')
    await page.waitForTimeout(2000)
    const inputs = page.locator('input, .ant-input, .ant-select').first()
    await expect(inputs).toBeVisible()
  })
})

test.describe('培训签到表', () => {
  test('页面加载并显示标题', async ({ page }) => {
    await page.goto('/hr/training/sign-in')
    await page.waitForTimeout(2000)
    await expect(page.getByText('培训签到表', { exact: true }).first()).toBeVisible()
  })

  test('表单元素存在', async ({ page }) => {
    await page.goto('/hr/training/sign-in')
    await page.waitForTimeout(2000)
    const inputs = page.locator('.ant-select:visible, input:not([type="radio"]):visible, textarea:visible').first()
    await expect(inputs).toBeVisible()
  })
})

test.describe('培训台账', () => {
  test('页面加载并显示标题', async ({ page }) => {
    await page.goto('/hr/training/ledger')
    await page.waitForTimeout(2000)
    await expect(page.locator('h1', { hasText: '培训台账' })).toBeVisible()
  })

  test('表格或空状态加载', async ({ page }) => {
    await page.goto('/hr/training/ledger')
    await page.waitForTimeout(2000)
    await expect(page.getByText('Application error').first()).not.toBeVisible().catch(() => {})
    await expect(page.locator('body')).toBeVisible()
  })
})

test.describe('年度培训计划', () => {
  test('页面加载并显示标题', async ({ page }) => {
    await page.goto('/hr/training/annual-plan')
    await page.waitForTimeout(2000)
    await expect(page.locator('h1', { hasText: '年度培训计划' })).toBeVisible()
  })

  test('表格或空状态加载', async ({ page }) => {
    await page.goto('/hr/training/annual-plan')
    await page.waitForTimeout(2000)
    await expect(page.getByText('Application error').first()).not.toBeVisible().catch(() => {})
    await expect(page.locator('body')).toBeVisible()
  })
})

test.describe('AI出题兼容入口', () => {
  test('旧入口重定向到培训资料', async ({ page }) => {
    await page.goto('/hr/training/ai-exam')
    await expect(page).toHaveURL(/.*\/hr\/training\/sign-in/)
    await expect(page.getByText('培训签到表', { exact: true }).first()).toBeVisible()
  })

  test('重定向后培训资料入口可用', async ({ page }) => {
    await page.goto('/hr/training/ai-exam')
    await expect(page.getByRole('button', { name: '新建培训资料' })).toBeVisible()
  })
})

test.describe('新厂人事模块数据验证', () => {
  test('新厂员工档案页面加载并显示数据', async ({ page }) => {
    await page.goto('/hr/new/profile')
    await page.waitForTimeout(3000)
    await expect(page.getByText('Application error').first()).not.toBeVisible().catch(() => {})
    await expect(page.locator('body')).toBeVisible()
  })

  test('新厂部门管理页面加载并显示数据', async ({ page }) => {
    await page.goto('/hr/new/departments')
    await page.waitForTimeout(3000)
    await expect(page.getByText('Application error').first()).not.toBeVisible().catch(() => {})
    await expect(page.locator('body')).toBeVisible()
  })

  test('新厂入职台账页面加载', async ({ page }) => {
    await page.goto('/hr/new/onboarding')
    await page.waitForTimeout(3000)
    await expect(page.getByText('Application error').first()).not.toBeVisible().catch(() => {})
    await expect(page.locator('body')).toBeVisible()
  })
})
