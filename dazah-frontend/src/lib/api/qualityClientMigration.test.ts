import { afterEach, describe, expect, it, vi } from 'vitest'

import * as quality from './client/quality'

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  })
}

describe('migrated quality client API coverage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('covers dashboard fallback and query construction for migrated quality endpoints', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => jsonResponse({ meta: { configured: true } }))
    vi.stubGlobal('fetch', fetchMock)

    await quality.fetchProductQualityProducts()
    await quality.fetchProductQualityStandards('P-1', { keyword: '含量', page: 2, page_size: 20 })
    await quality.fetchSupplierQualifications({
      keyword: '供应商',
      supplier_name: '甲',
      material_type: 'API',
      qualification_name: 'GMP',
      is_completed: false,
      page: 2,
      page_size: 20,
    })
    await quality.fetchSupplierStatistics()

    await quality.fetchMpaDashboard('qc_finished_high_spec')
    await quality.fetchMvtDashboard()
    await quality.fetchLftDashboard('qc_finished_lft_usp')
    await quality.fetchDlsDashboard('qc_finished_dor_vet')
    await quality.fetchLkmsDashboard('qc_finished_lkms')
    await quality.fetchFormulationsDashboard('qc_finished_formulation')
    await quality.fetchBbasDashboard('qc_finished_bbas')
    await quality.fetchTryptophanDashboard('qc_finished_tryptophan')
    await quality.fetchWaterDashboard('qc_finished_pure_water')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/product-quality-standards/P-1?keyword=%E5%90%AB%E9%87%8F&page=2&page_size=20',
    )
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('entity_code=qc_finished_high_spec'))).toBe(true)
  })

  it('covers quality list, statistics, Feishu, settings, and AI log clients', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => jsonResponse({ data: [], meta: { total: 3, configured: false } }))
    vi.stubGlobal('fetch', fetchMock)

    await quality.fetchDeviationStatistics()
    await quality.fetchCapaStatistics()
    await quality.fetchChangeDashboardStats()
    await quality.fetchValidationDashboardStats()
    await quality.fetchFeishuValidationDashboardStats()
    await quality.fetchCapa('capa-1')
    await quality.fetchCapas({
      page: 2,
      page_size: 20,
      status: 'open',
      source: 'deviation',
      category: 'quality',
      keyword: '偏差',
      capa_code: 'CAPA-1',
      affected_product: 'P-1',
      source_code: 'DEV-1',
      evaluation_result: 'effective',
      closure_date_from: '2026-01-01',
      closure_date_to: '2026-12-31',
      department: '质量部',
      qa_confirmer: '张三',
    })
    await quality.fetchCapas()
    await quality.fetchCapaPlanTracks({
      capa_id: 'capa-1',
      capa_code: 'CAPA-1',
      progress: 'in_progress',
      owner_name: '李四',
      reminder_status: 'pending',
      due_date_from: '2026-01-01',
      due_date_to: '2026-12-31',
      page: 2,
      page_size: 20,
    })
    await quality.fetchDeviations({
      page: 2,
      page_size: 20,
      status: 'open',
      level: 'major',
      department: '质量部',
      keyword: '偏差',
      deviation_code: 'DEV-1',
      product_keyword: 'P-1',
      has_occurred_before: 'false',
      is_closed: 'false',
      investigation_completed_from: '2026-01-01',
      investigation_completed_to: '2026-12-31',
      root_cause_keyword: '原因',
      corrective_actions_keyword: '措施',
    })
    await quality.fetchDeviation('deviation-1')
    await quality.fetchFeishuDeviationReportRecords({ page: 2, page_size: 20 })
    await quality.fetchDeviationReportRecords({ page: 1, page_size: 10 })
    await quality.fetchFeishuDeviationReportRecord('record-1')
    await quality.fetchFeishuDeviationInvestigationPushRecords({
      deviation_id: 'deviation-1',
      deviation_code: 'DEV-1',
      push_round: '2',
      submitter: '王五',
      department_head_result: '同意',
      qa_result: '同意',
      qa_head_result: '同意',
      submitted_at_from: '2026-01-01',
      submitted_at_to: '2026-12-31',
      page: 2,
      page_size: 20,
    })
    await quality.fetchDeviationInvestigationPushRecords()
    await quality.fetchRelatedCapasForDeviation('deviation-1')
    await quality.fetchDeviationAiSession('deviation-1')

    await quality.fetchChanges({
      change_type: 'technical',
      page: 2,
      page_size: 20,
      change_code: 'CHG-1',
      applicant_department: '质量部',
      change_object: '工艺',
      change_level: 'major',
      application_date_from: '2026-01-01',
      application_date_to: '2026-12-31',
      planned_approval_date_from: '2026-01-01',
      planned_approval_date_to: '2026-12-31',
      execution_date_from: '2026-01-01',
      execution_date_to: '2026-12-31',
      closure_date_from: '2026-01-01',
      closure_date_to: '2026-12-31',
      content_keyword: '变更',
    })
    await quality.fetchChange('change-1')
    await quality.fetchChangeActionPlans({
      change_id: 'change-1',
      change_code: 'CHG-1',
      project_name: '项目',
      related_work: '验证',
      owner_name: '李四',
      director_name: '王五',
      status: 'open',
      delay_flag: 'false',
      sync_status: 'synced',
      deadline_date_from: '2026-01-01',
      deadline_date_to: '2026-12-31',
      page: 2,
      page_size: 20,
    })
    await quality.fetchChangeActionPlansByChange('change-1')
    await quality.searchChangeActionPlanPersons(' 张 ', 10)
    await quality.fetchNextChangeCode('technical')

    await quality.fetchValidations({
      validation_type: 'process',
      status: 'draft',
      keyword: '验证',
      record_code: 'VAL-1',
      department: '质量部',
      planned_end_date_from: '2026-01-01',
      planned_end_date_to: '2026-12-31',
      drafted_at_from: '2026-01-01',
      drafted_at_to: '2026-12-31',
      page: 2,
      page_size: 20,
    })
    await quality.fetchValidationExecutions('process', { status: 'completed', keyword: '验证', page: 2, page_size: 20 })
    await quality.fetchFeishuValidations({ validation_type: 'process', status: 'draft', page: 2, page_size: 20 })
    await quality.fetchQualitySyncConflicts({ limit: 20 })
    await quality.fetchQualityFeishuAppSettings()
    await quality.fetchQualityFeishuEntitySettings()
    await quality.fetchQualityFeishuEntityTables('deviation', ' app-token ')
    await quality.fetchQualityFeishuEntityFieldMappingBundle('deviation', {
      app_token: ' app-token ',
      table_id: ' table-id ',
    })
    await quality.fetchQualityAiLogs({ entity_type: 'deviation', entity_id: 'deviation-1', page: 2, page_size: 20 })
    await quality.fetchFeishuCapas({ keyword: 'CAPA', page: 2, page_size: 20 })
    await quality.fetchFeishuCapaPlanTracks({ keyword: '计划', page: 2, page_size: 20 })
    await quality.fetchDepartmentContacts()

    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/quality/ai/logs?'))).toBe(true)
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/quality/feishu-settings/entities/deviation/tables?app_token=app-token'))).toBe(true)
  })

  it('covers OOS/OOT, complaint/return, document, and attachment clients', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => jsonResponse({ data: [], meta: { total: 0 } }))
    vi.stubGlobal('fetch', fetchMock)

    const params = { keyword: '异常', page: 2, page_size: 20 }
    await quality.fetchOosOotReportRecords(params)
    await quality.fetchOosOotInvestigationPushRecords(params)
    await quality.fetchOosLedgerRecords(params)
    await quality.fetchOotLedgerRecords(params)
    await quality.fetchOotLimitProducts(params)
    await quality.fetchOotLimitItems(params)
    await quality.fetchProductDepartmentRecords(params)
    await quality.fetchComplaintLedgerRecords(params)
    await quality.fetchReturnApplicationRecords(params)
    await quality.fetchReturnLedgerRecords(params)
    await quality.fetchDocumentDepartments()
    await quality.fetchDocumentEntries({ department_id: 'department-1', keyword: 'SOP', page: 2, page_size: 20 })
    await quality.lookupLatestDocument('文件 1')

    fetchMock.mockResolvedValueOnce(new Response(new Blob(['docx']), {
      status: 200,
      headers: {
        'content-type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'content-disposition': "attachment; filename*=UTF-8''%E7%9B%AE%E5%BD%95.docx",
      },
    }))
    const exported = await quality.fetchDocumentCatalogExport('department-1', '质量部')
    expect(exported.filename).toBe('目录.docx')

    fetchMock.mockResolvedValueOnce(new Response('markdown body', {
      status: 200,
      headers: { 'content-type': 'text/markdown' },
    }))
    await expect(quality.fetchDocumentEntryAttachmentContent('entry-1', 'docs/file name.md')).resolves.toMatchObject({
      text: 'markdown body',
      blobUrl: '',
      contentType: 'text/markdown',
    })

    const createObjectUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:attachment')
    fetchMock.mockResolvedValueOnce(new Response(new Blob(['pdf']), {
      status: 200,
      headers: { 'content-type': 'application/pdf' },
    }))
    await expect(quality.fetchDocumentEntryAttachmentContent('entry-1', 'docs/file.pdf')).resolves.toMatchObject({
      text: '',
      blobUrl: 'blob:attachment',
      contentType: 'application/pdf',
    })
    expect(createObjectUrl).toHaveBeenCalled()
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('docs/file%20name.md'))).toBe(true)
  })

  it('maps alternate payloads and surfaces authenticated client errors', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    fetchMock.mockResolvedValueOnce(jsonResponse({ data: { items: [{ id: 'capa-1' }], meta: { total: 4 } } }))
    await expect(quality.fetchCapas()).resolves.toEqual({ items: [{ id: 'capa-1' }], total: 4 })
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: { items: [{ id: 'deviation-1' }], meta: { total: 5 } } }))
    await expect(quality.fetchDeviations()).resolves.toEqual({ items: [{ id: 'deviation-1' }], total: 5 })
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: { items: [{ id: 'change-1' }], meta: { total: 6 } } }))
    await expect(quality.fetchChanges()).resolves.toEqual({ items: [{ id: 'change-1' }], total: 6 })

    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: { reason: 'forbidden' } }), {
      status: 403,
      statusText: 'Forbidden',
      headers: { 'content-type': 'application/json' },
    }))
    await expect(quality.fetchCapaPlanTracks()).rejects.toThrow('{"reason":"forbidden"}')

    fetchMock.mockResolvedValueOnce(new Response('plain failure', { status: 500, statusText: 'Server Error' }))
    await expect(quality.fetchDocumentDepartments()).rejects.toThrow('获取文件目录部门失败: Server Error')

    fetchMock.mockResolvedValueOnce(new Response('plain failure', { status: 404, statusText: 'Not Found' }))
    await expect(quality.lookupLatestDocument('missing')).resolves.toBeNull()
  })
})
