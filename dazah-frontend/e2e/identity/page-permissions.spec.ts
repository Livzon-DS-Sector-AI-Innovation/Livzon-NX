import { expect, test } from '@playwright/test'

test.describe('页面最小授权', () => {
  for (const { appearance, width } of [{ appearance: 'light', width: 1280 }, { appearance: 'dark', width: 390 }]) {
    test(`角色映射跨搜索保留用户并展示分配确认 ${appearance}`, async ({ context, page }) => {
      await page.setViewportSize({ width, height: 900 })
      await context.addCookies([{ name: 'auth_token', value: 'effective-admin', url: 'http://127.0.0.1:3200' }])
      await page.addInitScript((mode) => localStorage.setItem('dazah-appearance', mode), appearance)
      await page.route(/\/api\/v1\/identity\/admin\/users\?/, async (route) => {
        const keyword = new URL(route.request().url()).searchParams.get('keyword')
        await route.fulfill({ json: { code: 200, data: {
          total: 1, items: [{ id: keyword || 'default-user', name: keyword || '默认列表用户', roles: [] }],
        } } })
      })

      await page.goto('/settings?tab=permissions')
      await page.getByRole('button', { name: '角色映射', exact: true }).click()
      await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
      const mapping = page.getByRole('region', { name: '搜索用户批量分配角色' })
      await expect(mapping.getByRole('row', { name: /默认列表用户/ })).toBeVisible()
      const search = mapping.getByRole('searchbox', { name: '搜索用户', exact: true })
      for (const name of ['张三', '李四']) {
        await search.fill(name)
        await search.press('Enter')
        await mapping.getByRole('row', { name: new RegExp(name) }).getByRole('checkbox').check()
      }
      await search.fill('')
      await search.press('Enter')
      await expect(mapping.getByRole('row', { name: /默认列表用户/ })).toBeVisible()
      const selectedCount = mapping.getByText(/已选 2 位用户/)
      await expect(selectedCount).toBeVisible()
      const submit = mapping.getByRole('button', { name: '批量分配角色', exact: true })
      await expect(submit).toBeDisabled()
      const commonRole = mapping.getByRole('combobox', { name: '共同角色' })
      const firstUserRole = mapping.getByRole('combobox', { name: '张三的待分配角色' })
      const secondUserRole = mapping.getByRole('combobox', { name: '李四的待分配角色' })
      const firstUserRow = mapping.getByRole('row', { name: /默认列表用户/ })
      const rowPosition = await firstUserRow.boundingBox()
      for (const control of [selectedCount, submit, commonRole, firstUserRole, secondUserRole]) {
        const position = await control.boundingBox()
        expect(position && rowPosition && position.y >= rowPosition.y + rowPosition.height).toBe(true)
      }
      await firstUserRole.fill('员工查看')
      await page.getByText('员工查看角色', { exact: true }).click()
      await page.keyboard.press('Escape')
      await expect(mapping.getByRole('row', { name: /张三/ })).toContainText('员工查看角色')
      await expect(mapping.getByRole('row', { name: /李四/ })).toContainText('选择角色')
      await expect(submit).toBeDisabled()
      await commonRole.fill('员工查看')
      await expect(commonRole).toHaveAttribute('aria-expanded', 'true')
      await commonRole.press('Enter')
      await page.keyboard.press('Escape')
      await mapping.getByRole('button', { name: '统一设置待分配角色' }).click()
      await submit.click()
      const confirmation = page.getByRole('dialog')
      await expect(confirmation.getByText('张三：员工查看角色')).toBeVisible()
      await expect(confirmation.getByText('李四：员工查看角色')).toBeVisible()
      await expect(confirmation.getByRole('button', { name: '确认分配' })).toBeInViewport()
      await confirmation.getByRole('button', { name: /^取\s*消$/ }).click()
      await expect(submit).toBeEnabled()
      await page.getByRole('tab', { name: '按部门查询' }).click()
      await expect(page.getByRole('button', { name: '查询部门用户' })).toBeVisible()
      await page.getByRole('tab', { name: '搜索用户' }).click()
      await expect(mapping.getByText(/已选 2 位用户/)).toBeVisible()
    })
  }

  for (const appearance of ['light', 'dark']) {
    test(`系统设置的用户角色可检索首批名单外的账号 ${appearance}`, async ({ context, page }) => {
      await context.addCookies([{ name: 'auth_token', value: 'effective-admin', url: 'http://127.0.0.1:3200' }])
      await page.addInitScript((mode) => localStorage.setItem('dazah-appearance', mode), appearance)
      await page.route(/\/api\/v1\/identity\/admin\/users\?/, async (route) => {
        const params = new URL(route.request().url()).searchParams
        const match = params.get('keyword') === 'late-account@example.test'
        await route.fulfill({ json: { code: 200, data: {
          total: match ? 1 : 501,
          items: [{ id: match ? 'user-501' : 'user-1', name: match ? '后页用户' : '首批用户', roles: [] }],
        } } })
      })
      await page.goto('/settings?tab=permissions')
      await page.getByRole('button', { name: '用户角色', exact: true }).click()
      await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
      await expect(page.getByRole('row', { name: /首批用户/ })).toBeVisible()

      const search = page.getByPlaceholder('按姓名、部门、账号、邮箱、手机号或工号搜索')
      await search.fill('late-account@example.test')
      const request = page.waitForRequest((item) => item.url().includes('/identity/admin/users?')
        && new URL(item.url()).searchParams.has('keyword'))
      await search.press('Enter')
      const params = new URL((await request).url()).searchParams
      expect(Object.fromEntries(params)).toEqual({ keyword: 'late-account@example.test', offset: '0', limit: '20' })
      const matchedRow = page.getByRole('row', { name: /后页用户/ })
      await expect(matchedRow).toBeVisible()
      await expect(matchedRow.getByRole('button', { name: '分配角色' })).toBeEnabled()
      await expect(page.getByRole('row', { name: /首批用户/ })).toHaveCount(0)
    })
  }

  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    test(`有效权限只读展示自动模块入口 ${viewport.width}`, async ({ context, page }, testInfo) => {
      await page.setViewportSize(viewport)
      await context.addCookies([{ name: 'auth_token', value: 'effective-admin', url: 'http://127.0.0.1:3200' }])
      await page.goto('/system/user-roles')
      await expect(page.getByText('为用户分配角色，模块入口随有效页面权限自动生效。', { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: /模块访问$/ })).toHaveCount(0)
      await page.getByRole('button', { name: /有效权限$/ }).click()
      const drawer = page.getByRole('dialog')
      await expect(drawer.getByText('已开通 1 个模块', { exact: true })).toBeVisible()
      const hrRow = drawer.getByRole('row').filter({ hasText: '人事管理' })
      await expect(hrRow.getByText('自动开通', { exact: true })).toBeVisible()
      await hrRow.getByRole('button', { name: '展开行' }).click()
      await expect(drawer.getByText('员工查看角色', { exact: true })).toBeVisible()
      const pageRow = await drawer.getByRole('row').filter({ hasText: '员工管理' }).last().boundingBox()
      const nextModuleRow = await drawer.getByRole('row').filter({ hasText: '仓储管理' }).boundingBox()
      expect(pageRow && nextModuleRow && pageRow.y + pageRow.height <= nextModuleRow.y).toBe(true)
      await expect(drawer.getByRole('checkbox')).toHaveCount(0)
      await expect(drawer.getByRole('button', { name: /保存/ })).toHaveCount(0)
      await expect(drawer).toHaveCSS('width', viewport.width === 390 ? '390px' : '820px')
      await page.screenshot({ path: testInfo.outputPath('effective-permissions.png'), fullPage: true })
    })
  }

  test('系统管理员无需逐页授权即可访问已发布模块并进行操作', async ({ context, page }) => {
    await context.addCookies([{ name: 'auth_token', value: 'admin-no-page-grants', url: 'http://127.0.0.1:3200' }])
    const response = await page.goto('/purchasing/supplier')
    expect(response?.status()).toBe(200)
    await expect(page.getByRole('heading', { name: '暂无页面访问权限' })).toHaveCount(0)
    await expect(page.locator('input[type="file"]')).toBeEnabled()
    for (const moduleName of ['生产管理', '质量管理', '人事管理', '仓储管理', '采购管理']) {
      await expect(page.getByRole('navigation', { name: '业务模块' }).getByRole('link', { name: moduleName, exact: true })).toBeVisible()
    }
    await page.goto('/quality/deviations/ledger')
    await expect(page.getByRole('heading', { name: '偏差台账' })).toBeVisible()
    await expect(page.getByRole('button', { name: /新增台账$/ })).toBeVisible()
  })

  for (const appearance of ['light', 'dark']) {
    test(`页面权限工作台先预览且冲突保留本地修改 ${appearance}`, async ({ context, page }) => {
      await page.setViewportSize({ width: 1280, height: 900 })
      await page.emulateMedia({ reducedMotion: appearance === 'dark' ? 'reduce' : 'no-preference' })
      await context.addCookies([{ name: 'auth_token', value: 'matrix-admin', url: 'http://127.0.0.1:3200' }])
      await page.addInitScript((mode) => localStorage.setItem('dazah-appearance', mode), appearance)
      await page.goto('/system/roles')
      await page.evaluate(() => { document.documentElement.dataset.permissionNavigation = 'same-document' })
      const initialPermissionReads: string[] = []
      page.on('request', (request) => {
        if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/role-matrix/page-permissions')) {
          initialPermissionReads.push(request.url())
        }
      })
      const navigationProgress = page.getByRole('status', { name: /^正在(?:打开|加载)页面权限$/ })
      await Promise.all([
        expect(navigationProgress.first()).toBeVisible(),
        page.getByRole('link', { name: '页面权限', exact: true }).click(),
      ])
      await expect(page).toHaveURL(/roles\/role-matrix\/page-permissions$/)
      await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
      await expect(page.locator('html')).toHaveAttribute('data-permission-navigation', 'same-document')
      const heading = page.getByRole('heading', { name: '页面权限基线配置' })
      const save = page.getByRole('button', { name: '保存', exact: true })
      await expect(heading).toBeVisible()
      await expect(heading.locator('xpath=ancestor::header[1]/..')).toHaveCSS('animation-duration', appearance === 'dark' ? '0s' : '0.17s')
      await expect(save).toBeEnabled()
      expect(initialPermissionReads).toEqual([])
      await expect(page.getByRole('dialog')).toHaveCount(0)
      const modules = page.getByRole('navigation', { name: '业务模块', exact: true })
      for (const name of ['生产管理', '设备管理', '能源管理', '安全管理', '研发管理', '注册管理', '质量管理', '行政管理', '人事管理', '仓储管理', '采购管理']) {
        await expect(modules.getByRole('button', { name, exact: true })).toBeVisible()
      }
      await modules.getByRole('button', { name: '质量管理', exact: true }).click()
      await expect(page.getByRole('region', { name: '页面权限详情：偏差记录' })).toBeVisible()
      const tree = page.getByRole('navigation', { name: '页面', exact: true })
      await expect(tree.getByRole('button', { name: '偏差调查', exact: true })).toBeVisible()
      await expect(tree.getByRole('button', { name: '检验结果', exact: true })).toHaveCount(0)
      const summary = page.getByRole('button', { name: '折叠偏差记录配置摘要', exact: true })
      await expect(summary).toHaveAttribute('aria-expanded', 'true')
      await summary.click()
      await expect(page.getByRole('button', { name: '展开偏差记录配置摘要', exact: true })).toHaveAttribute('aria-expanded', 'false')
      await expect(page.getByRole('region', { name: '页面权限详情：偏差记录' })).toBeVisible()
      await page.keyboard.press('Control+k')
      await expect(page.getByRole('textbox', { name: '搜索角色页面权限' })).toBeFocused()
      await modules.getByRole('button', { name: '生产管理', exact: true }).click()
      const detail = page.getByRole('region', { name: '页面权限详情：生产批次' })
      const risk = detail.getByRole('checkbox', { name: '作废生产批次', exact: true })
      await expect(risk).toBeDisabled()
      const list = page.locator('#role-page-permission-list').locator('..')
      const permissionTier = list.getByRole('radiogroup', { name: '生产批次权限档位' })
      await expect(permissionTier.getByRole('radio', { name: '无权限' })).toBeChecked()
      await permissionTier.getByText('普通操作', { exact: true }).click()
      await expect(risk).toBeEnabled()
      await expect(risk).not.toBeChecked()
      await risk.check()
      await permissionTier.getByText('可查看', { exact: true }).click()
      await expect(detail.getByRole('radio', { name: '可查看' })).toBeChecked()
      await expect(risk).not.toBeChecked()
      await expect(risk).toBeDisabled()
      await page.getByPlaceholder('填写角色授权调整原因').fill('调整页面只读范围')
      await save.click()
      const confirmation = page.getByRole('dialog').filter({ hasText: '确认调整页面授权测试角色的页面权限' })
      await expect(confirmation.getByRole('columnheader', { name: '调整前', exact: true })).toBeVisible()
      await expect(confirmation.getByRole('columnheader', { name: '调整后', exact: true })).toBeVisible()
      await confirmation.getByRole('button', { name: '确认保存', exact: true }).click()
      await expect(page.getByText(/授权版本冲突.*本地修改已保留/)).toBeVisible()
      await expect(permissionTier.getByRole('radio', { name: '可查看' })).toBeChecked()
      await expect(page.getByPlaceholder('填写角色授权调整原因')).toHaveValue('调整页面只读范围')
      await expect(page.getByText('未保存调整 1 个页面', { exact: true })).toBeVisible()

      await expect(confirmation).toBeHidden()
      await expect(save).toHaveAttribute('aria-busy', 'false')
      await expect(save).toBeEnabled()
      await page.setViewportSize({ width: 390, height: 844 })
      await expect(save).toBeInViewport()
      const headerBounds = await modules.locator('xpath=preceding-sibling::header[1]').boundingBox()
      const moduleBounds = await modules.boundingBox()
      expect(headerBounds && moduleBounds && headerBounds.y + headerBounds.height <= moduleBounds.y).toBe(true)
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390)
    })
  }

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

  test('无独立模块授权时查询权限自动开通模块，但不能导入或访问其他页面', async ({ context, page }) => {
    await context.addCookies([{ name: 'auth_token', value: 'page-query', url: 'http://127.0.0.1:3200' }])
    await page.goto('/purchasing')
    await expect(page).toHaveURL(/\/purchasing\/supplier$/)
    await expect(page.getByRole('navigation', { name: '业务模块' }).getByRole('link', { name: '采购管理', exact: true })).toBeVisible()
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
    await expect(page.getByRole('heading', { name: '偏差台账' })).toBeVisible()
    for (const name of ['新建偏差', '导入', '导出', '批量删除']) {
      await expect(page.getByRole('button', { name, exact: true })).toHaveCount(0)
    }
    await page.goto('/quality/deviations/new')
    await expect(page.getByText('尚未获得新增偏差记录的操作权限，请联系系统管理员。')).toBeVisible()
    await expect(page.getByRole('button', { name: '保存台账' })).toHaveCount(0)
    const response = await page.goto('/quality/deviations/records')
    expect(response?.status()).toBe(403)
  })

  test('新增偏差提交台账（报告人改为可选）', async ({ context, page, request }) => {
    await context.addCookies([{ name: 'auth_token', value: 'ledger-create', url: 'http://127.0.0.1:3200' }])
    await page.goto('/quality/deviations/new')
    await page.getByLabel('产品名称/批号', { exact: true }).fill('产品A / 批次1')
    await page.getByLabel('偏差简要描述', { exact: true }).fill('浏览器新增偏差')
    await page.getByRole('button', { name: '保存台账' }).click()
    await expect(page).toHaveURL(/\/quality\/deviations\/ledger$/)
    const recorded = await request.get('http://127.0.0.1:4100/__test/ledger-write?token=ledger-create')
    expect(await recorded.json()).toMatchObject({ description: '浏览器新增偏差', affected_items: '产品A / 批次1', is_closed: false })
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
