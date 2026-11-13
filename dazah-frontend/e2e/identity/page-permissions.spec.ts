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

  for (const { appearance, viewport } of [
    { appearance: 'light', viewport: { width: 1366, height: 720 } },
    { appearance: 'dark', viewport: { width: 900, height: 720 } },
    { appearance: 'dark', viewport: { width: 390, height: 740 } },
  ]) {
    test(`分配角色抽屉无需整体下滑即可填写原因 ${appearance} ${viewport.width}`, async ({ context, page }) => {
      await page.setViewportSize(viewport)
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await context.addCookies([{ name: 'auth_token', value: 'assignment-layout-admin', url: 'http://127.0.0.1:3200' }])
      await page.addInitScript((mode) => localStorage.setItem('dazah-appearance', mode), appearance)
      await page.route(/\/api\/v1\/identity\/admin\/users\?/, (route) => route.fulfill({ json: { code: 200, data: {
        total: 1, items: [{ id: 'layout-user', name: 'QA部公用账号', grant_version: 1,
          roles: [
            { id: 'role-1', name: '测试角色 1', code: 'test_role_1', is_system: false },
            { id: 'role-2', name: '测试角色 2', code: 'test_role_2', is_system: false },
          ] }],
      } } }))
      await page.route('**/api/v1/identity/admin/data-scopes', (route) => route.fulfill({ json: { code: 200, data: [] } }))
      await page.goto('/settings?tab=permissions')
      await page.getByRole('button', { name: '用户角色', exact: true }).click()
      await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
      await page.getByRole('button', { name: /分配角色$/ }).click()

      const drawer = page.getByRole('dialog', { name: /分配角色/ })
      const body = drawer.locator('.ant-drawer-body')
      const search = drawer.getByRole('textbox', { name: '搜索可分配角色' })
      const footer = drawer.locator('.ant-drawer-footer')
      const reason = footer.getByRole('textbox', { name: '角色授权调整原因' })
      const reasonTrigger = footer.getByRole('button', { name: /授权调整原因/ })
      const lastRole = drawer.getByRole('checkbox', { name: /测试角色 12/ })
      await expect(lastRole).toBeAttached()
      await expect(lastRole).not.toBeInViewport()
      await expect(search).toBeInViewport({ ratio: 1 })
      const selection = drawer.getByRole('region', { name: '已选择的角色' })
      const restore = selection.getByRole('button', { name: '恢复原有选择' })
      const clear = selection.getByRole('button', { name: '取消全部选择' })
      const roleCount = selection.getByRole('heading', { name: '已选择 2 个角色' })
      await expect(restore).toBeDisabled()
      await expect.poll(() => drawer.evaluate((element) =>
        Math.abs(element.getBoundingClientRect().right - window.innerWidth))).toBeLessThanOrEqual(0.01)
      const selectionBox = (await selection.boundingBox())!
      const restoreBox = (await restore.boundingBox())!
      const clearBox = (await clear.boundingBox())!
      const countBox = (await roleCount.boundingBox())!
      const firstTag = selection.getByRole('button', { name: '移除角色 测试角色 1' })
      const tagBox = (await firstTag.boundingBox())!
      expect(restoreBox.y).toBe(clearBox.y)
      expect(restoreBox.height).toBe(clearBox.height)
      expect(restoreBox.x + restoreBox.width).toBeLessThan(clearBox.x)
      expect(clearBox.x + clearBox.width).toBeCloseTo(selectionBox.x + selectionBox.width, 0)
      expect(clearBox.y + clearBox.height).toBeLessThanOrEqual(tagBox.y)
      if (viewport.width < 576) {
        expect(restoreBox.y).toBeGreaterThanOrEqual(countBox.y + countBox.height)
      } else {
        expect(restoreBox.x).toBeGreaterThan(countBox.x + countBox.width)
      }
      await clear.click()
      await expect(selection).toContainText('已选择 0 个角色')
      await expect(restore).toBeInViewport({ ratio: 1 })
      await restore.click()
      await expect(selection).toContainText('已选择 2 个角色')
      await expect(drawer.getByRole('checkbox', { name: /^测试角色 1\b/ })).toBeChecked()
      await expect(drawer.getByRole('checkbox', { name: /^测试角色 2\b/ })).toBeChecked()
      await expect(reason).toBeHidden()
      await expect(reasonTrigger).toContainText('待填写')
      await expect(drawer.getByRole('button', { name: /^保\s*存$/ })).toBeInViewport({ ratio: 1 })
      await expect.poll(() => body.evaluate((element) => element.scrollHeight - element.clientHeight)).toBeLessThanOrEqual(1)

      const roleSection = drawer.getByRole('region', { name: '添加角色' })
      const scopeTrigger = footer.getByRole('button', { name: /部门数据范围/ })
      const scope = footer.getByRole('region', { name: '部门数据范围' })
      const save = footer.getByRole('button', { name: /^保\s*存$/ })
      await expect(scopeTrigger).toHaveAttribute('aria-expanded', 'false')
      await expect(scope).toBeHidden()
      const roleBounds = (await roleSection.boundingBox())!
      const reasonBounds = (await reasonTrigger.boundingBox())!
      const triggerBounds = (await scopeTrigger.boundingBox())!
      const saveBounds = (await save.boundingBox())!
      expect(triggerBounds.x + triggerBounds.width).toBeLessThanOrEqual(saveBounds.x)
      expect(triggerBounds.y).toBe(reasonBounds.y)
      expect(triggerBounds.height).toBe(reasonBounds.height)
      if (viewport.width >= 900) {
        await expect(drawer).toHaveCSS('width', '800px')
        expect(reasonBounds.x).toBeGreaterThanOrEqual(triggerBounds.x + triggerBounds.width)
        expect(reasonBounds.x + reasonBounds.width).toBeLessThanOrEqual(saveBounds.x)
        expect(Math.abs(triggerBounds.y - saveBounds.y)).toBeLessThanOrEqual(1)
        await expect(drawer.getByRole('checkbox', { name: /^测试角色 5\b/ })).toBeInViewport({ ratio: 1 })
      } else {
        expect(reasonBounds.y).toBeGreaterThanOrEqual(roleBounds.y + roleBounds.height)
      }

      await scopeTrigger.press('Enter')
      await scope.getByText('全部部门', { exact: true }).click()
      await expect(scopeTrigger).toHaveAttribute('aria-expanded', 'false')
      await expect(scopeTrigger).toContainText('全部部门')
      await expect(scope).toBeHidden()
      await scopeTrigger.press('Enter')
      await scope.getByText('本部门 + 子部门', { exact: true }).click()
      await expect(scopeTrigger).toContainText('本部门 + 子部门')
      await expect(scope).toBeHidden()
      await scopeTrigger.press('Enter')
      await expect(scopeTrigger).toHaveAttribute('aria-expanded', 'true')
      await scope.getByText('指定部门', { exact: true }).click()
      const done = scope.getByRole('button', { name: /^完\s*成$/ })
      await expect(done).toBeDisabled()
      const firstDepartment = scope.getByRole('treeitem', { name: '测试部门 1', exact: true })
      await expect(firstDepartment).toBeInViewport({ ratio: 1 })
      await firstDepartment.getByRole('checkbox').click()
      await expect(scopeTrigger).toContainText('指定部门（1）')
      await expect(scopeTrigger).toHaveAttribute('aria-expanded', 'true')
      await scope.getByRole('treeitem', { name: '测试部门 10', exact: true }).getByRole('checkbox').click()
      await expect(scopeTrigger).toContainText('指定部门（2）')
      await expect(scope).toBeInViewport({ ratio: 1 })
      const scopeBounds = (await scope.boundingBox())!
      expect(scopeBounds.y + scopeBounds.height).toBeLessThanOrEqual(triggerBounds.y)
      expect(await roleSection.boundingBox()).toEqual(roleBounds)
      expect(await save.boundingBox()).toEqual(saveBounds)
      await save.click({ trial: true })
      await done.click()
      await expect(scope).toBeHidden()
      await expect(scopeTrigger).toContainText('指定部门（2）')
      await expect(scopeTrigger).toBeFocused()
      await scopeTrigger.press('Enter')
      await expect(firstDepartment).toHaveAttribute('aria-checked', 'true')
      await scopeTrigger.press('Escape')
      await expect(scope).toBeHidden()
      await expect(scopeTrigger).toBeFocused()

      await search.fill('test_role_12')
      await expect(lastRole).toBeInViewport({ ratio: 1 })
      const lastRoleDescription = roleSection.getByText(/^可以查看质量管理模块中的偏差记录/)
      await expect(lastRoleDescription).toBeInViewport({ ratio: 1 })
      expect(await lastRoleDescription.evaluate((element) =>
        element.scrollHeight <= element.clientHeight && element.scrollWidth <= element.clientWidth)).toBe(true)
      await scopeTrigger.click()
      await reasonTrigger.click()
      await expect(scope).toBeHidden()
      const reasonPanel = footer.getByRole('region', { name: '授权调整原因', exact: true })
      await expect(reasonPanel).toBeInViewport({ ratio: 1 })
      await expect(reasonPanel.getByText('0 / 20', { exact: true })).toBeVisible()
      await expect(reasonPanel.getByRole('group', { name: '预设授权调整原因' }).getByRole('button')).toHaveCount(3)
      await reasonPanel.getByRole('button', { name: '岗位职责调整' }).click()
      await expect(reasonPanel).toBeHidden()
      await expect(reasonTrigger).toContainText('岗位职责调整')
      await expect(reasonTrigger).toBeFocused()
      expect(await save.boundingBox()).toEqual(saveBounds)
      await reasonTrigger.click()
      await expect(reason).toHaveValue('岗位职责调整')
      const manualReason = '因岗位职责变更调整指定部门查看权限范围'
      await reason.fill(manualReason)
      await expect(reasonPanel).toBeVisible()
      await save.click({ trial: true })
      await reasonPanel.getByRole('button', { name: /^完\s*成$/ }).click()
      await expect(reasonPanel).toBeHidden()
      await expect(reasonTrigger).toContainText(manualReason)
      const summaryBounds = (await reasonTrigger.getByText(manualReason, { exact: true }).boundingBox())!
      const updatedReasonBounds = (await reasonTrigger.boundingBox())!
      expect(summaryBounds.y + summaryBounds.height).toBeLessThan(updatedReasonBounds.y + updatedReasonBounds.height)
      expect(summaryBounds.x + summaryBounds.width).toBeLessThan(updatedReasonBounds.x + updatedReasonBounds.width)
      expect(await body.evaluate((element) => element.scrollTop)).toBe(0)
    })
  }

  for (const { width, appearance } of [{ width: 1366, appearance: 'light' }, { width: 390, appearance: 'dark' }]) {
    test(`展开全部已选角色后可移除单个角色 ${appearance}`, async ({ context, page }) => {
      await page.setViewportSize({ width, height: 740 })
      await page.addInitScript((mode) => localStorage.setItem('dazah-appearance', mode), appearance)
      await context.addCookies([{ name: 'auth_token', value: 'assignment-layout-admin', url: 'http://127.0.0.1:3200' }])
      const roles = Array.from({ length: 12 }, (_, index) => ({
        id: `role-${index + 1}`, name: `测试角色 ${index + 1}`, code: `test_role_${index + 1}`, is_system: false,
      }))
      await page.route(/\/api\/v1\/identity\/admin\/users\?/, (route) => route.fulfill({ json: { code: 200, data: {
        total: 1, items: [{ id: 'layout-user', name: '角色测试账号', grant_version: 1, roles }],
      } } }))
      await page.route('**/api/v1/identity/admin/data-scopes', (route) => route.fulfill({ json: { code: 200, data: [] } }))
      await page.goto('/system/user-roles')
      await page.getByRole('button', { name: /分配角色$/ }).click()

      const drawer = page.getByRole('dialog', { name: /分配角色/ })
      const selection = drawer.getByRole('region', { name: '已选择的角色' })
      const expand = selection.getByRole('button', { name: '展开全部' })
      const removeLast = selection.getByRole('button', { name: '移除角色 测试角色 12' })
      await expect(expand).toHaveAttribute('aria-expanded', 'false')
      await expect(removeLast).not.toBeInViewport()
      await expand.click()
      const collapse = selection.getByRole('button', { name: '收起', exact: true })
      await expect(collapse).toHaveAttribute('aria-expanded', 'true')
      const panelId = await collapse.getAttribute('aria-controls')
      const tags = page.locator(`[id="${panelId}"]`)
      expect(await tags.evaluate((element) => element.clientHeight)).toBeGreaterThan(84)
      await removeLast.scrollIntoViewIfNeeded()
      await expect(removeLast).toBeInViewport({ ratio: 1 })
      await removeLast.click()
      await expect(selection).toContainText('已选择 11 个角色')
      await expect(removeLast).toHaveCount(0)
      await collapse.click()
      await expect(expand).toHaveAttribute('aria-expanded', 'false')
      expect(await tags.evaluate((element) => element.clientHeight)).toBeLessThanOrEqual(84)
      await expect(drawer.getByRole('button', { name: /^保\s*存$/ })).toBeInViewport({ ratio: 1 })
    })
  }

  test('切换普通管理员时保留原有选择直至确认', async ({ context, page }) => {
    await context.addCookies([{ name: 'auth_token', value: 'assignment-layout-admin', url: 'http://127.0.0.1:3200' }])
    await page.route(/\/api\/v1\/identity\/admin\/users\?/, (route) => route.fulfill({ json: { code: 200, data: {
      total: 1, items: [{ id: 'layout-user', name: '角色测试账号', grant_version: 1, roles: [] }],
    } } }))
    await page.route('**/api/v1/identity/admin/data-scopes', (route) => route.fulfill({ json: { code: 200, data: [] } }))
    await page.goto('/system/user-roles')
    await page.getByRole('button', { name: /分配角色$/ }).click()
    const drawer = page.getByRole('dialog', { name: /分配角色/ })
    const available = drawer.getByRole('region', { name: '添加角色' })
    await expect(available.getByRole('checkbox').nth(0)).toHaveAccessibleName(/^系统管理员/)
    await expect(available.getByRole('checkbox').nth(1)).toHaveAccessibleName(/^普通管理员/)
    for (let index = 1; index <= 7; index += 1) {
      await drawer.getByRole('checkbox', { name: new RegExp(`^测试角色 ${index}\\b`) }).check()
    }
    const count = drawer.getByRole('region', { name: '已选择的角色' })
    await expect(count).toContainText('已选择 7 个角色')
    const admin = drawer.getByRole('checkbox', { name: /普通管理员/ })
    await admin.click()
    const confirmation = page.getByRole('dialog', { name: '切换为「普通管理员」？' })
    await expect(confirmation).toContainText('移除以下 7 个角色')
    await expect(confirmation).toContainText('测试角色 7')
    await confirmation.getByRole('button', { name: '保留当前选择' }).click()
    await expect(count).toContainText('已选择 7 个角色')
    await expect(admin).not.toBeChecked()

    const clear = count.getByRole('button', { name: '取消全部选择' })
    await expect(clear).toBeInViewport({ ratio: 1 })
    await admin.click()
    await confirmation.getByRole('button', { name: '确认切换' }).click()
    await expect(count).toContainText('已选择 1 个角色')
    await expect(admin).toBeChecked()
    await clear.click()
    await expect(count).toContainText('已选择 0 个角色')
    await expect(admin).not.toBeChecked()
  })

  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    test(`有效权限只读展示自动模块入口 ${viewport.width}`, async ({ context, page }, testInfo) => {
      await page.setViewportSize(viewport)
      const appearance = viewport.width === 390 ? 'light' : 'dark'
      await page.addInitScript((mode) => localStorage.setItem('dazah-appearance', mode), appearance)
      await context.addCookies([{ name: 'auth_token', value: 'effective-admin', url: 'http://127.0.0.1:3200' }])
      await page.goto('/system/user-roles')
      await expect(page.getByText('为用户分配角色，模块入口随有效页面权限自动生效。', { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: /模块访问$/ })).toHaveCount(0)
      await page.getByRole('button', { name: /有效权限$/ }).click()
      const drawer = page.getByRole('dialog')
      await expect(drawer.getByText('已开通 1 个模块', { exact: true })).toBeVisible()
      await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
      await expect(drawer.getByRole('button', { name: '了解访问规则' })).toHaveCount(0)
      await expect(drawer.getByRole('textbox', { name: '搜索模块' })).toBeVisible()
      const hrRow = drawer.getByRole('row').filter({ hasText: '人事管理' })
      await expect(hrRow.getByText('自动开通', { exact: true })).toBeVisible()
      await hrRow.getByRole('button', { name: '展开行' }).click()
      await expect(drawer.getByText('员工查看角色', { exact: true })).toBeVisible()
      const pageRow = await drawer.getByRole('row').filter({ hasText: '员工管理' }).last().boundingBox()
      const nextModuleRow = await drawer.getByRole('row').filter({ hasText: '仓储管理' }).boundingBox()
      expect(pageRow && nextModuleRow && pageRow.y + pageRow.height <= nextModuleRow.y).toBe(true)
      await expect(drawer.getByRole('checkbox')).toHaveCount(0)
      await expect(drawer.getByRole('button', { name: /保存/ })).toHaveCount(0)
      await expect(drawer).toHaveCSS('width', viewport.width === 390 ? '390px' : '560px')
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
      let releaseNavigation = () => {}
      const navigationReady = new Promise<void>((resolve) => { releaseNavigation = resolve })
      await page.route(/\/system\/roles\/role-matrix\/page-permissions(?:\?|$)/, async (route) => {
        if (route.request().method() === 'GET') await navigationReady
        await route.continue()
      })
      const initialPermissionReads: string[] = []
      page.on('request', (request) => {
        if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/role-matrix/page-permissions')) {
          initialPermissionReads.push(request.url())
        }
      })
      const navigationProgress = page.getByRole('status', { name: /^正在(?:打开|加载)页面权限$/ })
      try {
        await page.goto('/system/roles')
        await page.evaluate(() => { document.documentElement.dataset.permissionNavigation = 'same-document' })
        await page.getByRole('link', { name: '页面权限', exact: true }).click()
        await expect(navigationProgress.first()).toBeVisible()
      } finally {
        releaseNavigation()
      }
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
      await detail.getByText('作废生产批次', { exact: true }).click()
      await expect(risk).toBeChecked()
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
