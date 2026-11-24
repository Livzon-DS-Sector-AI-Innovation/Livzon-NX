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
  TobaccoGiftApplyButton: (props: unknown) => ({ type: 'TobaccoGiftApplyButton', props }),
}))
vi.mock('@/components/feishu-data', () => ({
  MappedDatasetPage: (props: unknown) => ({ type: 'MappedDatasetPage', props }),
  ModuleFeishuDataSourcePage: (props: unknown) => ({ type: 'ModuleFeishuDataSourcePage', props }),
}))
vi.mock('@/components/administration/DormitoryDashboard', () => ({
  default: (props: unknown) => ({ type: 'DormitoryDashboard', props }),
}))
vi.mock('./(dashboard)/admin/dormitory/workspace', () => ({
  default: (props: unknown) => ({ type: 'DormitoryWorkspace', props }),
}))
vi.mock('@/components/administration/NoticeWorkspace', () => ({
  default: (props: unknown) => ({ type: 'NoticeWorkspace', props }),
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
import DormitoryPage from './(dashboard)/admin/dormitory/page'
import DormitoryWorkspace from './(dashboard)/admin/dormitory/workspace'
import NoticePage from './(dashboard)/admin/notice/page'
import NoticeWorkspaceMock from '@/components/administration/NoticeWorkspace'
import ScrapMaterialsPage from './(dashboard)/admin/scrap-materials/page'
import SealsPage from './(dashboard)/admin/seals/page'
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

  it('renders the requisition records mirror with a bare apply button (no copy)', () => {
    const fragment = TobaccoGiftRecordsPage() as unknown as {
      props: { children: ElementLike[] }
    }
    const [buttonRow, mirror] = fragment.props.children
    // 按钮经 vi.mock 的组件替身渲染，替身类型名即真实组件名
    const button = buttonRow.props.children as unknown as ElementLike
    expect((button.type as { name?: string }).name).toBe('TobaccoGiftApplyButton')
    expect(mirror.props).toMatchObject({
      moduleCode: 'administration',
      pageKey: 'admin:tobacco-gift:records',
      title: '领用记录',
    })
  })

  it('renders the seals mirror without any extra form entry', () => {
    const element = SealsPage() as unknown as ElementLike
    expect(element.props).toMatchObject({
      moduleCode: 'administration',
      pageKey: 'admin:seals',
      title: '印章管理',
      enableAdvancedQuery: false,
      enablePersonAvatars: true,
    })
  })

  it('renders the scrap-materials mirror for tab-switched bindings', () => {
    const element = ScrapMaterialsPage() as unknown as ElementLike
    expect(element.props).toMatchObject({
      moduleCode: 'administration',
      pageKey: 'admin:scrap-materials',
      title: '废旧物资',
      enableAdvancedQuery: true,
      enablePersonAvatars: true,
      enableExport: true,
    })
  })

  it('renders the dormitory page through the client workspace', () => {
    const element = DormitoryPage() as unknown as ElementLike
    // 页面只做委托；工作台的组合细节（三表页签/默认排序/仪表盘联动）
    // 在 workspace.test.tsx 里渲染断言
    expect(element.type).toBe(DormitoryWorkspace)
  })

  it('renders the notice page through the client workspace', () => {
    const element = NoticePage() as unknown as ElementLike
    // 平台原生公告台账：页面只委托工作台组件，无飞书镜像绑定
    expect(element.type).toBe(NoticeWorkspaceMock)
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
