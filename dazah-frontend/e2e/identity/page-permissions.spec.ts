import { expect, test } from '@playwright/test'

test.describe('页面最小授权', () => {
  test('系统管理员无需逐页授权即可访问已发布模块并进行操作', async ({ context, page }) => {
    await context.addCookies([{ name: 'auth_token', value: 'admin-no-page-grants', url: 'http://127.0.0.1:3200' }])
    const response = await page.goto('/purchasing/supplier')
    expect(response?.status()).toBe(200)
    await expect(page.getByRole('heading', { name: '暂无页面访问权限' })).toHaveCount(0)
    await expect(page.locator('input[type="file"]')).toBeEnabled()
    for (const moduleName of ['生产管理', '质量管理', '人事管理', '仓储管理', '采购管理']) {
      await expect(page.getByRole('navigation').getByRole('link', { name: moduleName, exact: true })).toBeVisible()
    }
    await page.goto('/quality/deviations/ledger')
    await expect(page.getByRole('heading', { name: '偏差登记表' })).toBeVisible()
    await expect(page.getByRole('button', { name: /新建偏差$/ })).toBeVisible()
  })

  test('角色矩阵模块全部显示中文，保存先预览且冲突保留本地修改', async ({ context, page }) => {
    await context.addCookies([{ name: 'auth_token', value: 'matrix-admin', url: 'http://127.0.0.1:3200' }])
    await page.goto('/system/roles')
    await page.getByRole('button', { name: '页面权限', exact: true }).click()
    const drawer = page.getByRole('dialog')
    for (const name of ['生产管理', '设备管理', '能源管理', '安全管理', '研发管理', '注册管理', '质量管理', '行政管理', '人事管理', '仓储管理', '采购管理']) {
      await expect(drawer.getByText(name, { exact: true })).toBeVisible()
    }
    await drawer.getByText('生产管理', { exact: true }).click()
    await expect(drawer.getByRole('checkbox', { name: '作废生产批次', exact: true })).toBeVisible()
    await expect(drawer.getByRole('checkbox', { name: '作废生产批次', exact: true })).not.toBeChecked()
    await expect(drawer.getByRole('columnheader', { name: '数据范围', exact: true })).toHaveCount(0)
    await drawer.getByRole('checkbox', { name: '查询', exact: true }).check()
    await drawer.getByPlaceholder('填写角色授权调整原因').fill('调整页面只读范围')
    await drawer.getByRole('button', { name: '预览并保存基线' }).click()
    const confirmation = page.getByRole('dialog').filter({ hasText: '确认调整页面授权测试角色的页面权限' })
    await expect(confirmation.getByRole('columnheader', { name: '调整前', exact: true })).toBeVisible()
    await expect(confirmation.getByRole('columnheader', { name: '调整后', exact: true })).toBeVisible()
    await confirmation.getByRole('button', { name: '确认保存', exact: true }).click()
    await expect(page.getByText(/授权版本冲突.*本地修改已保留/)).toBeVisible()
    await expect(drawer.getByRole('checkbox', { name: '查询', exact: true })).toBeChecked()
  })

  for (const token of ['page-denied', 'page-access']) {
    test(`${token} 在服务端页面取数前拒绝`, async ({ context, page, request }) => {
      await context.addCookies([{ name: 'auth_token', value: token, url: 'http://127.0.0.1:3200' }])
      const response = await page.goto('/purchasing/supplier')
      expect(response?.status()).toBe(403)
      await expect(page.getByRole('heading', { name: '页面访问受限' })).toBeVisible()
      await expect(page.getByText(token === 'page-access'
        ? '可以访问此页面，但尚未获得查询数据权限。请联系管理员授权。'
        : '未获得当前菜单页面的访问权限。')).toBeVisible()
      const calls = await request.get(`http://127.0.0.1:4100/__test/page-requests?token=${token}`)
      expect((await calls.json()).count).toBe(0)
    })
  }

  test('查询权限可打开授权页面，但不能导入或直接访问同模块其他页面', async ({ context, page }) => {
    await context.addCookies([{ name: 'auth_token', value: 'page-query', url: 'http://127.0.0.1:3200' }])
    await page.goto('/purchasing')
    await expect(page).toHaveURL(/\/purchasing\/supplier$/)
    await expect(page.getByText('未获得批量导入权限，仅可查询供应商清单')).toBeVisible()
    await expect(page.locator('input[type="file"]')).toBeDisabled()
    const response = await page.goto('/purchasing/order')
    expect(response?.status()).toBe(403)
  })

  for (const token of ['ledger-denied', 'ledger-access']) {
    test(`${token} 在偏差详情服务端取数前拒绝`, async ({ context, page, request }) => {
      await context.addCookies([{ name: 'auth_token', value: token, url: 'http://127.0.0.1:3200' }])
      const response = await page.goto('/quality/deviations/00000000-0000-0000-0000-000000000001')
      expect(response?.status()).toBe(403)
      await expect(page.getByRole('heading', { name: '页面访问受限' })).toBeVisible()
      const calls = await request.get(`http://127.0.0.1:4100/__test/page-requests?token=${token}`)
      expect((await calls.json()).count).toBe(0)
    })
  }

  test('偏差台账只读入口不显示高风险操作且不能打开报告记录', async ({ context, page }) => {
    await context.addCookies([{ name: 'auth_token', value: 'ledger-query', url: 'http://127.0.0.1:3200' }])
    await page.goto('/quality/deviations/ledger')
    await expect(page.getByRole('heading', { name: '偏差登记表' })).toBeVisible()
    for (const name of ['新建偏差', '导入', '导出', '批量删除']) {
      await expect(page.getByRole('button', { name, exact: true })).toHaveCount(0)
    }
    await page.goto('/quality/deviations/new')
    await expect(page.getByText('尚未获得新增偏差记录的操作权限，请联系系统管理员。')).toBeVisible()
    await expect(page.getByRole('button', { name: '保存台账' })).toHaveCount(0)
    const response = await page.goto('/quality/deviations/records')
    expect(response?.status()).toBe(403)
  })

  test('新增偏差选择中文报告人并提交关联部门', async ({ context, page, request }) => {
    await context.addCookies([{ name: 'auth_token', value: 'ledger-create', url: 'http://127.0.0.1:3200' }])
    await page.goto('/quality/deviations/new')
    await page.getByLabel('报告人', { exact: true }).click()
    await page.getByText('王报告（质量部）', { exact: true }).click()
    await expect(page.getByLabel('部门', { exact: true })).toHaveValue('质量部')
    await page.getByLabel('产品名称/批号', { exact: true }).fill('产品A / 批次1')
    await page.getByLabel('偏差简要描述', { exact: true }).fill('浏览器新增偏差')
    await page.getByRole('button', { name: '保存台账' }).click()
    await expect(page).toHaveURL(/\/quality\/deviations\/ledger$/)
    const recorded = await request.get('http://127.0.0.1:4100/__test/ledger-write?token=ledger-create')
    expect(await recorded.json()).toMatchObject({ reporter_open_id: 'test-reporter', department: '质量部', description: '浏览器新增偏差', is_closed: false })
  })

  test('批量删除确认前不写入，成功后更新台账', async ({ context, page, request }) => {
    await context.addCookies([{ name: 'auth_token', value: 'ledger-delete', url: 'http://127.0.0.1:3200' }])
    await page.goto('/quality/deviations/ledger')
    await expect(page.getByText('PC-BATCH', { exact: true })).toBeVisible()
    await page.locator('thead input[type="checkbox"]').check()
    await page.getByRole('button', { name: '批量删除', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText(/本批不会删除任何记录/)).toBeVisible()
    const before = await request.get('http://127.0.0.1:4100/__test/ledger-write?token=ledger-delete')
    expect(await before.json()).toBeNull()
    await dialog.getByRole('button', { name: /^确\s*认$/ }).click()
    await expect(page.getByText('PC-BATCH', { exact: true })).toHaveCount(0)
    const recorded = await request.get('http://127.0.0.1:4100/__test/ledger-write?token=ledger-delete')
    expect(await recorded.json()).toEqual({ ids: ['00000000-0000-0000-0000-000000000011'] })
  })
})
