import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import React, { type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { moduleMenus, type ModuleMenu } from '@/lib/menu-config'
import { MENU_PAGE_UNAVAILABLE, PAGE_ACCESS_NOTICE_HEADER, PAGE_ACCESS_NOTICE_SEGMENT, QUERY_PERMISSION_REQUIRED } from '@/lib/page-access-notice'
import type { User } from '@/types/user'
import { AppShell } from './AppShell'
import DashboardLayout from '@/app/(dashboard)/layout'
import DashboardNotFound from '@/app/(dashboard)/not-found'
import PageAccessNoticePage from '@/app/(dashboard)/page-access-notice/[...originalPath]/page'

const session = vi.hoisted(() => ({ pathname: '/purchasing/supplier', segment: 'purchasing', noticeMarker: '', user: null as User | null }))
vi.mock('next/navigation', () => ({
  usePathname: () => session.pathname,
  useSelectedLayoutSegment: () => session.segment,
  useSearchParams: () => new URLSearchParams(),
  notFound: () => { throw new Error('not found') },
  redirect: vi.fn(),
}))
vi.mock('next/headers', () => ({ headers: async () => new Headers({
  'X-Dazah-Page-Path': session.pathname,
  [PAGE_ACCESS_NOTICE_HEADER]: session.noticeMarker,
}) }))
vi.mock('@/actions/auth', () => ({ getCurrentUser: async () => session.user }))
vi.mock('@/components/AntdProvider', () => ({ AntdProvider: ({ children }: { children: ReactNode }) => children }))
vi.mock('@/components/agent/AgentFloatingEntry', () => ({ AgentFloatingEntry: () => null }))
vi.mock('@/components/feishu-data', () => ({ MappedMenuPageGate: ({ children }: { children: ReactNode }) => (
  <div data-mapped-page>{children}</div>
) }))
vi.mock('./TopNav', () => ({ TopNav: ({ modules }: { modules: ModuleMenu[] }) => (
  <nav>{modules.map((module) => <a key={module.key} href={module.path}>{module.label}</a>)}</nav>
) }))
vi.mock('./Sidebar', () => ({ Sidebar: ({ modules }: { modules: ModuleMenu[] }) => (
  <aside>{modules.map((module) => <span key={module.key}>{module.label}</span>)}</aside>
) }))

function makeUser(overrides: Partial<User> = {}): User {
  return { id: 'test-user', name: '测试用户', role: 'user', status: 'active', auth_source: 'local',
    grant_version: 1, module_codes: ['procurement'], page_permissions: [],
    page_permission_rollouts: { procurement: 'enforced' }, ...overrides }
}

function pageGrant(permissions: Array<'access' | 'query' | 'operate'>): NonNullable<User['page_permissions']> {
  return [{ page_key: 'purchasing:supplier', module_code: 'procurement', permissions,
    source: 'user', sensitive_actions: [], data_scope: { scope_type: 'not_applicable' } }]
}

describe('application shell permission boundary', () => {
  beforeEach(() => {
    session.pathname = '/purchasing/supplier'
    session.segment = 'purchasing'
    session.noticeMarker = ''
  })
  it('gives the protected permission workbench the full viewport', () => {
    session.pathname = '/system/roles/test-role/page-permissions'
    const html = renderToStaticMarkup(<AppShell user={makeUser({ role: 'admin' })}>页面权限基线配置</AppShell>)
    expect(html).toContain('页面权限基线配置')
    expect(html).not.toContain('<nav>')
    expect(html).not.toContain('<aside>')
    const denied = renderToStaticMarkup(<AppShell user={makeUser()}>页面权限基线配置</AppShell>)
    expect(denied).not.toContain('页面权限基线配置')
  })
  it('retains a compact mobile entry to the energy sidebar', () => {
    session.pathname = '/energy/reports'
    const html = renderToStaticMarkup(<AppShell user={makeUser({ role: 'admin' })}>能源报表</AppShell>)
    expect(html).toContain('能源菜单')
    expect(html).toContain('min-[701px]:hidden')
    expect(html).toContain('能源报表')
  })

  it.each(moduleMenus)('allows administrators into $label without individual grants', (module) => {
    session.pathname = module.path
    const html = renderToStaticMarkup(<AppShell user={makeUser({ role: 'admin', module_codes: [],
      page_permission_rollouts: { [module.moduleCode]: 'enforced' } })}>业务内容</AppShell>)
    expect(html).toContain('业务内容')
    expect(html).not.toContain('暂无页面访问权限')
    for (const entry of moduleMenus) expect(html).toContain(`href="${entry.path}"`)
  })

  it('preserves administrator content through both server and client guards', async () => {
    session.user = makeUser({ role: 'admin', module_codes: undefined })
    const html = renderToStaticMarkup(await DashboardLayout({ children: '业务内容' }))
    expect(html).toContain('业务内容')
    expect(html).not.toContain('暂无页面访问权限')
  })

  it.each([undefined, []])('does not treat missing ordinary-user module grants as unrestricted: %j', (module_codes) => {
    const html = renderToStaticMarkup(<AppShell user={makeUser({ module_codes })}>业务内容</AppShell>)
    expect(html).toContain('暂无模块访问权限')
    expect(html).toContain('当前账号在“采购管理”中没有可访问页面')
    expect(html).not.toContain('业务内容')
  })

  it('opens an effectively granted page with no legacy module grant and closes it after revocation', () => {
    const html = renderToStaticMarkup(<AppShell user={makeUser({ module_codes: [],
      page_permissions: pageGrant(['access', 'query']),
    })}>业务内容</AppShell>)
    expect(html).toContain('业务内容')
    expect(html).toContain('href="/purchasing"')
    const revoked = renderToStaticMarkup(<AppShell user={makeUser({ module_codes: ['procurement'],
      page_permissions: pageGrant([]),
    })}>业务内容</AppShell>)
    expect(revoked).toContain('暂无模块访问权限')
    expect(revoked).not.toContain('业务内容')
  })

  it.each([
    { permissions: [], message: '暂无模块访问权限' },
    { permissions: ['access'] as const, message: '当前菜单仅授予入口权限' },
  ])('preserves ordinary-user denial: $message', async ({ permissions, message }) => {
    session.user = makeUser({ page_permissions: pageGrant([...permissions]) })
    const html = renderToStaticMarkup(await DashboardLayout({ children: '业务内容' }))
    expect(html).toContain(message)
    expect(html).not.toContain('业务内容')
  })

  it('renders the authorized notice route with navigation and skips mapped business data', async () => {
    session.user = makeUser({ page_permissions: [
      ...pageGrant(['access', 'query']),
      ...pageGrant(['access']).map((grant) => ({ ...grant, page_key: 'purchasing:order' })),
    ] })
    session.pathname = '/purchasing/order'
    session.segment = PAGE_ACCESS_NOTICE_SEGMENT
    session.noticeMarker = QUERY_PERMISSION_REQUIRED
    const notice = await PageAccessNoticePage()
    const html = renderToStaticMarkup(await DashboardLayout({
      children: <>{notice}<span>提示路由内容</span></>,
    }))
    expect(html).toContain('当前菜单仅授予入口权限')
    expect(html).toContain('role="heading" aria-level="1"')
    expect(html).toContain('查看业务数据请联系管理员开通查询权限。')
    expect(html).toContain('提示路由内容')
    expect(html).toContain('href="/purchasing"')
    expect(html).toMatch(/aria-current="page"[^>]*>采购订单/)
    expect(html).not.toContain('data-mapped-page')
    expect(html).not.toContain('了解访问规则')
  })

  it('renders an unavailable menu in the shell with its own heading and guidance', async () => {
    session.user = makeUser({ page_permissions: pageGrant(['access', 'query']) })
    session.segment = PAGE_ACCESS_NOTICE_SEGMENT
    session.noticeMarker = MENU_PAGE_UNAVAILABLE
    const html = renderToStaticMarkup(await DashboardLayout({ children: await PageAccessNoticePage() }))
    expect(html).toMatch(/role="heading" aria-level="1">页面暂未开放/)
    expect(html).toContain('请选择其他菜单继续操作。')
    expect(html).toContain('href="/purchasing"')
    expect(html).not.toContain('开通查询权限')
    expect(html).not.toContain('data-mapped-page')
  })

  it('renders a business-route 404 in the shell without requiring a notice rewrite', async () => {
    session.user = makeUser({ page_permissions: pageGrant(['access', 'query']) })
    const html = renderToStaticMarkup(await DashboardLayout({ children: <DashboardNotFound /> }))
    expect(html).toMatch(/role="heading" aria-level="1">页面未找到/)
    expect(html).toContain('href="/purchasing"')
    expect(html).toContain('请检查访问地址，或通过菜单前往其他页面。')
  })

  it('renders only the granted page for an ordinary query user', async () => {
    session.user = makeUser({ page_permissions: pageGrant(['access', 'query']) })
    const html = renderToStaticMarkup(await DashboardLayout({ children: '业务内容' }))
    expect(html).toContain('业务内容')
    expect(html).toContain('href="/purchasing"')
    expect(html).not.toContain('href="/quality"')
    session.pathname = '/purchasing/order'
    const denied = renderToStaticMarkup(await DashboardLayout({ children: '业务内容' }))
    expect(denied).toContain('暂无页面访问权限')
    expect(denied).not.toContain('业务内容')
  })

  it('admits the equipment console with only a legacy workshop-leaf grant', () => {
    // 统一工作台：旧「车间×功能」叶授权经展开后，/equipment 聚合入口按任一模块授权放行
    session.pathname = '/equipment'
    const html = renderToStaticMarkup(<AppShell user={makeUser({
      module_codes: ['equipment'],
      page_permissions: [{
        page_key: 'equipment:workshop-101-2:inspection-101-2',
        module_code: 'equipment',
        permissions: ['access', 'query'],
        source: 'user', sensitive_actions: [], data_scope: { scope_type: 'not_applicable' },
      }],
      page_permission_rollouts: { equipment: 'enforced' },
    })}>业务内容</AppShell>)
    expect(html).toContain('业务内容')
    expect(html).not.toContain('暂无页面访问权限')
  })

  it('builds navigation from the current user page grant', () => {
    const html = renderToStaticMarkup(<AppShell user={makeUser({
      page_permissions: pageGrant(['access', 'query']),
    })}>业务内容</AppShell>)
    expect(html).toContain('业务内容')
    expect(html).toContain('href="/purchasing"')
    expect(html).not.toContain('href="/quality"')
  })

  it('keeps page denial and query-only states in the shell', () => {
    const sourcePath = fileURLToPath(new URL('./AppShell.tsx', import.meta.url))
    const source = readFileSync(sourcePath, 'utf8')

    expect(source).toContain('暂无页面访问权限')
    expect(source).toContain('PageAccessNotice')
    expect(source).toContain('MappedMenuPageGate')
    expect(source).toContain('getAuthorizedPageMenus')
    expect(source).toContain('grant_version: user.grant_version')
  })
})
