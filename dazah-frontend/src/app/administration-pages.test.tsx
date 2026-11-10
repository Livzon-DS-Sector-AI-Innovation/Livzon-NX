import { describe, expect, it, vi, beforeEach } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchStats: vi.fn(),
  redirect: vi.fn((path: string) => {
    throw new Error(`REDIRECT:${path}`)
  }),
}))

vi.mock('next/navigation', () => ({ redirect: mocks.redirect }))
vi.mock('@/lib/api/server/administration', () => ({
  fetchTobaccoGiftDashboardStats: mocks.fetchStats,
}))
vi.mock('@/components/administration', () => ({
  TobaccoGiftDashboard: (props: unknown) => ({ type: 'TobaccoGiftDashboard', props }),
  TobaccoGiftRequisitionCard: () => null,
}))
vi.mock('@/components/feishu-data', () => ({
  MappedDatasetPage: (props: unknown) => ({ type: 'MappedDatasetPage', props }),
  ModuleFeishuDataSourcePage: (props: unknown) => ({ type: 'ModuleFeishuDataSourcePage', props }),
}))
vi.mock('@/actions/administration', () => ({
  createAdministrationFeishuRootAction: vi.fn(),
  deleteAdministrationFeishuRootAction: vi.fn(),
  discoverAdministrationFeishuRootAction: vi.fn(),
  saveAdministrationFeishuConfigAction: vi.fn(),
  saveAdministrationPageBindingsAction: vi.fn(),
  syncAdministrationFeishuResourceAction: vi.fn(),
  syncAdministrationFeishuResourcesAction: vi.fn(),
  testAdministrationFeishuConfigAction: vi.fn(),
}))

import AdminPage from './(dashboard)/admin/page'
import AdministrationFeishuSettingsPage from './(dashboard)/admin/settings/feishu/page'
import TobaccoGiftItemsPage from './(dashboard)/admin/tobacco-gift/items/page'
import TobaccoGiftDashboardPage from './(dashboard)/admin/tobacco-gift/page'
import TobaccoGiftRecordsPage from './(dashboard)/admin/tobacco-gift/records/page'

type ElementLike = { type: unknown; props: Record<string, unknown> }

describe('administration pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('redirects the module root to the tobacco-gift dashboard', () => {
    expect(() => AdminPage()).toThrow('REDIRECT:/admin/tobacco-gift')
    expect(mocks.redirect).toHaveBeenCalledWith('/admin/tobacco-gift')
  })

  it('prefetches dashboard stats with the dashboard page key', async () => {
    const stats = { item_categories: 3 }
    mocks.fetchStats.mockResolvedValue(stats)

    const element = (await TobaccoGiftDashboardPage()) as unknown as ElementLike

    expect(mocks.fetchStats).toHaveBeenCalledWith('admin:tobacco-gift:dashboard')
    expect(element.props).toEqual({ stats, error: null })
  })

  it('degrades to an error state when stats cannot be loaded', async () => {
    mocks.fetchStats.mockRejectedValue(new Error('当前页面不能调用此业务接口'))

    const element = (await TobaccoGiftDashboardPage()) as unknown as ElementLike

    expect(element.props).toEqual({ stats: null, error: '当前页面不能调用此业务接口' })
  })

  it('renders the items mirror with administration module routing', () => {
    const element = TobaccoGiftItemsPage() as unknown as ElementLike
    expect(element.props).toMatchObject({
      moduleCode: 'administration',
      pageKey: 'admin:tobacco-gift:items',
      title: '物品清单',
      enableAdvancedQuery: false,
    })
  })

  it('renders the requisition records mirror with the form entry', () => {
    const fragment = TobaccoGiftRecordsPage() as unknown as {
      props: { children: ElementLike[] }
    }
    const [, mirror] = fragment.props.children
    expect(mirror.props).toMatchObject({
      moduleCode: 'administration',
      pageKey: 'admin:tobacco-gift:records',
      title: '领用记录',
    })
  })

  it('wires every Feishu settings write through server actions', () => {
    const element = AdministrationFeishuSettingsPage() as unknown as ElementLike
    expect(element.props.moduleCode).toBe('administration')
    const writeActions = element.props.writeActions as Record<string, unknown>
    expect(Object.keys(writeActions).sort()).toEqual([
      'createRoot',
      'deleteRoot',
      'discoverRoot',
      'saveBindings',
      'saveConfig',
      'syncResource',
      'syncResources',
      'testConfig',
    ])
    expect(Object.values(writeActions).every((value) => typeof value === 'function')).toBe(true)
  })
})
