import { expect, test } from '@playwright/test'

// Bundled Chromium otherwise starts with RenderDocument disabled by Playwright.
test.use({ launchOptions: { args: ['--disable-features=PaintHolding'] } })

const settings = '/settings?tab=permissions&view=impersonation'

test('模拟身份横幅在首屏和窄屏保持在顶部栏内', async ({ page, context, baseURL }) => {
  await context.addCookies([
    { name: 'auth_token', value: 'impersonation-admin', url: baseURL! },
    { name: 'impersonation_token', value: 'impersonation-procurement', url: baseURL!, httpOnly: true },
  ])
  // Keep the server-rendered page visible before Ant Design injects its client styles.
  await page.route('**/*', route => route.request().resourceType() === 'script' ? route.abort() : route.continue())
  const header = page.getByRole('banner')
  const banner = header.locator('[data-platform-notice="warning"]').filter({ hasText: '采购验收用户' })
  const feedback = header.getByRole('button', { name: '问题反馈' })

  for (const hydrated of [false, true]) {
    if (hydrated) await page.unrouteAll()
    await page.emulateMedia({ colorScheme: hydrated ? 'dark' : 'light' })
    await page.goto('/purchasing/supplier')
    await expect(banner).toBeVisible()
    if (hydrated) await expect(feedback).toBeEnabled()

    for (const width of [1280, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 720 })
      const toolbar = (await header.boundingBox())!
      const notice = (await banner.boundingBox())!
      const logo = (await header.getByText('API', { exact: true }).boundingBox())!
      const name = (await banner.getByText('采购验收用户', { exact: true }).boundingBox())!
      const restore = (await banner.getByRole('button', { name: '返回管理员身份' }).boundingBox())!
      const feedbackButton = (await feedback.boundingBox())!
      const view = `${hydrated ? '交互就绪后' : '首屏'} ${width}px`
      expect(notice.y, `${view} 横幅顶部`).toBeGreaterThanOrEqual(toolbar.y)
      expect(notice.y + notice.height, `${view} 横幅底部`).toBeLessThanOrEqual(toolbar.y + toolbar.height)
      expect(notice.x, `${view} 横幅左侧`).toBeGreaterThanOrEqual(logo.x + logo.width)
      expect(notice.x + notice.width, `${view} 横幅右侧`).toBeLessThanOrEqual(feedbackButton.x)
      expect(name.width, `${view} 用户名称仍可见`).toBeGreaterThan(24)
      expect(restore.x, `${view} 返回按钮左侧`).toBeGreaterThanOrEqual(name.x + name.width)
      expect(restore.x + restore.width, `${view} 返回按钮右侧`).toBeLessThanOrEqual(notice.x + notice.width)
    }
  }
})

test('模拟登录输入关键词后自动筛选并可清空', async ({ page, context, baseURL }) => {
  await context.addCookies([{ name: 'auth_token', value: 'impersonation-admin', url: baseURL! }])
  await page.goto(settings)
  const search = page.getByRole('searchbox', { name: '搜索姓名、账号或工号' })
  const target = page.getByRole('row', { name: /采购验收用户/ })
  await expect(target).toBeVisible()

  await search.fill('没有此账号')
  await expect(page.getByText('暂无可模拟的用户')).toBeVisible()
  await search.fill('  procurement-test  ')
  await expect(target).toBeVisible()

  const cleared = page.waitForRequest(request => new URL(request.url()).pathname.endsWith('/impersonation/targets')
    && new URL(request.url()).searchParams.get('keyword') === '')
  await page.getByRole('button', { name: '清空搜索' }).click()
  expect(new URL((await cleared).url()).searchParams.get('offset')).toBe('0')
  await expect(search).toHaveValue('')
  await expect(target).toBeVisible()
})

test('模拟登录切换权限视角并在同一浏览器恢复管理员', async ({ page, context }) => {
  await page.addInitScript(() => {
    document.addEventListener('animationstart', (event) => {
      if (event.pseudoElement !== '::view-transition-new(root)' || event.animationName !== 'workspace-identity-expand') return
      const phase = document.documentElement.dataset.workspaceIdentityTransition
      if (phase) sessionStorage.setItem(`test:workspace-identity-animation:${phase}`, window.location.pathname)
      const reveal = getComputedStyle(document.documentElement, event.pseudoElement)
      if (phase === 'opening') {
        sessionStorage.setItem('test:workspace-identity-tear-feather', String(reveal.maskImage.includes('feGaussianBlur')))
      }
      if (phase === 'restored') {
        sessionStorage.setItem('test:workspace-identity-fan-feather', reveal.getPropertyValue('--identity-fan-radial-feather').trim())
        const origin = getComputedStyle(document.documentElement)
        sessionStorage.setItem('test:workspace-identity-fan-origin', JSON.stringify({
          x: parseFloat(origin.getPropertyValue('--workspace-identity-origin-x')),
          y: parseFloat(origin.getPropertyValue('--workspace-identity-origin-y')),
        }))
      }
    })
    document.addEventListener('animationend', (event) => {
      if (event.pseudoElement !== '::view-transition-new(root)' || event.animationName !== 'workspace-identity-expand') return
      const phase = document.documentElement.dataset.workspaceIdentityTransition
      if (phase) sessionStorage.setItem(`test:workspace-identity-duration:${phase}`, String(event.elapsedTime))
    })
  })
  await page.emulateMedia({ colorScheme: 'dark' })
  await context.addCookies([{
    name: 'auth_token', value: 'impersonation-admin', url: 'http://127.0.0.1:3200',
  }])
  const otherTab = await context.newPage()
  await otherTab.goto(settings)
  await expect(otherTab.getByRole('heading', { name: '权限管理' })).toBeVisible()
  await page.bringToFront()

  await page.goto('/settings?tab=permissions')
  const workspaceInsets = () => page.getByRole('main').first().evaluate(element => {
    const { top, bottom } = element.getBoundingClientRect()
    return { top, bottomGap: window.innerHeight - bottom }
  })
  const normalWorkspace = await workspaceInsets()
  await page.getByRole('tab', { name: '权限检查' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('navigation', { name: '权限管理子导航' }).getByRole('button', { name: '模拟登录', exact: true }))
    .toHaveAttribute('aria-current', 'page')
  const search = page.getByRole('searchbox', { name: '搜索姓名、账号或工号' })
  await search.fill('没有此用户')
  await expect(page.getByText('暂无可模拟的用户')).toBeVisible()
  await search.fill('采购')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect(page.getByRole('columnheader', { name: '角色', exact: true })).toBeVisible()
  const targetRow = page.getByRole('row').filter({ hasText: '采购验收用户' })
  await expect(targetRow.getByText('采购查询员', { exact: true })).toBeVisible()
  await expect(targetRow.getByText('供应商审核员', { exact: true })).toBeVisible()

  const roleFilter = page.getByRole('combobox', { name: '按角色筛选' })
  const roleOptions = page.locator('.ant-select-dropdown:visible')
  await roleFilter.click()
  await roleOptions.getByText('财务复核员', { exact: true }).click()
  await expect(page.getByText('暂无可模拟的用户')).toBeVisible()
  await expect(search).toHaveValue('采购')
  await roleFilter.click()
  await roleOptions.getByText('采购查询员', { exact: true }).click()
  await expect(targetRow).toBeVisible()
  await search.fill('没有此账号')
  await expect(page.getByText('暂无可模拟的用户')).toBeVisible()
  await search.fill('procurement-test')
  await roleFilter.click()
  await roleOptions.getByText('全部角色', { exact: true }).click()
  await expect(targetRow).toBeVisible()
  await roleFilter.click()
  await roleOptions.getByText('采购查询员', { exact: true }).click()
  const secondPage = page.getByTitle('2', { exact: true })
  await secondPage.click()
  await expect(targetRow).toBeVisible()

  await page.getByRole('button', { name: '模拟登录 采购验收用户' }).click()
  const confirmation = page.getByRole('dialog', { name: '确认模拟登录' })
  await expect(confirmation.getByText(/提交、审批、同步等操作会实际生效/)).toBeVisible()
  const confirmationCenterOffset = () => confirmation.evaluate(element => {
    const { left, top, width, height } = element.getBoundingClientRect()
    return Math.max(
      Math.abs(left + width / 2 - window.innerWidth / 2),
      Math.abs(top + height / 2 - window.innerHeight / 2),
    )
  })
  await expect.poll(confirmationCenterOffset).toBeLessThanOrEqual(2)
  await page.emulateMedia({ colorScheme: 'light' })
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await expect.poll(confirmationCenterOffset).toBeLessThanOrEqual(2)
  await confirmation.getByRole('button', { name: '切换身份' }).click()

  await expect(page).toHaveURL(/\/purchasing\/supplier$/)
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('test:workspace-identity-animation:opening')))
    .toBe('/purchasing/supplier')
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('test:workspace-identity-tear-feather')))
    .toBe('true')
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('test:workspace-identity-duration:opening')))
    .toBe('1.12')
  const header = page.getByRole('banner')
  const banner = header.locator('[data-platform-notice="warning"]').filter({ hasText: '当前处于 采购验收用户 用户的模拟视角' })
  await expect(banner).toBeVisible()
  await expect.poll(workspaceInsets).toEqual(normalWorkspace)
  const bannerBounds = () => banner.evaluate(element => {
    const { left, right, top, bottom, width } = element.getBoundingClientRect()
    return { left, rightGap: document.documentElement.clientWidth - right, top, bottom, width }
  })
  const desktop = await bannerBounds()
  expect(desktop.width).toBeLessThanOrEqual(544)
  expect(Math.abs(desktop.left - desktop.rightGap)).toBeLessThanOrEqual(1)
  expect(desktop.bottom).toBeLessThanOrEqual(normalWorkspace.top)
  await expect(banner.locator('strong')).toHaveText('采购验收用户')
  const textAlignmentOffset = async () => {
    const centers = await Promise.all([
      '当前处于', '采购验收用户', '用户的模拟视角', '返回管理员身份',
    ].map(label => banner.getByText(label, { exact: true }).evaluate(element => {
      const range = document.createRange()
      range.selectNodeContents(element)
      const { top, height } = range.getBoundingClientRect()
      return top + height / 2
    })))
    return Math.max(...centers) - Math.min(...centers)
  }
  await expect.poll(textAlignmentOffset).toBeLessThanOrEqual(1)
  await expect(banner).toHaveCSS('backdrop-filter', 'blur(16px) saturate(0.82)')
  await expect(banner).toHaveCSS('animation-duration', '18s')
  const glassLighting = () => banner.evaluate(element => {
    const outline = getComputedStyle(element, '::before').backgroundImage
    const reflection = getComputedStyle(element, '::after')
    return { outline, reflection: reflection.backgroundImage, blur: reflection.filter, opacity: reflection.opacity }
  })
  const initialLighting = await glassLighting()
  expect(initialLighting.outline).toContain('conic-gradient')
  expect(initialLighting.reflection).toBe(initialLighting.outline)
  expect(initialLighting.blur).toContain('blur(14px)')
  expect(Number(initialLighting.opacity)).toBeGreaterThan(0.18)
  await expect.poll(async () => (await glassLighting()).reflection).not.toBe(initialLighting.reflection)
  const lightBackground = await banner.evaluate((element) => getComputedStyle(element).backgroundColor)
  await expect(page.getByRole('heading', { name: '供应商管理' })).toBeVisible()
  const nav = page.getByRole('navigation', { name: '业务模块' })
  await expect(nav.getByRole('link', { name: '采购管理', exact: true })).toBeVisible()
  await expect(nav.getByRole('link', { name: '质量管理', exact: true })).toHaveCount(0)
  await expect(otherTab).toHaveURL(/\/purchasing\/supplier$/)

  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  const restore = page.getByRole('button', { name: '返回管理员身份' })
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect.poll(() => banner.evaluate((element) => getComputedStyle(element).backgroundColor)).not.toBe(lightBackground)
  await expect(banner).toHaveCSS('animation-name', 'none')
  const darkLighting = await glassLighting()
  expect(darkLighting.reflection).toBe(darkLighting.outline)
  expect(Number(darkLighting.opacity)).toBeGreaterThan(Number(initialLighting.opacity))
  expect(Number(darkLighting.opacity)).toBeGreaterThan(0.31)
  await expect.poll(workspaceInsets).toEqual(normalWorkspace)
  await expect.poll(textAlignmentOffset).toBeLessThanOrEqual(1)
  await expect(nav.getByRole('link', { name: '采购管理', exact: true })).toBeInViewport({ ratio: 1 })
  await expect(header.getByRole('button', { name: '问题反馈' })).toBeInViewport({ ratio: 1 })
  await expect(header.getByRole('button', { name: '我的待办' })).toBeInViewport({ ratio: 1 })
  await expect(page.getByRole('heading', { name: '供应商管理' })).toBeInViewport({ ratio: 1 })
  await expect(restore).toBeInViewport()
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  const bannerOrigin = await banner.evaluate(element => {
    const { left, width, bottom } = element.getBoundingClientRect()
    return { x: (left + width / 2) / innerWidth * 100, y: bottom / innerHeight * 100 }
  })
  const restoredQuery = page.waitForRequest(request => {
    const { pathname } = new URL(request.url())
    return pathname === '/api/v1/identity/admin/impersonation/targets'
  })
  await restore.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp('/settings\\?tab=permissions&view=impersonation$'))
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('test:workspace-identity-animation:restored')))
    .toBe('/settings')
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('test:workspace-identity-fan-feather')))
    .toBe('74px')
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('test:workspace-identity-duration:restored')))
    .toBe('1.24')
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem('test:workspace-identity-fan-origin') || 'null')))
    .toEqual(bannerOrigin)
  const restoredFilters = new URL((await restoredQuery).url()).searchParams
  expect(restoredFilters.get('keyword')).toBe('procurement-test')
  expect(restoredFilters.get('role_id')).toBe('procurement-reader')
  expect(restoredFilters.get('offset')).toBe('20')
  await expect(search).toHaveValue('procurement-test')
  await expect(page.locator('.ant-select').filter({ has: roleFilter }).getByText('采购查询员', { exact: true })).toBeVisible()
  await expect(secondPage).toHaveClass(/ant-pagination-item-active/)
  await expect(page.getByRole('button', { name: '模拟登录 采购验收用户' })).toBeVisible()
  await expect(page.getByRole('button', { name: '返回管理员身份' })).toHaveCount(0)
  await expect(otherTab).not.toHaveURL(/\/purchasing\/supplier$/)
})

test('失效的模拟视角经明确退出恢复原管理员会话', async ({ page, context }) => {
  await context.addCookies([
    { name: 'auth_token', value: 'impersonation-admin', url: 'http://127.0.0.1:3200' },
    { name: 'impersonation_token', value: 'invalid-session', url: 'http://127.0.0.1:3200', httpOnly: true },
  ])
  await page.goto('/purchasing/supplier')
  await expect(page).toHaveURL(/\/auth\/impersonation$/)
  await expect(page.getByText('模拟登录暂不可用或已结束')).toBeVisible()
  await page.getByRole('button', { name: '返回管理员身份' }).click()
  await expect(page).toHaveURL(new RegExp('/settings\\?tab=permissions&view=impersonation$'))
})
