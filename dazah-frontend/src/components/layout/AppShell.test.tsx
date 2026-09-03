import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import React, { type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { moduleMenus, type ModuleMenu } from '@/lib/menu-config'
import type { User } from '@/types/user'
import { AppShell } from './AppShell'
import DashboardLayout from '@/app/(dashboard)/layout'

const session = vi.hoisted(() => ({ pathname: '/purchasing/supplier', user: null as User | null }))
vi.mock('next/navigation', () => ({ usePathname: () => session.pathname, redirect: vi.fn() }))
vi.mock('next/headers', () => ({ headers: async () => new Headers({ 'X-Dazah-Page-Path': session.pathname }) }))
vi.mock('@/actions/auth', () => ({ getCurrentUser: async () => session.user }))
vi.mock('@/components/AntdProvider', () => ({ AntdProvider: ({ children }: { children: ReactNode }) => children }))
vi.mock('@/components/agent/AgentFloatingEntry', () => ({ AgentFloatingEntry: () => null }))
vi.mock('@/components/feishu-data', () => ({ MappedMenuPageGate: ({ children }: { children: ReactNode }) => children }))
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
  beforeEach(() => { session.pathname = '/purchasing/supplier' })

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
    expect(html).toContain('当前账号未获“采购管理”的查看权限')
    expect(html).not.toContain('业务内容')
  })

  it.each([
    { permissions: [], message: '暂无页面访问权限' },
    { permissions: ['access'] as const, message: '当前页面仅允许访问' },
  ])('preserves ordinary-user denial: $message', async ({ permissions, message }) => {
    session.user = makeUser({ page_permissions: pageGrant([...permissions]) })
    const html = renderToStaticMarkup(await DashboardLayout({ children: '业务内容' }))
    expect(html).toContain(message)
    expect(html).not.toContain('业务内容')
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

  it('keeps page denial and query-only states in the shell', () => {
    const sourcePath = fileURLToPath(new URL('./AppShell.tsx', import.meta.url))
    const source = readFileSync(sourcePath, 'utf8')

    expect(source).toContain('暂无页面访问权限')
    expect(source).toContain('当前页面仅允许访问')
    expect(source).toContain('MappedMenuPageGate')
    expect(source).toContain('getAuthorizedPageMenus')
    expect(source).toContain('grant_version: user.grant_version')
  })
})
