import { expect, test } from '@playwright/test'

const pagePath = '/hr/training/annual-plan'
const permissionMessage = '您没有年度培训计划的批量导入权限，请联系管理员'
const forbiddenMessage = '没有执行此操作的权限，请联系管理员'

for (const appearance of ['light', 'dark']) {
  test.describe(`年度培训计划导入 · ${appearance}`, () => {
    test.beforeEach(async ({ page }) => {
      await page.addInitScript(mode => localStorage.setItem('dazah-appearance', mode), appearance)
    })

    test('已知缺少批量导入权限时禁用入口并说明原因', async ({ context, page, baseURL }) => {
      await context.addCookies([{ name: 'auth_token', value: 'annual-plan-read', url: baseURL! }])
      await page.goto(pagePath)
      await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
      await expect(page.getByRole('button', { name: '导入文档' })).toBeDisabled()
      await page.getByRole('group', { name: permissionMessage }).focus()
      await expect(page.getByRole('tooltip')).toHaveText(permissionMessage)
    })

    test('服务端撤回导入授权时保留文档并显示业务提示', async ({ context, page, baseURL }) => {
      await context.addCookies([{ name: 'auth_token', value: 'annual-plan-import-revoked', url: baseURL! }])
      await page.goto(pagePath)
      await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
      await page.getByRole('button', { name: '导入文档' }).click()
      const dialog = page.getByRole('dialog', { name: '导入年度培训计划' })
      const year = `${new Date().getFullYear() + 1}年`
      const selectedYear = dialog.getByTitle(year, { exact: true })
      await dialog.getByRole('combobox').click()
      await page.locator('.ant-select-item-option').getByText(year, { exact: true }).click()
      await expect(selectedYear).toBeVisible()
      await dialog.locator('input[type="file"]').setInputFiles({
        name: '年度培训计划.docx',
        mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        buffer: Buffer.from('mock document'),
      })

      const response = page.waitForResponse(res => res.request().method() === 'POST'
        && new URL(res.url()).pathname === pagePath && Boolean(res.request().headers()['next-action']))
      await dialog.getByRole('button', { name: /确\s*定/ }).click()
      expect((await response).status()).toBe(200)
      await expect(page.locator('.ant-message').getByText(forbiddenMessage)).toBeVisible()
      await expect(dialog.getByText('年度培训计划.docx', { exact: true })).toBeVisible()
      await expect(selectedYear).toBeVisible()
      await expect(page.getByText(/Minified React|Server Components render/)).toHaveCount(0)
    })
  })
}

test('新建冲突保留表单，删除被拒时保留原计划', async ({ context, page, baseURL }) => {
  await context.addCookies([{ name: 'auth_token', value: 'annual-plan-writes', url: baseURL! }])
  await page.goto(pagePath)
  await page.getByRole('button', { name: '新建年度计划' }).click()
  const form = page.getByRole('dialog', { name: '新建年度培训计划' })
  await form.getByRole('button', { name: /创\s*建/ }).click()
  await expect(page.locator('.ant-message').getByText('该部门本年度的培训计划已存在')).toBeVisible()
  await expect(form).toBeVisible()
  await form.getByRole('button', { name: /取\s*消/ }).click()
  await page.getByText('删除', { exact: true }).click()
  await page.getByRole('button', { name: /确\s*定/ }).click()
  await expect(page.locator('.ant-message').getByText(forbiddenMessage)).toBeVisible()
  await expect(page.getByRole('link', { name: '查看', exact: true })).toBeVisible()
})
