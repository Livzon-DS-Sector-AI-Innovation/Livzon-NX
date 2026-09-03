/* @vitest-environment happy-dom */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'migration-server-token' }),
  }),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies,
  headers: vi.fn(async () => new Headers({ 'X-Dazah-Page-Path': '/hr/position-transfers' })),
}))

import * as admin from './server/admin'
import * as hr from './server/hr'
import * as quality from './server/quality'
import * as registration from './server/registration'
import * as regulatory from './server/regulatoryTracker'
import * as warehouse from './server/warehouse'

function okResponse(data: unknown = []): Response {
  return new Response(JSON.stringify({ code: 200, message: 'ok', data }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('migrated server API contracts', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => okResponse()))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('constructs authenticated system, HR, quality and warehouse reads', async () => {
    await admin.serverFetchPermissions()
    await admin.serverFetchRoles()
    await admin.serverFetchDeptRules()
    await admin.serverFetchDepartments()
    await admin.serverFetchMenus()
    await admin.serverFetchAdminUsers()

    await hr.fetchPositionTransfersServer({ keyword: '张', approval_status: 'pending', page: 2 })
    expect(vi.mocked(fetch).mock.calls.at(-1)?.[1]?.headers).toEqual(expect.objectContaining({
      'X-Dazah-Page-Path': '/hr/position-transfers',
    }))
    await hr.fetchJobPostingsServer({ keyword: 'QA', page: 2 })
    await hr.fetchCandidatesServer({ keyword: '李', fit_level: 'A', interview_status: 'pending' })
    await hr.fetchOnboardingServer({ keyword: '新员工' })
    await hr.fetchNewEmployeesServer({ department: '质量', status: 'active', keyword: '王' })
    await hr.fetchNewDepartmentsServer({ keyword: '生产' })
    await hr.fetchNewOnboardingRecordsServer({ department: '生产', position: '技术员' })
    await hr.fetchNewDepartureRecordsServer({ department: '生产', offboarding_type: 'resign' })
    await hr.fetchNewOffboardingRecordsServer({ department: '生产', offboarding_type: 'retire' })
    await hr.generateOffboardingCertificateServer('departure-1')
    await hr.fetchEmployeeStatsServer()
    await hr.fetchContractsServer({ keyword: '合同', contract_sequence: '2026', page: 2 })
    await hr.fetchAnnualTrainingPlanByIdServer('plan-1')
    await hr.fetchContractApprovalResultsServer({
      start_date: '2026-01-01',
      end_date: '2026-12-31',
      department: '质量',
      result: 'approved',
    })

    await quality.fetchProductQualityStandardsServer('P-1', { keyword: '含量', page: 2, page_size: 10 })
    await quality.fetchProductQualityProductsServer()
    await quality.fetchComplaintLedgerServer()
    await quality.fetchReturnLedgerServer()
    await quality.fetchReturnApplicationServer()
    await quality.fetchDeviationServer('deviation-1')
    await quality.fetchFeishuValidationDashboardStatsServer()
    await quality.fetchDocumentDepartmentsServer()
    await quality.fetchLabelVerificationsServer({ page: 1, page_size: 20 })

    await warehouse.fetchWarehouseDashboard('raw', true, true)
    await warehouse.fetchWarehousePageFeishuConfigs()
    await warehouse.fetchRawMaterials()
    await warehouse.fetchPackagingMaterials()
    await warehouse.fetchProducts()
    await warehouse.fetchWarehouseMaterialPage('raw-summary', {
      page: 2,
      page_size: 50,
      source: 'feishu',
      force: true,
      keyword: '物料',
      start_date: '2026-01-01',
      end_date: '2026-01-31',
      date_field: '入库日期',
      product: '产品A',
      area: '一区',
      quality_status: '合格',
      warning_status: 'normal',
      material_category: 'raw',
      filters: [{ field: '物料名称', operator: 'contains', value: '酸' }],
    }, 1000)

    const calls = vi.mocked(fetch).mock.calls
    expect(calls.length).toBeGreaterThanOrEqual(35)
    expect(calls.some(([, init]) => {
      const headers = init?.headers as Record<string, string> | undefined
      return headers?.Authorization === 'Bearer migration-server-token'
    })).toBe(true)
    expect(calls.some(([url]) => String(url).includes('/hr/new/onboarding-records'))).toBe(true)
    expect(calls.some(([url]) => String(url).includes('/quality/label-verifications'))).toBe(true)
    expect(calls.some(([url]) => String(url).includes('/warehouse/material-pages/raw-summary'))).toBe(true)
  })

  it('constructs registration and regulatory reads plus protected writes', async () => {
    await registration.serverApiGet('/api/v1/registration/ping')
    await registration.serverApiPost('/api/v1/registration/items', { name: '项目' })
    await registration.serverApiPut('/api/v1/registration/items/1', { name: '项目2' })
    await registration.serverApiPatch('/api/v1/registration/items/1', { status: 'active' })
    await registration.serverApiDelete('/api/v1/registration/items/1')
    await registration.serverApiPostFormData('/api/v1/registration/import', new FormData())
    await registration.fetchAuthorizationLedgerServer({
      product_name: '产品A',
      market_name: 'EU',
      status: '已递交',
      keyword: '授权',
    })
    await registration.fetchAuthorizationFdaServer({ product_name: '产品A', keyword: 'FDA' })
    await registration.fetchCertificateWorkbookOverviewServer()
    await registration.fetchCertificateReminderSettingsServer()
    await registration.fetchCertificateReminderRecipientsServer()
    await registration.fetchCertificateSheetDetailServer('sheet/1')
    await registration.fetchProjectLedgerWorkbookServer()
    await registration.fetchProjectLedgerSheetDetailServer('sheet/2')
    await registration.fetchProjectOverviewServer()
    await registration.fetchDeclarationProgressWorkbookServer()
    await registration.fetchDeclarationProgressSheetDetailServer('declaration/1')
    await registration.fetchFeeDashboardServer(2026)
    await registration.fetchFeeEntriesServer(2026)
    await registration.fetchInspectionContactsServer()
    await registration.fetchKnowledgeOverviewServer()
    await registration.fetchKnowledgeCategoriesServer()
    await registration.fetchKnowledgeArticlesServer()
    await registration.fetchKnowledgeArticleDetailServer('article/1')

    await regulatory.fetchRegulatoryTrackerSummaryServer()
    await regulatory.fetchRegulatoryTrackerDocumentsServer({
      keyword: 'GMP',
      sourceSite: 'NMPA',
      publishDateFrom: '2026-01-01',
      publishDateTo: '2026-01-31',
      captureDateFrom: '2026-01-01',
      captureDateTo: '2026-01-31',
      statusText: 'active',
      classification: 'quality',
      isNew: true,
      page: 2,
      pageSize: 50,
    })
    await regulatory.fetchRegulatoryTrackerDocumentDetailServer('document/1')
    await regulatory.fetchRegulatoryTrackerSyncJobsServer(2, 50)
    await regulatory.fetchRegulatoryTrackerNotificationSettingsServer()
    await regulatory.fetchRegulatoryTrackerNotificationRecipientsServer()

    const calls = vi.mocked(fetch).mock.calls
    expect(calls.some(([url]) => String(url).includes('/registration/authorization-letters/ledger'))).toBe(true)
    expect(calls.some(([url]) => String(url).includes('/regulatory-documents?'))).toBe(true)
    expect(calls.some(([, init]) => init?.method === 'POST' && init?.body === JSON.stringify({ name: '项目' }))).toBe(true)
    expect(calls.some(([, init]) => init?.body instanceof FormData)).toBe(true)
  })

  it('maps server errors instead of returning placeholder data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('forbidden', { status: 403, statusText: 'Forbidden' }),
    ))

    await expect(admin.serverFetchRoles()).rejects.toThrow('请求失败 (403)')
    await expect(hr.fetchNewEmployeesServer()).rejects.toThrow('HTTP 403')
    await expect(registration.serverApiGet('/api/v1/registration/protected')).rejects.toThrow('请求失败: 403 Forbidden')
    await expect(regulatory.fetchRegulatoryTrackerSummaryServer()).rejects.toThrow('请求失败: 403 Forbidden')
    await expect(warehouse.fetchProducts()).rejects.toThrow('获取成品库存失败')
  })
})
