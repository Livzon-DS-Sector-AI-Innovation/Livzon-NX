/* @vitest-environment happy-dom */

import React from 'react'
import { App as AntdApp } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  usePathname: () => '/migration/smoke',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: 'record-1', entityCode: 'employee' }),
}))

vi.mock('next/link', () => ({
  default: ({ children, ...props }: { children?: React.ReactNode } & Record<string, unknown>) =>
    React.createElement('a', props, children),
}))

vi.mock('next/image', () => ({
  default: (props: Record<string, unknown>) => React.createElement('img', props),
}))

vi.mock('styled-jsx/style', () => ({ default: () => null }))
vi.mock('echarts-for-react', () => ({
  default: ({ option }: { option?: unknown }) => React.createElement('pre', null, JSON.stringify(option ?? {})),
}))
vi.mock('@/hooks/usePermission', () => ({
  usePermission: () => ({ has: () => true, hasAny: () => true }),
}))

vi.mock('@/lib/download', () => ({ downloadBlob: vi.fn(), downloadZip: vi.fn() }))
vi.mock('@/lib/feishu-url', () => ({ parseFeishuBitableUrl: vi.fn(() => ({ app_token: 'app', table_id: 'table' })) }))

type ComponentModule = Record<string, unknown>
type ModuleLoader = () => Promise<ComponentModule>
type ImportMetaWithGlob = ImportMeta & {
  glob: <T>(patterns: string[], options: { eager: false }) => Record<string, T>
}

const moduleLoaders = (import.meta as ImportMetaWithGlob).glob<ModuleLoader>(
  [
    './components/quality/**/*.{ts,tsx}',
    './components/registration/**/*.{ts,tsx}',
    './components/hr/**/*.{ts,tsx}',
    './components/warehouse/**/*.{ts,tsx}',
    '!./components/**/*.test.{ts,tsx}',
  ],
  { eager: false },
)

const emptyWarehouseData = {
  page_key: 'raw-summary', page_title: '原辅料库存', columns: [], rows: [], total: 0,
  page: 1, page_size: 20, total_pages: 0, source: 'empty', generated_at: null,
  base_name: '测试数据',
}

function propsFor(path: string, exportName: string): Record<string, unknown> {
  const sessionData = {
    training_date: '2026-08-25', training_time_start: '09:00', training_time_end: '10:30',
    topic: 'GMP培训', training_method: '课堂', instructor: '张三', assessment_method: '笔试',
    employee_names: ['李四'], trainee_departments: ['质量部'], employee_dept_map: { 李四: '质量部' },
  }
  const candidate = {
    id: 'candidate-1', name: '张三', job_position: 'QA', interview_status: '待安排',
    fit_level: '高', education: '本科', phone: '13800000000', email: 'test@example.com',
  }
  const record = {
    id: 'record-1', record_id: 'record-1', code: 'TEST-1', name: '测试记录', title: '测试记录',
    project_name: '项目A', product_name: '产品A', product: '产品A', project: '项目A',
    department: '质量部', department_name: '质量部', status: '待处理', state: 'pending',
    created_at: '2026-08-01', updated_at: '2026-08-02', effective_date: '2026-08-01',
    expiry_date: '2027-08-01', latest_values: { project_name: '项目A', product_name: '产品A' },
    latest_style_marks: {}, history_count: 1, fields: [], history: [], attachments: [], comments: [],
  }
  const props: Record<string, unknown> = {
    initialRecords: [record], initialFdaRecords: [record], initialDepartments: [{ id: 'dept-1', name: '质量部', sort_order: 1, document_count: 1 }], initialJobs: [candidate],
    initialItems: [record], items: [record], records: [record], rows: [record], changes: [record], deviations: [record],
    total: 1, page: 1, pageSize: 20, totalPages: 1, open: false,
    onClose: vi.fn(), onApplied: vi.fn(), onCancel: vi.fn(), onSuccess: vi.fn(),
    onRefresh: vi.fn(), onSubmit: vi.fn(), onChange: vi.fn(),
  }
  if (path.includes('WarehouseFeishuTablePage')) {
    props.pageKey = 'raw-summary'
    props.data = emptyWarehouseData
  }
  if (path.includes('ProductTable')) props.initialItems = [{ id: 'product-1', name: '产品A', spec: '注射级', unit: 'kg', orderQty: 100, pending: 10, qualified: 80, subtotal: 80, remaining: 20 }]
  if (path.includes('RawMaterialTable')) props.initialItems = [{ id: 'material-1', name: '原料A', spec: 'USP', unit: 'kg', orderQty: 100, pending: 10, qualified: 80, subtotal: 80, remaining: 20, safetyStock: 30 }]
  if (path.includes('PackagingTable')) props.initialItems = [{ id: 'packaging-1', name: '包装A', spec: '25kg', unit: '箱', orderQty: 100, pending: 10, qualified: 80, subtotal: 80, remaining: 20, safetyStock: 30 }]
  if (path.includes('WarehouseFeishuConfigPage')) props.initialConfigs = []
  if (path.includes('WarehouseDashboard')) {
    props.group = 'raw'; props.title = '原料库存'; props.baseName = '仓储'; props.initialData = {
      safety: { total: 0, ok: 0, low: 0 }, quality: { 合格: 0, 待验: 0, 不合格: 0 },
      material_outbound_30d: [], packaging_outbound_30d_total: 0, month_inbound_total: 0,
      low_stock_top: [],
    }
  }
  if (path.includes('KnowledgeBasePage')) props.articles = [record]; props.categories = [{ id: 'cat-1', name: '法规' }]; props.overview = { total_articles: 1, published_articles: 1, category_count: 1 }
  if (path.includes('RegulationTrackerPage')) props.initialResult = { items: [record], total: 1, page: 1, pageSize: 20, totalPages: 1 }
  if (path.includes('ChangeTable')) props.changes = [record]
  if (path.includes('DeviationTable')) props.deviations = [record]
  if (path.includes('CapaTable')) props.capas = [record]
  if (path.includes('DocumentCatalogPage')) props.initialDepartments = [{ id: 'dept-1', name: '质量部', sort_order: 1, document_count: 1 }]
  if (path.includes('ProductQualityStandardPage')) props.initialRecords = [record]
  if (path.includes('TrainingPersonnelConfigModal')) { props.level = '公司级'; props.scopeDept = undefined }
  if (path.includes('WarehouseAiPanel')) props.initialData = { messages: [{ role: 'assistant', content: '库存分析' }] }
  if (exportName === 'AttachmentPreview') { props.url = ''; props.fileName = 'test.txt' }
  if (path.includes('AIReportPanel')) props.content = '# 分析报告\n\n内容'
  if (path.includes('AiWrittenExamClient') || path.includes('OralExamSheetClient') || path.includes('PracticalExamSheetClient') || path.includes('SignInSheetClient')) props.sessionData = sessionData
  if (path.includes('CandidateCardView')) Object.assign(props, { candidates: [candidate], page: 1, pageSize: 20, loading: false })
  if (path.includes('CandidateDetailClient')) props.candidate = candidate
  if (path.includes('DepartmentTable')) Object.assign(props, { departments: [], orgTreeData: [], filters: { keyword: '', parentId: null, leaderName: '' }, allDepartments: [] })
  if (path.includes('DepartmentTreeView')) props.departments = []
  if (path.includes('EmployeeDashboardClient')) props.stats = { total: 0, contract_expiring_count: 0, department_distribution: [], status_distribution: {}, expiring_contracts: [] }
  if (path.includes('RosterClient')) Object.assign(props, { initialEmployees: [], initialTotal: 0 })
  if (path.includes('ChangeActionPlanTable')) Object.assign(props, { items: [{ id: 'plan-1', change_code: 'CHG-1', project_name: '项目A', related_work: '验证', owner_name: '张三', status: '未启动' }], filters: { change_code: '', project_name: '', related_work: '', owner_name: '', status: '' }, loading: false, page: 1, pageSize: 20 })
  if (path.includes('DepartmentContactPage')) Object.assign(props, { items: [], activeDepartment: '全部', departmentOptions: [] })
  if (path.includes('DeviationAiConversationPanel')) props.deviation = { id: 'deviation-1', deviation_code: 'DEV-1', title: '偏差', status: 'open' }
  if (path.includes('ImportPreviewDrawer')) Object.assign(props, { isOpen: false, title: '导入', headers: [], fileInputId: 'file', templateDownloadUrl: '#', templateFilename: 'template.docx', previewAction: vi.fn(async () => ({})), confirmAction: vi.fn(async () => ({ success_count: 0, update_count: 0, skip_count: 0, error_count: 0 })) })
  if (path.includes('QualityAiAttachmentList')) Object.assign(props, { attachments: [], uploading: false, deletingId: null, onUpload: vi.fn(async () => undefined), onDelete: vi.fn(async () => undefined) })
  if (path.includes('ReportEditor')) Object.assign(props, { initialContent: '调查报告', versions: [], investigationRecords: [], onSave: vi.fn(async () => undefined) })
  if (path.includes('ValidationTable')) Object.assign(props, { mode: 'master', items: [], filters: { record_code: '', keyword: '', status: '', department: '', validation_type: '', planned_end_date_from: '', planned_end_date_to: '', drafted_at_from: '', drafted_at_to: '' }, loading: false, page: 1, pageSize: 20 })
  if (path.includes('TrendDashboardShared')) props.chart = { actual_series: [], target_series: [], categories: [], spec_lines: [] }
  if (path.includes('AiFillPanel')) Object.assign(props, { chapterId: 'chapter-1', chapterCode: 'C01', assets: [], onAssetsChange: vi.fn() })
  if (path.includes('AuthorizationLetterDashboard')) Object.assign(props, { filteredFdaRecords: [], filteredLedgerRecords: [] })
  if (path.includes('CertificateManagementDashboard')) props.overview = { total_records: 0, sheet_count: 0, issuer_count: 0, product_count: 0, expired_count: 0, due_90_count: 0, total_pages: 0, sheet_summaries: [] }
  if (path.includes('CertificateDashboardPage')) Object.assign(props, { overview: { total_records: 0, sheet_count: 0, issuer_count: 0, product_count: 0, expired_count: 0, due_90_count: 0, total_pages: 0, sheet_summaries: [], records: [] }, reminderSettings: { is_enabled: false, reminder_days: 90, recipient_open_id: null, recipient_name: null, recipient_department: null, pending_count: 0 }, reminderRecipients: [] })
  if (path.includes('CertificateSheetPage')) props.detail = { sheet_key: 'certificates', sheet_name: '证书', columns: [], rows: [], summary: { total_records: 0 }, total: 0, page: 1, page_size: 20, total_pages: 0 }
  if (path.includes('DeclarationProgressDashboardPage')) props.overview = { sheets: [{ sheet_key: 'declarations', sheet_name: '申报', columns: [{ label: '项目', key: 'project' }], records: [record], summary: { total_records: 1, total_history_versions: 1 } }] }
  if (path.includes('DeclarationProgressPage')) props.detail = { sheet_key: 'declarations', sheet_name: '申报', columns: [{ label: '项目', key: 'project_name' }], records: [record], total: 1, page: 1, page_size: 20, total_pages: 1 }
  if (path.includes('FeeDashboardPage')) props.dashboard = { total_amount: 100, paid_amount: 50, pending_amount: 50, total_records: 1, inspection_contact_count: 1, fee_type_summaries: [{ fee_type: '注册', amount: 100 }], payment_status_summaries: [{ status: '待支付', amount: 50 }], year_summaries: [{ year: 2026, amount: 100 }], year_fee_type_summaries: [], agency_summaries: [{ agency_name: '机构A', amount: 100 }] }
  if (path.includes('FeeLedgerPage')) props.entries = [{ ...record, fee_type: '注册', payment_status: '待支付', amount: 100, currency: 'CNY', agency_name: '机构A' }]
  if (path.includes('InspectionContactsPage')) props.contacts = [{ ...record, test_item: '检测', agency_name: '机构A', contact_name: '张三', contact_phone: '13800000000', contact_email: 'a@example.com' }]
  if (path.includes('KnowledgeArticleDetail')) props.article = { ...record, id: 'article-1', title: '法规', content: '# 内容', tags: '质量,GMP' }
  if (path.includes('ProjectDashboardPage')) props.overview = { module_name: '注册项目', modules: [] }
  if (path.includes('ProjectLedgerDashboardPage')) props.overview = { sheets: [{ sheet_key: 'projects', sheet_name: '项目', columns: [{ label: '项目', key: 'project' }], records: [record], summary: { total_records: 1, records_with_history: 1 } }] }
  if (path.includes('ProjectLedgerSheetPage')) props.detail = { sheet_key: 'projects', sheet_name: '项目', columns: [{ label: '项目', key: 'project_name' }], records: [record], total: 1, page: 1, page_size: 20, total_pages: 1 }
  if (path.includes('RegistrationDashboardCharts') && exportName === 'RegistrationSummaryHero') props.metrics = []
  if (path.includes('RegulationTrackerPage')) Object.assign(props, { initialResult: { items: [], total: 0, page: 1, pageSize: 20, totalPages: 0 }, initialNotificationSettings: { is_enabled: false, recent_days: 7, recipient_open_id: null, recipient_name: null, recipient_department: null, schedule_time: '09:00', pending_count: 0 }, notificationRecipients: [] })
  if (path.includes('ValidationAuditDetailClient')) Object.assign(props, { task: { id: 'task-1', task_name: '验证审计', status: 'pending', audit_mode: 'full' }, initialFiles: [], initialIssues: [], initialReport: null })
  return props
}

function isComponentExport(name: string): boolean {
  if (['normalizeLedgerRecord', 'replaceLedgerMainRecord', 'upsertLedgerUpdateRecord', 'removeLedgerUpdateRecord'].includes(name)) {
    return false
  }
  return name === 'default' || /(?:Page|Client|Panel|Table|Modal|Drawer|Form|View|Dashboard|Landing|List|Card|Section|Content|Sheet|Record|Detail|Config|Settings|Evaluation|Attachment|Ledger|Report|Editor|Provider|Banner|Header|Tree|Chart|Contacts|Qualification|Application|Management|Standard|Limit|Article|Overview|Hero)$/.test(name)
}

function renderComponent(component: unknown, props: Record<string, unknown>): string {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return renderToStaticMarkup(
    React.createElement(
      QueryClientProvider,
      { client: queryClient },
      React.createElement(AntdApp, null, React.createElement(component as React.ElementType, props)),
    ),
  )
}

describe('migrated component surface coverage', () => {
  it('renders the default surface of every migrated component module', async () => {
    const failures: string[] = []
    let candidates = 0
    for (const [path, load] of Object.entries(moduleLoaders)) {
      if (path.endsWith('/index.ts') || path.endsWith('/index.tsx')) continue
      if (path.includes('ReturnApplicationPage')) continue
      const loadedModule = await load()
      for (const [exportName, component] of Object.entries(loadedModule)) {
        if (!isComponentExport(exportName) || typeof component !== 'function') continue
        candidates += 1
        try {
          const html = renderComponent(component, propsFor(path, exportName))
          expect(html.length).toBeGreaterThan(0)
        } catch (error) {
          failures.push(`${path}#${exportName}: ${error instanceof Error ? error.message : String(error)}`)
        }
      }
    }
    expect(candidates).toBeGreaterThan(100)
    expect(failures).toEqual([])
  }, 120000)
})
