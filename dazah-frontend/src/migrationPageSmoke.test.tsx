import React from 'react'
import { App as AntdApp } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  usePathname: () => '/warehouse/raw-materials',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock('@/hooks/usePermission', () => ({
  usePermission: () => ({ hasAny: () => true, has: () => true }),
}))

vi.mock('@/lib/api/client/hr', () => {
  const empty = vi.fn(async () => [])
  return {
    fetchAnnualTrainingPlans: empty,
    fetchPlanItems: empty,
    fetchPlanAttachmentSections: empty,
    fetchUsedTrainingContent: empty,
    fetchTrainingSession: vi.fn(async () => ({})),
    fetchSessionDocuments: empty,
    fetchNewHires: empty,
    fetchTrainingPersonnelConfigs: empty,
    fetchTrainingDepartments: empty,
  }
})

vi.mock('@/actions/hr', () => ({
  fetchDepartments: vi.fn(async () => ({ data: [], meta: { total: 0, page: 1, page_size: 20 } })),
  fetchCandidatesAction: vi.fn(),
  fetchDepartmentTreeAction: vi.fn(),
  fetchDepartmentsAction: vi.fn(),
  fetchEmployeesAction: vi.fn(),
  fetchJobPostingsAction: vi.fn(),
  fetchOrgTreeAction: vi.fn(),
  getDepartmentSyncStatus: vi.fn(),
  sendOfferEmailAction: vi.fn(),
  syncDepartmentsFromFeishuAction: vi.fn(),
  syncFromFeishuAction: vi.fn(),
  createTrainingLedger: vi.fn(),
  markTrainingContentUsed: vi.fn(),
  upsertTrainingSession: vi.fn(),
  upsertTrainingDocument: vi.fn(),
}))

vi.mock('@/actions/quality', () => ({
  resolveDocumentEntryContent: vi.fn(),
}))

vi.mock('@/lib/api/client/warehouse', () => ({
  fetchWarehouseMaterialPage: vi.fn(async () => undefined),
  fetchWarehouseRecordDetail: vi.fn(async () => undefined),
}))

vi.mock('@/actions/warehouse', () => ({
  deleteWarehouseRecordAction: vi.fn(),
  updateWarehouseRecordAction: vi.fn(),
}))

vi.mock('@/actions/registration', () => ({
  createAuthorizationFdaEntry: vi.fn(),
  createAuthorizationLedgerMain: vi.fn(),
  createAuthorizationLedgerUpdate: vi.fn(),
  deleteAuthorizationFdaEntry: vi.fn(),
  deleteAuthorizationLedgerMain: vi.fn(),
  deleteAuthorizationLedgerUpdate: vi.fn(),
  updateAuthorizationFdaEntry: vi.fn(),
  updateAuthorizationLedgerMain: vi.fn(),
  updateAuthorizationLedgerUpdate: vi.fn(),
}))

vi.mock('@/lib/api/client/registration', () => ({
  fetchAuthorizationFdaExport: vi.fn(async () => new Blob()),
  fetchAuthorizationLedgerExport: vi.fn(async () => new Blob()),
}))

const renderWithAntdApp = (element: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return renderToStaticMarkup(
    React.createElement(
      QueryClientProvider,
      { client: queryClient },
      React.createElement(AntdApp, null, element),
    ),
  )
}

describe('migrated page smoke contracts', () => {
  it('renders the HR training entry with empty data', async () => {
    const { default: TrainingSignInTabsClient } = await import(
      './components/hr/TrainingSignInTabsClient'
    )
    const html = renderWithAntdApp(React.createElement(TrainingSignInTabsClient))
    expect(html).toContain('培训')
  })

  it('renders the registration authorization ledger with empty data', async () => {
    const { default: AuthorizationLetterClient } = await import(
      './components/registration/AuthorizationLetterClient'
    )
    const html = renderWithAntdApp(
      React.createElement(AuthorizationLetterClient, {
        initialRecords: [],
        initialFdaRecords: [],
      })
    )
    expect(html).toContain('授权')
  })

  it('renders the warehouse Feishu page with an empty response', async () => {
    const { WarehouseFeishuTablePage } = await import(
      './components/warehouse/WarehouseFeishuTablePage'
    )
    const html = renderWithAntdApp(
      React.createElement(WarehouseFeishuTablePage, {
        pageKey: 'raw-summary',
        data: {
          page_key: 'raw-summary',
          page_title: '原辅料库存',
          columns: [],
          rows: [],
          total: 0,
          page: 1,
          page_size: 20,
          total_pages: 0,
          source: 'empty',
          generated_at: null,
          base_name: '测试数据',
          stats: undefined,
        } as never,
      })
    )
    expect(html).toContain('原辅料库存')
  })

  it('renders quality, HR, registration and warehouse summary components with empty data', async () => {
    const { QualityFeishuSettingsPage } = await import(
      './components/quality/QualityFeishuSettingsPage'
    )
    const { ChangeTable } = await import('./components/quality/ChangeTable')
    const { default: DepartmentClient } = await import('./components/hr/DepartmentClient')
    const { default: RecruitmentClient } = await import('./components/hr/RecruitmentClient')
    const { default: KnowledgeBasePage } = await import(
      './components/registration/KnowledgeBasePage'
    )
    const { default: RegulationTrackerPage } = await import(
      './components/registration/RegulationTrackerPage'
    )
    const { WarehouseFeishuConfigPage } = await import(
      './components/warehouse/WarehouseFeishuConfigPage'
    )
    const { WarehouseAiPanel } = await import('./components/warehouse/WarehouseAiPanel')
    const { RawMaterialTable } = await import('./components/warehouse/RawMaterialTable')
    const { PackagingTable } = await import('./components/warehouse/PackagingTable')
    const { ProductTable } = await import('./components/warehouse/ProductTable')

    expect(renderWithAntdApp(React.createElement(QualityFeishuSettingsPage))).toContain('飞书')
    expect(renderWithAntdApp(React.createElement(ChangeTable, {
      changes: [],
      total: 0,
    })).length).toBeGreaterThan(0)
    expect(renderWithAntdApp(React.createElement(DepartmentClient, {
      initialDepartments: [],
      initialTotal: 0,
    }))).toContain('部门')
    expect(renderWithAntdApp(React.createElement(RecruitmentClient, { initialJobs: [] }))).toContain('招聘')
    expect(renderWithAntdApp(React.createElement(KnowledgeBasePage, {
      articles: [],
      categories: [],
      overview: { total_articles: 0, published_articles: 0, category_count: 0 } as never,
    }))).toContain('知识库')
    expect(renderWithAntdApp(React.createElement(RegulationTrackerPage, {
      initialResult: { items: [], total: 0, page: 1, pageSize: 20, totalPages: 0 },
      initialNotificationSettings: {
        is_enabled: false,
        recent_days: 7,
        recipient_open_id: null,
        recipient_name: null,
        recipient_department: null,
        schedule_time: '09:00',
        pending_count: 0,
      },
      notificationRecipients: [],
    }))).toContain('法规')
    expect(renderWithAntdApp(React.createElement(WarehouseFeishuConfigPage, {
      initialConfigs: [],
    }))).toContain('飞书')
    expect(renderWithAntdApp(React.createElement(WarehouseAiPanel))).toContain('仓储AI分析')
    const empty: never[] = []
    expect(renderWithAntdApp(React.createElement(RawMaterialTable, { initialItems: empty }))).toContain('原辅料')
    expect(renderWithAntdApp(React.createElement(PackagingTable, { initialItems: empty }))).toContain('包材')
    expect(renderWithAntdApp(React.createElement(ProductTable, { initialItems: empty }))).toContain('成品')
  })

  it('keeps the department page available when each initial source fails', async () => {
    const hrActions = await import('@/actions/hr')
    vi.mocked(hrActions.fetchDepartments).mockRejectedValue(new Error('部门服务不可用'))
    vi.mocked(hrActions.fetchDepartmentTreeAction).mockRejectedValue(new Error('部门树服务不可用'))
    vi.mocked(hrActions.fetchOrgTreeAction).mockRejectedValue(new Error('组织树服务不可用'))

    const { default: DepartmentsPage } = await import('./app/(dashboard)/hr/departments/page')
    const element = await DepartmentsPage()
    expect(element).toBeTruthy()
  })
})
