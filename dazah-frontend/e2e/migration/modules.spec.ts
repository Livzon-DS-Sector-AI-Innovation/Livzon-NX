import { expect, test } from '@playwright/test'

const migratedPages = [
  // 质量：迁移入口、文件目录和三类检验子模块
  '/quality',
  '/quality/documents',
  '/quality/inspection/items',
  '/quality/inspection/instruments',
  '/quality/inspection/finished',
  '/quality/capas',
  '/quality/oos-oot',
  // 注册：项目、证书、费用、知识库和验证审计
  '/registration',
  '/registration/project',
  '/registration/certificate-management',
  '/registration/fees',
  '/registration/knowledge',
  '/registration/reference-standard',
  '/registration/supplementary-reply',
  '/registration/validation-audit',
  // 仓储：迁移入口、飞书配置、物料、五金、产品和分析
  '/warehouse',
  '/warehouse/feishu-config',
  '/warehouse/materials/dashboard',
  '/warehouse/hardware/dashboard',
  '/warehouse/product',
  '/warehouse/ai-analysis',
  // 系统权限五页
  '/system/roles',
  '/system/user-roles',
  '/system/menus',
  '/system/dept-roles',
  '/system/permission-verification',
] as const

for (const path of migratedPages) {
  test(`迁移页面 ${path} 可加载且无意外 API 5xx/4xx`, async ({ page }) => {
    const failedApiResponses: string[] = []
    const pageErrors: string[] = []
    page.on('pageerror', (error) => pageErrors.push(error.message))
    page.on('response', (response) => {
      const url = response.url()
      if (url.includes('/api/') && [404, 405, 422, 500, 502, 503].includes(response.status())) {
        failedApiResponses.push(`${response.status()} ${url}`)
      }
    })

    const response = await page.goto(path, { waitUntil: 'domcontentloaded' })
    expect(response?.status(), `${path} 页面响应状态`).toBeLessThan(400)
    await expect(page.locator('body')).toBeVisible()
    await expect(page.getByText('Application error', { exact: false })).toHaveCount(0)
    await page.waitForTimeout(1200)
    expect(failedApiResponses, `${path} 存在失败 API 请求`).toEqual([])
    expect(pageErrors, `${path} 存在未处理前端异常`).toEqual([])
  })
}
