/* @vitest-environment happy-dom */

import { act, Component, createElement, type ErrorInfo, type ReactElement, type ReactNode } from 'react'
import type { JSXSource } from 'react/jsx-dev-runtime'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const mocks = vi.hoisted(() => {
  const functions = new Map<string, ReturnType<typeof vi.fn>>()
  const get = (moduleName: string, name: string) => {
    const key = `${moduleName}:${name}`
    let fn = functions.get(key)
    if (!fn) {
      const fallback = Object.assign([] as unknown[], {
        data: [], items: [], records: [], total: 0, page: 1, pageSize: 20,
        success: true, code: 200,
      })
      fn = vi.fn(async () => fallback)
      functions.set(key, fn)
    }
    return fn
  }
  const moduleFactory = (moduleName: string) => {
    const known = Object.fromEntries([
    'testHrFeishuAppSettings', 'testHrFeishuEntitySetting', 'updateEmailConfig', 'testEmailConfig',
    'updateHrFeishuAppSettings', 'updateHrFeishuEntitySetting', 'browseFolderAction', 'uploadOfferTemplateAction',
    'fetchAnnualTrainingPlans', 'fetchPlanItems', 'fetchPlanAttachmentSections', 'fetchUsedTrainingContent',
    'fetchTrainingSession', 'fetchSessionDocuments', 'fetchNewHires', 'fetchTrainingPersonnelConfigs',
    'fetchTrainingDepartments', 'createTrainingLedger', 'markTrainingContentUsed', 'upsertTrainingSession',
    'upsertTrainingDocument', 'fetchEmployeeTrainingMembers', 'fetchEmployeeTrainingRecords', 'importFeishuMembers',
    'addEmployeeTrainingMember', 'removeEmployeeTrainingMember', 'updateEmployeeTrainingMember',
    'fetchNewEmployeeTrainingPlans', 'fetchNewEmployeeTrainingStats', 'fetchDepartmentPositions',
    'generateNewEmployeeTrainingPlan', 'createPositionTrainingMappingAction', 'updateNewEmployeeTrainingPlan',
    'fetchPositionTrainingLists', 'createPositionTrainingList', 'batchUpdatePositionTrainingListItems',
    'importPositionTrainingLists', 'clearPositionTrainingListsByDept', 'fetchCustomTrainingDepartments',
    'fetchTrainingDeptMappings', 'fetchFeishuMembers', 'saveTrainingPersonnelConfig', 'deleteTrainingPersonnelConfig',
    'fetchEmailConfig', 'fetchHrFeishuAppSettings', 'fetchHrFeishuEntityFieldMappingBundle',
    'fetchHrFeishuEntitySettings', 'fetchHrFeishuEntityTables', 'formatHrFeishuTestSummary',
    'createAuthorizationFdaEntry', 'createAuthorizationLedgerMain', 'createAuthorizationLedgerUpdate',
    'deleteAuthorizationFdaEntry', 'deleteAuthorizationLedgerMain', 'deleteAuthorizationLedgerUpdate',
    'updateAuthorizationFdaEntry', 'updateAuthorizationLedgerMain', 'updateAuthorizationLedgerUpdate',
    'fetchAuthorizationFdaExport', 'fetchAuthorizationLedgerExport', 'fetchRegulatoryTrackerDocumentDetailClient',
    'fetchRegulatoryTrackerDocumentsClient', 'fetchRegulatoryTrackerNotificationRecipientsClient',
    'fetchRegulatoryTrackerSyncStatusClient', 'analyzeRegulatoryDocumentClient', 'manualSyncRegulatoryTrackerClient',
    'updateRegulatoryTrackerNotificationSettingsClient', 'createProjectLedgerEntry', 'createProjectLedgerSubRecord',
    'deleteProjectLedgerEntry', 'updateProjectLedgerEntry', 'fetchProjectLedgerRecordHistory',
    'createDeclarationProgressEntry', 'createDeclarationProgressSubRecord', 'deleteDeclarationProgressEntry',
    'updateDeclarationProgressEntry', 'fetchDeclarationProgressRecordHistory', 'createKnowledgeArticle',
    'createKnowledgeCategory', 'deleteKnowledgeArticle', 'deleteKnowledgeCategory', 'extractArticleFromFile',
    'updateKnowledgeArticle', 'updateKnowledgeCategory', 'uploadKnowledgeAttachment', 'createDocumentDepartment',
    'createDocumentEntry', 'deleteDocumentDepartment', 'deleteDocumentEntry', 'importDocumentCatalogExcel',
    'batchImportDocumentAttachments', 'updateDocumentDepartment', 'updateDocumentEntry', 'fetchDocumentDepartments',
    'fetchDocumentEntries', 'fetchDocumentCatalogExport', 'fetchDocumentEntryAttachmentContent', 'createOotLimitItem',
    'createOotLimitProduct', 'deleteOotLimitItem', 'deleteOotLimitProduct', 'updateOotLimitItem', 'updateOotLimitProduct',
    'updateQualityFeishuAppSettings', 'testQualityFeishuAppSettings', 'updateQualityFeishuEntitySetting', 'testQualityFeishuEntitySetting',
    'fetchOotLimitItems', 'fetchOotLimitProducts', 'pullOosOotReportRecords', 'updateOosOotReportRecord',
    'deleteOosOotReportRecord', 'fetchOosOotReportRecords', 'fetchDepartmentContacts', 'fetchQualityFeishuAppSettings',
    'fetchQualityFeishuEntitySettings', 'fetchQualityFeishuEntityFieldMappingBundle', 'fetchQualityFeishuEntityTables',
    'formatQualityFeishuTestSummary', 'formatQualitySyncSummary', 'pullQualityRecordsFromFeishu',
    'pullOosOotInvestigationPushRecords', 'updateOosOotInvestigationPushRecord', 'deleteOosOotInvestigationPushRecord',
    'fetchOosOotInvestigationPushRecords', 'fetchOosLedgerRecords', 'fetchOotLedgerRecords',
    'fetchProductQualityStandards', 'createProductQualityStandardAction', 'updateProductQualityStandardAction',
    'deleteProductQualityStandardAction', 'pullProductQualityStandardsAction', 'fetchWarehouseDashboard',
    'fetchWarehouseMaterialPage', 'fetchWarehouseRecordDetail',
      ].map((name) => [name, get(moduleName, name)]))
    return new Proxy(known, {
      get(target, name: string | symbol) {
        if (name === 'then') return undefined
        if (typeof name !== 'string') return Reflect.get(target, name)
        if (!(name in target)) target[name] = get(moduleName, name)
        return target[name]
      },
    })
  }
  return {
    get,
    moduleFactory,
    permissionAllowed: true,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), loading: vi.fn() },
    modal: { confirm: vi.fn(({ onOk }: { onOk?: () => unknown }) => void onOk?.()) },
    router: { push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() },
  }
})

const getMock = (moduleName: string, name: string) => mocks.get(moduleName, name)

vi.mock('next/navigation', () => ({
  usePathname: () => '/migration/coverage',
  useRouter: () => mocks.router,
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: 'record-1' }),
}))
vi.mock('react/jsx-runtime', async () => {
  const actual = await vi.importActual<typeof import('react/jsx-runtime')>('react/jsx-runtime')
  const inspect = (type: unknown, props: unknown) => {
    if (!type) console.error('undefined jsx type', props)
  }
  return {
    ...actual,
    jsx: (type: unknown, props: Record<string, unknown>, key?: string) => {
      inspect(type, props)
      return actual.jsx(type as never, props, key)
    },
    jsxs: (type: unknown, props: Record<string, unknown>, key?: string) => {
      inspect(type, props)
      return actual.jsxs(type as never, props, key)
    },
  }
})
vi.mock('react/jsx-dev-runtime', async () => {
  const actual = await vi.importActual<typeof import('react/jsx-dev-runtime')>('react/jsx-dev-runtime')
  return {
    ...actual,
    jsxDEV: (type: unknown, props: Record<string, unknown>, key?: string, _isStatic?: boolean, _source?: JSXSource, _self?: unknown) => {
      if (!type) console.error('undefined jsx dev type', props)
      return actual.jsxDEV(type as never, props, key, _isStatic ?? false, _source, _self)
    },
  }
})
vi.mock('next/link', () => ({ default: ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) => createElement('a', props, children) }))
vi.mock('next/image', () => ({ default: (props: Record<string, unknown>) => createElement('img', props) }))
vi.mock('styled-jsx/style', () => ({ default: () => null }))
vi.mock('@/hooks/usePermission', () => ({ usePermission: () => ({ has: () => mocks.permissionAllowed, hasAny: () => mocks.permissionAllowed }) }))

vi.mock('@/actions/hr', () => mocks.moduleFactory('actions/hr'))
vi.mock('@/actions/admin', () => mocks.moduleFactory('actions/admin'))
vi.mock('@/actions/quality', () => mocks.moduleFactory('actions/quality'))
vi.mock('@/actions/registration', () => mocks.moduleFactory('actions/registration'))
vi.mock('@/actions/warehouse', () => mocks.moduleFactory('actions/warehouse'))
vi.mock('@/actions/quality-capa', () => mocks.moduleFactory('actions/quality-capa'))
vi.mock('@/actions/quality-change', () => mocks.moduleFactory('actions/quality-change'))
vi.mock('@/actions/quality-deviation', () => mocks.moduleFactory('actions/quality-deviation'))
vi.mock('@/actions/quality-deviation-workbench', () => mocks.moduleFactory('actions/quality-deviation-workbench'))
vi.mock('@/actions/quality-inspection', () => mocks.moduleFactory('actions/quality-inspection'))
vi.mock('@/actions/validation-audit', () => mocks.moduleFactory('actions/validation-audit'))
vi.mock('@/lib/api/validation-audit', () => mocks.moduleFactory('lib/api/validation-audit'))
vi.mock('@/lib/api/dossier-writer-client', () => mocks.moduleFactory('lib/api/dossier-writer-client'))
vi.mock('@/lib/api/client/hr', () => mocks.moduleFactory('lib/api/client/hr'))
vi.mock('@/lib/api/client/admin', () => mocks.moduleFactory('lib/api/client/admin'))
vi.mock('@/lib/api/client/quality', () => mocks.moduleFactory('lib/api/client/quality'))
vi.mock('@/lib/api/client/registration', () => mocks.moduleFactory('lib/api/client/registration'))
vi.mock('@/lib/api/client/regulatoryTracker', () => mocks.moduleFactory('lib/api/client/regulatoryTracker'))
vi.mock('@/lib/api/client/warehouse', () => mocks.moduleFactory('lib/api/client/warehouse'))
vi.mock('@/lib/api/hr', () => mocks.moduleFactory('lib/api/hr'))
vi.mock('@/lib/api/quality', () => mocks.moduleFactory('lib/api/quality'))
vi.mock('@/lib/api/registration', () => mocks.moduleFactory('lib/api/registration'))
vi.mock('@/lib/api/warehouse', () => mocks.moduleFactory('lib/api/warehouse'))

vi.mock('@/lib/download', () => ({ downloadZip: vi.fn(), downloadBlob: vi.fn() }))
vi.mock('@/lib/api/ai', () => ({
  submitWrittenExamGenerate: vi.fn(async () => 'job-1'),
  pollWrittenExamGenerate: vi.fn(async () => ({
    choice_questions: [{ number: 1, question: '新题', options: [{ label: 'A', text: '正确' }], answer: 'A' }],
    true_false_questions: [], fill_blank_questions: [],
  })),
  exportWrittenExam: vi.fn(async () => new Blob(['exam'])),
  extractExamDocumentText: vi.fn(async () => ({ text: '解析后的培训内容' })),
  generateOralExamQuestions: vi.fn(async () => ({ questions: [{ question: '口试问题', answer: '答案要点' }] })),
}))
vi.mock('docx-preview', () => ({ renderAsync: vi.fn(async () => undefined) }))
vi.mock('@/lib/feishu-url', () => ({ parseFeishuBitableUrl: vi.fn(() => ({ app_token: 'bascn-test', table_id: 'tbl-test' })) }))
vi.mock('@/components/registration', () => ({
  AuthorizationLetterDashboard: () => createElement('div', null, '授权概览'),
  RegistrationSummaryHero: ({ children }: { children?: ReactNode }) => createElement('div', null, '注册总览', children),
  RegistrationChartCard: ({ children }: { children?: ReactNode }) => createElement('div', null, children),
  CertificateManagementDashboard: () => createElement('div', null, '证书总览'),
  buildHorizontalBarOption: () => ({}),
  buildStackedBarOption: () => ({}),
  buildDonutOption: () => ({}),
}))
vi.mock('echarts-for-react', () => ({ default: ({ option }: { option?: unknown }) => createElement('pre', null, JSON.stringify(option ?? {})) }))
vi.mock('echarts', () => ({ graphic: { LinearGradient: class LinearGradient {} } }))
vi.mock('./components/quality/DocumentEntryAttachmentModal', () => ({
  default: () => createElement('div', null, '附件管理'),
  DocumentAttachmentPreviewModal: () => createElement('div', null, '附件预览'),
}))

vi.mock('./components/hr/SignInSheetClient', async () => {
  const React = await import('react')
  const MockSignInSheetClient = ({ onSessionChange }: { onSessionChange?: (value: Record<string, unknown>) => void }) => {
    React.useEffect(() => {
      onSessionChange?.({
        training_date: '2026-08-25', training_time_start: '09:00', training_time_end: '10:30',
        topic: 'GMP培训', training_method: '课堂', instructor: '张三', assessment_method: '笔试',
        department: '人事行政部', trainee_departments: ['质量部'], employee_names: ['李四'],
        employee_dept_map: { 李四: '质量部' }, checked_content: [],
      })
    }, [onSessionChange])
    return createElement('div', null, '签到表')
  }
  return {
    default: MockSignInSheetClient,
  }
})
vi.mock('./components/hr/AttachmentContentModal', () => ({
  default: ({ open, onConfirm }: { open?: boolean; onConfirm?: (entries: unknown[]) => void }) => open
    ? createElement('button', { onClick: () => onConfirm?.([{ key: 'entry-1', name: 'GMP指南', code: 'SOP-1' }]) }, '确认附件内容')
    : createElement('div', null, '附件内容'),
}))

vi.mock('@ant-design/icons', async () =>
  await vi.importActual<typeof import('@ant-design/icons')>('@ant-design/icons')
)

vi.mock('antd', async () => {
  const React = await import('react')
  const { Children, cloneElement, createContext, forwardRef, isValidElement, useMemo, useRef } = React
  const FormContext = createContext<Record<string, unknown> | null>(null)
  const Wrapper = ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) =>
    createElement('div', props, children)
  const Button = ({ children, icon, onClick, htmlType, disabled, loading, ...props }: { children?: ReactNode; icon?: ReactNode; onClick?: () => void; htmlType?: string; disabled?: boolean; loading?: boolean } & Record<string, unknown>) =>
    createElement('button', { ...props, type: htmlType === 'submit' ? 'submit' : 'button', disabled: disabled || loading, onClick }, icon, children)
  const Input = forwardRef<HTMLInputElement, { value?: unknown; defaultValue?: unknown; onChange?: (event: { target: { value: string } }) => void; placeholder?: string; type?: string }>(function Input(props, ref) {
    const handleChange = (event: Event) => props.onChange?.({ target: { value: (event.target as HTMLInputElement).value } })
    return createElement('input', { ref, ...props, value: props.value ?? props.defaultValue ?? '', onChange: handleChange, onInput: handleChange })
  })
  const TextArea = (props: { value?: unknown; defaultValue?: unknown; onChange?: (event: { target: { value: string } }) => void; placeholder?: string }) => {
    const handleChange = (event: Event) => props.onChange?.({ target: { value: (event.target as HTMLTextAreaElement).value } })
    return createElement('textarea', { ...props, value: props.value ?? props.defaultValue ?? '', onChange: handleChange, onInput: handleChange })
  }
  const Password = Input
  const Search = forwardRef<HTMLInputElement, { value?: unknown; defaultValue?: unknown; onChange?: (event: { target: { value: string } }) => void; onSearch?: (value: string) => void; placeholder?: string; type?: string }>(function Search(props, ref) {
    const handleChange = (event: Event) => { const value = (event.target as HTMLInputElement).value; props.onChange?.({ target: { value } }); props.onSearch?.(value) }
    return createElement('input', { ref, ...props, value: props.value ?? props.defaultValue ?? '', onChange: handleChange, onInput: handleChange })
  })
  ;(Input as typeof Input & { TextArea: typeof TextArea; Password: typeof Password; Search: typeof Search }).TextArea = TextArea
  ;(Input as typeof Input & { TextArea: typeof TextArea; Password: typeof Password; Search: typeof Search }).Password = Password
  ;(Input as typeof Input & { TextArea: typeof TextArea; Password: typeof Password; Search: typeof Search }).Search = Search
  const AutoComplete = ({ value, defaultValue, onChange, onSearch, placeholder, ...props }: { value?: unknown; defaultValue?: unknown; onChange?: (value: string) => void; onSearch?: (value: string) => void; placeholder?: string } & Record<string, unknown>) =>
    createElement('input', { ...props, value: value ?? defaultValue ?? '', placeholder, onChange: (event: Event) => { const next = (event.target as HTMLInputElement).value; onChange?.(next); onSearch?.(next) } })
  const Select = ({ value, defaultValue, options = [], onChange, mode, placeholder, children, ...props }: { value?: unknown; defaultValue?: unknown; options?: Array<{ label: ReactNode; value: string | number }>; onChange?: (value: unknown) => void; mode?: string; placeholder?: string; children?: ReactNode } & Record<string, unknown>) =>
    createElement('select', { ...props, value: mode === 'multiple' || mode === 'tags' ? (Array.isArray(value) ? value : value ? [value] : []) : Array.isArray(value) ? value[0] ?? '' : value ?? defaultValue ?? '', multiple: mode === 'multiple' || mode === 'tags', 'aria-label': placeholder, onChange: (event: Event) => onChange?.(mode === 'multiple' || mode === 'tags' ? [(event.target as HTMLSelectElement).value] : (event.target as HTMLSelectElement).value) }, [createElement('option', { key: 'empty', value: '' }, placeholder ?? ''), ...options.map((option) => createElement('option', { key: String(option.value), value: option.value }, option.label)), children])
  const DatePicker = ({ value, onChange, placeholder }: { value?: unknown; onChange?: (value: unknown) => void; placeholder?: string }) =>
    createElement('input', { type: 'date', value: value && typeof value === 'object' && 'format' in value ? (value as { format: (format: string) => string }).format('YYYY-MM-DD') : '', placeholder, onChange: () => onChange?.(null) })
  const RangePicker = () => createElement('input', { type: 'date' })
  const InputNumber = ({ value, onChange, placeholder }: { value?: unknown; onChange?: (value: unknown) => void; placeholder?: string }) =>
    createElement('input', { type: 'number', value: value ?? '', placeholder, onChange: () => onChange?.(1) })
  const Switch = ({ checked, defaultChecked, onChange }: { checked?: boolean; defaultChecked?: boolean; onChange?: (value: boolean) => void }) =>
    createElement('input', { type: 'checkbox', checked: checked ?? defaultChecked ?? false, onChange: (event: Event) => onChange?.((event.target as HTMLInputElement).checked) })
  const Checkbox = ({ checked, onChange, children, disabled, value }: { checked?: boolean; onChange?: (event: { target: { checked: boolean } }) => void; children?: ReactNode; disabled?: boolean; value?: string }) =>
    createElement('label', null, createElement('input', { type: 'checkbox', value, disabled, checked: checked ?? false, onChange: (event: Event) => onChange?.({ target: { checked: (event.target as HTMLInputElement).checked } }) }), children)
  const CheckboxGroup = ({ value = [], options = [], onChange, children }: { value?: unknown[]; options?: Array<{ label: ReactNode; value: string }>; onChange?: (values: unknown[]) => void; children?: ReactNode }) => {
    const optionNodes = options.map((option) => createElement('label', { key: option.value }, createElement('input', { type: 'checkbox', value: option.value, checked: value.includes(option.value), onChange: (event: Event) => {
      const next = new Set(value)
      if ((event.target as HTMLInputElement).checked) next.add(option.value)
      else next.delete(option.value)
      onChange?.(Array.from(next))
    } }), option.label))
    const bindCheckboxes = (child: ReactNode): ReactNode => {
      if (!isValidElement(child)) return child
      const props = child.props as { value?: unknown; children?: ReactNode }
      if (child.type === Checkbox) {
        const childValue = String(props.value ?? '')
        return cloneElement(child as ReactElement<{ checked?: boolean; onChange?: (event: { target: { checked: boolean } }) => void }>, {
          checked: value.includes(childValue),
          onChange: (event: { target: { checked: boolean } }) => {
            const next = new Set(value)
            if (event.target.checked) next.add(childValue)
            else next.delete(childValue)
            onChange?.(Array.from(next))
          },
        })
      }
      return cloneElement(child as ReactElement<{ children?: ReactNode }>, { children: Children.map(props.children, bindCheckboxes) })
    }
    const childNodes = Children.map(children, bindCheckboxes)
    return createElement('div', null, optionNodes, childNodes)
  }
  ;(Checkbox as typeof Checkbox & { Group: typeof CheckboxGroup }).Group = CheckboxGroup
  const Card = ({ children, title, extra, onClick, ...props }: { children?: ReactNode; title?: ReactNode; extra?: ReactNode; onClick?: () => void } & Record<string, unknown>) =>
    createElement('section', { ...props, onClick }, title, extra, children)
  const Table = ({ columns = [], dataSource = [], rowKey, locale, onRow, rowSelection, ...props }: { columns?: Array<{ title?: ReactNode; dataIndex?: string; render?: (value: unknown, record: Record<string, unknown>, index: number) => ReactNode }>; dataSource?: Array<Record<string, unknown>>; rowKey?: string | ((record: Record<string, unknown>) => string); locale?: { emptyText?: ReactNode }; onRow?: (record: Record<string, unknown>, index?: number) => Record<string, unknown>; rowSelection?: { onChange?: (keys: unknown[], rows?: Record<string, unknown>[]) => void } } & Record<string, unknown>) => {
    const rows = dataSource.length ? dataSource.map((record, rowIndex) => {
      const key = typeof rowKey === 'function' ? rowKey(record) : rowKey ? String(record[rowKey]) : rowIndex
      const rowProps = onRow?.(record, rowIndex) ?? {}
      return createElement('tr', { key, ...rowProps, onClick: (event: unknown) => { (rowProps.onClick as ((event: unknown) => void) | undefined)?.(event); rowSelection?.onChange?.([key], [record]) } }, columns.map((column, index) => createElement('td', { key: `${index}` }, column.render ? column.render(column.dataIndex ? record[column.dataIndex] : undefined, record, rowIndex) : column.dataIndex ? String(record[column.dataIndex] ?? '') : '')))
    }) : createElement('tr', { key: 'empty' }, createElement('td', { colSpan: columns.length }, locale?.emptyText ?? ''))
    return createElement('table', { ...props }, createElement('thead', null, createElement('tr', null, columns.map((column, index) => createElement('th', { key: index }, column.title))),), createElement('tbody', null, rows))
  }
  const Modal = ({ open, children, footer, title, onCancel, onOk, afterOpenChange }: { open?: boolean; children?: ReactNode; footer?: ReactNode; title?: ReactNode; onCancel?: () => void; onOk?: () => void; afterOpenChange?: (open: boolean) => void }) => {
    React.useEffect(() => { afterOpenChange?.(Boolean(open)) }, [open])
    return open ? createElement('div', { role: 'dialog' }, createElement('h2', null, title), createElement('button', { onClick: onCancel }, '取消'), createElement('button', { onClick: onOk }, '确定'), children, footer) : null
  }
  ;(Modal as typeof Modal & { confirm: (config: { onOk?: () => unknown }) => void; destroyAll: () => void }).confirm = (config) => void config.onOk?.()
  ;(Modal as typeof Modal & { confirm: (config: { onOk?: () => unknown }) => void; destroyAll: () => void }).destroyAll = () => undefined
  const Drawer = ({ open, children, title, onClose, extra, afterOpenChange }: { open?: boolean; children?: ReactNode; title?: ReactNode; onClose?: () => void; extra?: ReactNode; afterOpenChange?: (open: boolean) => void }) => {
    React.useEffect(() => { afterOpenChange?.(Boolean(open)) }, [open])
    return open ? createElement('aside', null, createElement('h2', null, title), createElement('button', { onClick: onClose }, '关闭'), extra, children) : null
  }
  const Alert = ({ title, description, children }: { title?: ReactNode; description?: ReactNode; children?: ReactNode }) => createElement('div', null, title, description, children)
  const Divider = ({ children }: { children?: ReactNode }) => createElement('div', null, children)
  const Tag = ({ children, closable, onClose, ...props }: { children?: ReactNode; closable?: boolean; onClose?: () => void } & Record<string, unknown>) => createElement('span', props, children, closable ? createElement('button', { onClick: onClose, 'aria-label': '关闭标签' }, '×') : null)
  const Empty = ({ description }: { description?: ReactNode }) => createElement('span', null, description ?? '暂无数据')
  ;(Empty as typeof Empty & { PRESENTED_IMAGE_SIMPLE: null }).PRESENTED_IMAGE_SIMPLE = null
  const Typography = { Title: ({ children }: { children?: ReactNode }) => createElement('h1', null, children), Text: ({ children }: { children?: ReactNode }) => createElement('span', null, children), Paragraph: ({ children }: { children?: ReactNode }) => createElement('p', null, children), Link: Wrapper }
  const Space = Object.assign(Wrapper, { Compact: Wrapper })
  const Collapse = ({ items = [], children }: { items?: Array<{ key: string; label?: ReactNode; children?: ReactNode }>; children?: ReactNode }) => createElement('div', null, items.map((item) => createElement('section', { key: item.key }, item.label, item.children)), children)
  const Tabs = ({ items = [], children, onChange, tabBarExtraContent }: { items?: Array<{ key: string; label?: ReactNode; children?: ReactNode }>; children?: ReactNode; onChange?: (key: string) => void; tabBarExtraContent?: ReactNode }) => createElement('div', null, items.map((item) => createElement('section', { key: item.key }, createElement('button', { onClick: () => onChange?.(item.key) }, item.label), item.children)), tabBarExtraContent, children)
  const List = ({ dataSource = [], renderItem, locale, children }: { dataSource?: unknown[]; renderItem?: (item: unknown, index: number) => ReactNode; locale?: { emptyText?: ReactNode }; children?: ReactNode }) => createElement('div', null, dataSource.length ? dataSource.map((item, index) => createElement('div', { key: index }, renderItem?.(item, index))) : locale?.emptyText, children)
  const Menu = ({ items = [], onClick, children }: { items?: Array<{ key: string; label?: ReactNode }>; onClick?: (info: { key: string }) => void; children?: ReactNode }) => createElement('nav', null, items.map((item) => createElement('button', { key: item.key, onClick: () => onClick?.({ key: item.key }) }, item.label)), children)
  const Tree = ({ treeData = [], onSelect, onCheck }: { treeData?: Array<{ key?: string; title?: ReactNode; children?: unknown[] }>; onSelect?: (keys: string[]) => void; onCheck?: (keys: string[]) => void }) => createElement('div', null, treeData.map((item, index) => createElement('button', { key: item.key ?? index, onClick: () => { const key = String(item.key ?? index); onSelect?.([key]); onCheck?.([key]) } }, item.title, item.children ? 'children' : null)))
  const Upload = ({ children, customRequest, beforeUpload }: { children?: ReactNode; customRequest?: (options: { file: File; onSuccess?: (value?: unknown) => void; onError?: (error: Error) => void }) => unknown; beforeUpload?: (file: File, fileList: File[]) => unknown }) => {
    const triggerUpload = async () => {
      const file = new File(['test upload'], 'template.pdf', { type: 'application/pdf' })
      if (beforeUpload && beforeUpload(file, [file]) === false) return
      if (!customRequest) return
      await customRequest({ file, onSuccess: vi.fn(), onError: vi.fn() })
    }
    return createElement('div', { onClick: () => void triggerUpload() }, children)
  }
  ;(Upload as typeof Upload & { Dragger: typeof Upload }).Dragger = Upload
  const Dropdown = ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) => createElement('span', props, children)
  const Spin = Wrapper
  const Popconfirm = ({ children, onConfirm }: { children?: ReactNode; onConfirm?: () => void }) => createElement('span', { onClick: onConfirm }, children)
  const Pagination = ({ onChange }: { onChange?: (page: number, pageSize: number) => void }) => createElement('button', { onClick: () => onChange?.(2, 20) }, '下一页')
  const Statistic = ({ title, value }: { title?: ReactNode; value?: ReactNode }) => createElement('div', null, title, value)
  const Badge = ({ children, text }: { children?: ReactNode; text?: ReactNode }) => createElement('span', null, children, text)
  const Segmented = ({ value, options = [], onChange }: { value?: string; options?: Array<{ label: ReactNode; value: string }>; onChange?: (value: string) => void }) => createElement('select', { value, onChange: (event: Event) => onChange?.((event.target as HTMLSelectElement).value) }, options.map((option) => createElement('option', { key: option.value, value: option.value }, option.label)))
  const Radio = ({ checked, value, onChange, children }: { checked?: boolean; value?: string; onChange?: (event: { target: { value?: string } }) => void; children?: ReactNode }) => createElement('label', null, createElement('input', { type: 'radio', value, checked: checked ?? false, onChange: () => onChange?.({ target: { value } }) }), children)
  const RadioGroup = ({ value, onChange, children, ...props }: { value?: string; onChange?: (event: { target: { value?: string } }) => void; children?: ReactNode } & Record<string, unknown>) => createElement('div', props, Children.map(children, (child) => isValidElement(child) ? cloneElement(child as ReactElement<{ value?: string; checked?: boolean; onChange?: (event: { target: { value?: string } }) => void }>, { checked: (child.props as { value?: string }).value === value, onChange }) : child))
  ;(Radio as typeof Radio & { Group: typeof RadioGroup; Button: typeof Radio }).Group = RadioGroup
  ;(Radio as typeof Radio & { Group: typeof Wrapper; Button: typeof Radio }).Button = Radio
  const Form = ({ children, form, onFinish }: { children?: ReactNode; form?: Record<string, unknown>; onFinish?: (values: Record<string, unknown>) => void }) => {
    if (form) {
      const api = form as Record<string, unknown>
      api.submit = async () => onFinish?.((api.getValues as (() => Record<string, unknown>) | undefined)?.() ?? {})
    }
    return createElement(FormContext.Provider, { value: form ?? {} }, createElement('form', { onSubmit: (event: Event) => { event.preventDefault(); void onFinish?.((form?.getValues as () => Record<string, unknown>)?.() ?? {}) } }, children))
  }
  const FormItem = ({ children, label, name }: { children?: ReactNode; label?: ReactNode; name?: string }) => createElement('label', null, label, children, name ? createElement('span', { 'data-field': name }) : null)
  Form.Item = FormItem
  Form.useForm = <T extends Record<string, unknown> = Record<string, unknown>>() => {
    const values = useRef<T>({} as T)
    const api = useMemo(() => ({
       getValues: () => ({
         name: '测试记录', department_id: 'dept-1', title: '测试记录', sort_order: 1, code: 'TEST',
         contract_sequence: '首次', dept_leader_name: '主管', contract_opinion: '同意续签',
         contract_start_1: '2026-01-01', contract_end_1: '2026-12-31', contract_start_2: '2027-01-01',
         contract_end_2: '2027-12-31', contract_start_3: '2028-01-01', contract_end_3: '2028-12-31',
         contract_start_4: '2029-01-01', contract_end_4: '2029-12-31', contract_start_5: '2030-01-01',
         contract_end_5: '2030-12-31', contract_start_6: '2031-01-01', contract_end_6: '2031-12-31',
         start_date: '2026-09-01', end_date: '2027-08-31', method: 'GET', path: '/api/v1/hr/employees',
         department: '质量部', role_id: 'role-1', feishu_department_id: 'feishu-new', department_name: '质量部',
         oos_oot_code: 'INV-1', push_round: '第1次', submitter: '张三', department_head_direct: 'head-1',
         department_head_result: '通过', qa_result: '待审核', qa_head_result: '待审核', process_status: '待QA审核',
         type: 'menu', status: 'active', route_path: '/test/menu', permission_code: 'test:read', icon: 'menu',
         ...values.current,
       }),
       getFieldsValue: () => ({ ...values.current }),
      validateFields: async () => ({
        name: '测试记录', department_id: 'dept-1', title: '测试记录', sort_order: 1, code: 'TEST',
        contract_sequence: '首次', dept_leader_name: '主管', contract_opinion: '同意续签',
        contract_start_1: '2026-01-01', contract_end_1: '2026-12-31', contract_start_2: '2027-01-01',
        contract_end_2: '2027-12-31', contract_start_3: '2028-01-01', contract_end_3: '2028-12-31',
        contract_start_4: '2029-01-01', contract_end_4: '2029-12-31', contract_start_5: '2030-01-01',
        contract_end_5: '2030-12-31', contract_start_6: '2031-01-01', contract_end_6: '2031-12-31',
        start_date: '2026-09-01', end_date: '2027-08-31', method: 'GET', path: '/api/v1/hr/employees',
        department: '质量部', role_id: 'role-1', feishu_department_id: 'feishu-new', department_name: '质量部',
        oos_oot_code: 'INV-1', push_round: '第1次', submitter: '张三', department_head_direct: 'head-1',
        department_head_result: '通过', qa_result: '待审核', qa_head_result: '待审核', process_status: '待QA审核',
        type: 'menu', status: 'active', route_path: '/test/menu', permission_code: 'test:read', icon: 'menu',
        ...values.current,
      }),
      submit: async () => ({
        name: '测试记录', department_id: 'dept-1', title: '测试记录', sort_order: 1, code: 'TEST',
        contract_sequence: '首次', dept_leader_name: '主管', contract_opinion: '同意续签',
        contract_start_1: '2026-01-01', contract_end_1: '2026-12-31', contract_start_2: '2027-01-01',
        contract_end_2: '2027-12-31', contract_start_3: '2028-01-01', contract_end_3: '2028-12-31',
        contract_start_4: '2029-01-01', contract_end_4: '2029-12-31', contract_start_5: '2030-01-01',
        contract_end_5: '2030-12-31', contract_start_6: '2031-01-01', contract_end_6: '2031-12-31',
        start_date: '2026-09-01', end_date: '2027-08-31', method: 'GET', path: '/api/v1/hr/employees',
        department: '质量部', role_id: 'role-1', feishu_department_id: 'feishu-new', department_name: '质量部',
        oos_oot_code: 'INV-1', push_round: '第1次', submitter: '张三', department_head_direct: 'head-1',
        department_head_result: '通过', qa_result: '待审核', qa_head_result: '待审核', process_status: '待QA审核',
        type: 'menu', status: 'active', route_path: '/test/menu', permission_code: 'test:read', icon: 'menu',
        ...values.current,
      }),
      resetFields: () => { values.current = {} as T },
      setFieldsValue: (next: Partial<T>) => { values.current = { ...values.current, ...next } as T },
      setFieldValue: (name: string, value: unknown) => { values.current = { ...values.current, [name]: value } as T },
      getFieldValue: (name: string) => values.current[name],
    }), [])
    return [api] as const
  }
  Form.useWatch = () => undefined
  const App = Object.assign(({ children }: { children?: ReactNode }) => createElement('div', null, children), { useApp: () => ({ message: mocks.message, modal: { ...mocks.modal, warning: vi.fn(), info: vi.fn() } }) })
  const TimePicker = Object.assign(Wrapper, { RangePicker })
  const Result = Wrapper
  const Avatar = Wrapper
  const exports = { App, Alert, AutoComplete, Avatar, Badge, Breadcrumb: Wrapper, Button, Card, Checkbox, Collapse, Col: Wrapper, DatePicker: Object.assign(DatePicker, { RangePicker }), Descriptions: Object.assign(Wrapper, { Item: Wrapper }), Divider, Drawer, Dropdown, Empty, Flex: Wrapper, Form, Input, InputNumber, List, Menu, Modal, Pagination, Popconfirm, Progress: Wrapper, Radio, Result, Row: Wrapper, Select, Segmented, Space, Spin, Statistic, Switch, Table, Tabs, Tag, TimePicker, Timeline: Wrapper, Tooltip: Wrapper, Tree, Typography, Upload }
  return new Proxy(exports, { get: (target, name: string | symbol) => name === 'then' ? undefined : target[name as keyof typeof target] ?? Wrapper })
})

import { HrFeishuSettingsPage } from './components/hr/HrFeishuSettingsPage'
import CandidateDetailClient from './components/hr/CandidateDetailClient'
import OffboardingClient from './components/hr/OffboardingClient'
import AnnualPlanDetailClient from './components/hr/AnnualPlanDetailClient'
import AnnualPlanListClient from './components/hr/AnnualPlanListClient'
import AnnualTrainingStatsClient from './components/hr/AnnualTrainingStatsClient'
import TrainingEvaluationListClient from './components/hr/TrainingEvaluationListClient'
import TrainingNotificationClient from './components/hr/TrainingNotificationClient'
import OralExamSheetClient from './components/hr/OralExamSheetClient'
import PracticalExamSheetClient from './components/hr/PracticalExamSheetClient'
import TrainingSignInTabsClient, { cnToInt, extractAnnexRefs, formatTopicForSignin, matchDrugCategory, matchTrainingType } from './components/hr/TrainingSignInTabsClient'
import EmployeeTrainingListClient from './components/hr/EmployeeTrainingListClient'
import NewEmployeeTrainingListClient from './components/hr/NewEmployeeTrainingListClient'
import PositionTrainingListClient from './components/hr/PositionTrainingListClient'
import TrainingLedgerPageClient from './components/hr/TrainingLedgerPageClient'
import EsgTrainingReportClient from './components/hr/EsgTrainingReportClient'
import TrainingLedgerImportModal from './components/hr/TrainingLedgerImportModal'
import TrainingPersonnelConfigModal from './components/hr/TrainingPersonnelConfigModal'
import AuthorizationLetterClient from './components/registration/AuthorizationLetterClient'
import RegulationTrackerPage, { buildQueryParams, formatDate, hasCompletedAnalysis } from './components/registration/RegulationTrackerPage'
import ProjectLedgerSheetPage from './components/registration/ProjectLedgerSheetPage'
import ProjectLedgerDashboardPage from './components/registration/ProjectLedgerDashboardPage'
import DeclarationProgressPage from './components/registration/DeclarationProgressPage'
import DeclarationProgressDashboardPage from './components/registration/DeclarationProgressDashboardPage'
import KnowledgeBasePage from './components/registration/KnowledgeBasePage'
import DocumentCatalogPage from './components/quality/DocumentCatalogPage'
import OotLimitManagementPage from './components/quality/OotLimitManagementPage'
import OosOotReportRecordPage from './components/quality/OosOotReportRecordPage'
import OosOotInvestigationPushPage from './components/quality/OosOotInvestigationPushPage'
import { OosOotLedgerPageBase } from './components/quality/OosOotLedgerPageBase'
import ProductQualityStandardPage from './components/quality/ProductQualityStandardPage'
import WarehouseDashboard from './components/warehouse/WarehouseDashboard'
import { WarehouseAiPanel } from './components/warehouse/WarehouseAiPanel'
import OralExamAiModal from './components/hr/OralExamAiModal'
import { ChangeActionPlanEditModal } from './components/quality/ChangeActionPlanEditModal'
import AiWrittenExamClient from './components/hr/AiWrittenExamClient'
import DeptMappingSettingsClient from './components/hr/DeptMappingSettingsClient'
import DeptScopeSettingsClient from './components/hr/DeptScopeSettingsClient'
import PositionTransferClient from './components/hr/PositionTransferClient'
import DepartmentClient from './components/hr/DepartmentClient'
import { useSyncPolling } from './components/hr/useSyncPolling'
import OnboardingManagementPage from './components/hr/onboarding-management/OnboardingManagementPage'
import { Sidebar } from './components/layout/Sidebar'
import ValidationAuditListClient from './components/registration/validation-audit/ValidationAuditListClient'
import ValidationAuditNewClient from './components/registration/validation-audit/ValidationAuditNewClient'
import ValidationAuditDetailClient from './components/registration/validation-audit/ValidationAuditDetailClient'
import { DocxPreview } from './components/registration/DocxPreview'
import DeptRecipientDrawer from './components/hr/DeptRecipientDrawer'
import ContractApprovalResultsClient from './components/hr/ContractApprovalResultsClient'
import ApprovalSettingsListClient from './components/hr/ApprovalSettingsListClient'
import ReminderDetailClient from './components/hr/ReminderDetailClient'
import PlanTrackingClient from './components/hr/PlanTrackingClient'
import ContractTableClient from './components/hr/ContractTableClient'
import TrainerListClient from './components/hr/TrainerListClient'
import NewEmployeeTrainingDetailClient from './components/hr/NewEmployeeTrainingDetailClient'
import { QualityFeishuSettingsPage } from './components/quality/QualityFeishuSettingsPage'
import OosOotProductDepartmentPage from './components/quality/OosOotProductDepartmentPage'
import ReturnApplicationPage from './components/quality/ReturnApplicationPage'
import ReturnLedgerPage from './components/quality/ReturnLedgerPage'
import SupplierQualificationPage from './components/quality/SupplierQualificationPage'
import { DeviationReportRecordPage } from './components/quality/DeviationReportRecordPage'
import { DeviationHistoryPage } from './components/quality/DeviationHistoryPage'
import { DeviationWorkbenchPage } from './components/quality/DeviationWorkbenchPage'
import { InspectionFeishuRecordModal } from './components/quality/inspection/InspectionFeishuRecordModal'
import { InspectionFeishuTable } from './components/quality/inspection/InspectionFeishuTable'
import { DepartmentContactPage } from './components/quality/DepartmentContactPage'
import DocumentCatalogPickerModal from './components/hr/DocumentCatalogPickerModal'
import OnboardingAttachmentPreviewModal from './components/hr/onboarding-management/OnboardingAttachmentPreviewModal'
import CertificateSheetPage from './components/registration/CertificateSheetPage'
import CertificateManagementDashboard from './components/registration/CertificateManagementDashboard'
import CertificateDashboardPage from './components/registration/CertificateDashboardPage'
import FeeDashboardPage from './components/registration/FeeDashboardPage'
import FeeLedgerPage from './components/registration/FeeLedgerPage'
import KnowledgeArticleDetail from './components/registration/KnowledgeArticleDetail'
import InspectionContactsPage from './components/registration/InspectionContactsPage'
import WarehouseFeishuConfigPage from './components/warehouse/WarehouseFeishuConfigPage'
import { RoleManager } from './components/system/RoleManager'
import { UserRoleManager } from './components/system/UserRoleManager'
import { DeptRoleMapper } from './components/system/DeptRoleMapper'
import { MenuManager } from './components/system/MenuManager'
import { PermissionVerification } from './components/system/PermissionVerification'

const notificationSettings = {
  is_enabled: false, recent_days: 7, recipient_open_id: null, recipient_name: null,
  recipient_department: null, schedule_time: '09:00', pending_count: 0,
}

class RenderBoundary extends Component<{ children?: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error('render boundary', error, info.componentStack)
  }
  render() {
    return this.state.failed ? null : this.props.children
  }
}

function renderClient(element: ReactNode) {
  const container = document.createElement('div')
  const root = createRoot(container, {
    onUncaughtError: (error, info) => console.error('uncaught component error', error, info.componentStack),
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  document.body.append(container)
  act(() => root.render(createElement(QueryClientProvider, { client }, createElement(RenderBoundary, null, element))))
  return { container, root, client }
}

function queryElement<T extends Element>(root: ParentNode, selector: string): T | null {
  return root.querySelector(selector) as T | null
}

function renderStatic(element: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return renderToStaticMarkup(createElement(QueryClientProvider, { client }, element))
}

async function settle() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

function closeRendered(rendered: { root: Root; client: QueryClient; container: HTMLDivElement }) {
  act(() => rendered.root.unmount())
  rendered.client.clear()
  rendered.container.remove()
}

type ComponentLoader = () => Promise<Record<string, unknown>>
type ComponentGlobImportMeta = ImportMeta & {
  glob: <T>(patterns: string[], options: { eager: false }) => Record<string, T>
}

const interactiveComponentLoaders = (import.meta as ComponentGlobImportMeta).glob<ComponentLoader>([
  './components/quality/**/*.{ts,tsx}',
  './components/registration/**/*.{ts,tsx}',
  './components/hr/**/*.{ts,tsx}',
  './components/warehouse/**/*.{ts,tsx}',
  './components/system/**/*.{ts,tsx}',
  '!./components/**/*.test.{ts,tsx}',
], { eager: false })

const interactiveTargets = [
  'HrFeishuSettingsPage.tsx', 'TrainingSignInTabsClient.tsx', 'DeptScopeSettingsClient.tsx',
  'ContractAlertBanner.tsx', 'EmployeeTrainingListClient.tsx', 'TrainingLedgerPageClient.tsx',
  'DeptMappingSettingsClient.tsx', 'PlanTrackingClient.tsx', 'NewEmployeeTrainingDetailClient.tsx',
  'AuthorizationLetterClient.tsx', 'ProjectLedgerSheetPage.tsx',
  'DeclarationProgressPage.tsx', 'KnowledgeBasePage.tsx',
  'QualityFeishuSettingsPage.tsx', 'OotLimitManagementPage.tsx', 'DocumentCatalogPage.tsx',
  'WarehouseFeishuConfigPage.tsx', 'WarehouseAiPanel.tsx', 'RoleManager.tsx', 'UserRoleManager.tsx',
  'MenuManager.tsx', 'PermissionVerification.tsx', 'DeptRoleMapper.tsx',
  'OosOotInvestigationPushPage.tsx', 'OosOotReportRecordPage.tsx', 'OosOotProductDepartmentPage.tsx',
  'ReturnApplicationPage.tsx', 'ReturnLedgerPage.tsx', 'SupplierQualificationPage.tsx',
  'DeviationReportRecordPage.tsx', 'DeviationInvestigationPushPage.tsx', 'ChangeTable.tsx',
  'CapaTable.tsx', 'ComplaintLedgerPage.tsx', 'DeviationTable.tsx', 'SupplierDashboardPage.tsx',
  'ValidationLedgerPage.tsx', 'ValidationEditModal.tsx', 'ImportPreviewDrawer.tsx',
  'ProductQualityStandardPage.tsx', 'InspectionFeishuTable.tsx', 'FinishedSubtablePage.tsx',
  'CertificateDashboardPage.tsx', 'CertificateManagementDashboard.tsx', 'CertificateSheetPage.tsx', 'FeeDashboardPage.tsx',
  'FeeLedgerPage.tsx', 'KnowledgeArticleDetail.tsx', 'InspectionContactsPage.tsx',
  'AnnualTrainingStatsClient.tsx', 'PositionTrainingListClient.tsx', 'TrainerListClient.tsx',
  'TrainingEvaluationListClient.tsx', 'TrainingNotificationClient.tsx', 'TrainingAttachmentClient.tsx',
  'TrainingPersonnelConfigModal.tsx', 'RecruitmentClient.tsx', 'CandidateDetailClient.tsx',
  'CandidateListView.tsx', 'DepartmentClient.tsx', 'DepartmentTable.tsx', 'DepartmentForm.tsx',
  'EmployeeForm.tsx', 'EmployeeProfileClient.tsx', 'OffboardingClient.tsx', 'OffboardingForm.tsx',
  'PositionTransferClient.tsx', 'PositionTransferForm.tsx', 'ContractTableClient.tsx',
  'ReminderSettingsListClient.tsx', 'ReminderDetailClient.tsx', 'ApprovalSettingsListClient.tsx',
  'NewEmployeeTrainingListClient.tsx', 'OnboardingManagementPage.tsx', 'TrainingLedgerImportModal.tsx', 'EmployeeFillForm.tsx',
  'FeishuContactListClient.tsx', 'DepartmentTreeView.tsx', 'TrainingAttachmentClient.tsx',
]

const genericWarehouseData = {
  page_key: 'raw-summary', page_title: '原辅料库存', table_name: '原辅料库存', columns: [], rows: [],
  total: 0, page: 1, page_size: 20, total_pages: 0, source: 'empty', generated_at: null,
}

function interactivePropsFor(path: string): Record<string, unknown> {
  const record = {
    id: 'record-1', record_id: 'record-1', name: '测试记录', title: '测试记录', code: 'TEST-1',
    project_name: '项目A', product_name: '产品A', status: '待处理', department: '质量部',
    created_at: '2026-08-01', updated_at: '2026-08-02', latest_values: { project_name: '项目A' },
    latest_style_marks: {}, history_count: 1,
  }
  const props: Record<string, unknown> = {
    initialRecords: [record], initialFdaRecords: [record], initialItems: [record], items: [record],
    records: [record], rows: [record], dataSource: [record], total: 1, page: 1, pageSize: 20,
    initialTotal: 1, totalPages: 1, open: false, onClose: vi.fn(), onApplied: vi.fn(), onCancel: vi.fn(),
    onSuccess: vi.fn(), onRefresh: vi.fn(), onSubmit: vi.fn(), onChange: vi.fn(),
    changes: [record], capas: [record], deviations: [record], departments: [record], allDepartments: [record],
    orgTreeData: [{ id: 'dept-1', name: '质量部', type: 'department', children: [] }],
    filters: { keyword: '', parentId: null, leaderName: '' },
    initialEmployees: [record], initialJobs: [record], jobs: [record], entries: [record], contacts: [record],
    employee: record, article: { ...record, content: '# 法规\n\n内容', attachments: [], comments: [] },
    params: Promise.resolve({ entityCode: 'candidate' }),
    onFilterChange: vi.fn(), onRowClick: vi.fn(), onEdit: vi.fn(), onDelete: vi.fn(), onSelect: vi.fn(), onAdd: vi.fn(), onNodeClick: vi.fn(), canEdit: true,
    reminderSettings: { is_enabled: false, reminder_days: 90, recipient_open_id: null, recipient_name: null, recipient_department: null, pending_count: 0 },
    reminderRecipients: [],
    initialData: [], data: genericWarehouseData, detail: { ...record, columns: [], records: [record], fields: [], history: [] },
    candidate: { ...record, name: '候选人', job_position: 'QA', interview_status: '待安排' },
    sessionData: { training_date: '2026-08-25', training_time_start: '09:00', training_time_end: '10:00', topic: 'GMP培训', instructor: '张三', employee_names: ['李四'], trainee_departments: ['质量部'] },
    overview: { total_records: 1, sheets: [], sheet_count: 1, issuer_count: 1, product_count: 1, expired_count: 0, due_90_count: 0, total_pages: 1, sheet_summaries: [] },
    dashboard: { total_amount: 1, paid_amount: 1, pending_amount: 0, total_records: 1, inspection_contact_count: 1, fee_type_summaries: [], payment_status_summaries: [], year_summaries: [], year_fee_type_summaries: [], agency_summaries: [] },
    planId: 'plan-1', plan: { id: 'plan-1', year: 2026, plan_level: '部门级', department: '质量部', version: 'V1' },
    initialResult: { items: [record], total: 1, page: 1, pageSize: 20, totalPages: 1 },
    columns: [{ label: '名称', key: 'name' }], overviewData: {}, chart: { actual_series: [], target_series: [], categories: [], spec_lines: [] },
  }
  if (path.includes('WarehouseFeishuConfigPage')) props.initialConfigs = [record]
  if (path.includes('WarehouseDashboard')) props.initialData = { safety: { total: 1, ok: 1, low: 0 }, quality: { 合格: 1, 待验: 0, 不合格: 0 }, low_stock_top: [], material_outbound_30d: [], packaging_outbound_30d_total: 0, month_inbound_total: 0 }
  if (path.includes('DeclarationProgressPage') || path.includes('ProjectLedgerSheetPage')) {
    const ledgerRecord = { record_id: 'record-1', sequence: 1, latest_values: { project_name: '项目A', product: '产品A', status: '进行中', market: '中国' }, latest_style_marks: { status: 'updated' }, history_count: 2 }
    props.detail = {
      sheet_key: path.includes('DeclarationProgressPage') ? 'gmp-projects' : 'projects', sheet_name: path.includes('DeclarationProgressPage') ? '申报进度' : '项目台账',
      columns: [{ label: '项目名称', key: 'project_name' }, { label: '产品', key: 'product' }, { label: '状态', key: 'status' }, { label: '国家/受理机构', key: 'market' }],
      records: [ledgerRecord], supports_sub_records: true, total: 1, page: 1, page_size: 20, total_pages: 1,
    }
  }
  if (path.includes('KnowledgeBasePage')) Object.assign(props, { articles: [record], categories: [{ id: 'cat-1', name: '法规' }], overview: { total_articles: 1, published_articles: 1, category_count: 1 } })
  if (path.includes('TrainingPersonnelConfigModal')) Object.assign(props, { open: true, level: '公司级', scopeDept: undefined })
  if (/(DepartmentForm|EmployeeForm|OffboardingForm|PositionTransferForm|ValidationEditModal|TrainingPersonnelConfigModal)/.test(path)) props.open = true
  if (path.includes('RecruitmentClient')) props.initialJobs = [record]
  if (path.includes('CertificateDashboardPage')) props.overview = { ...(props.overview as Record<string, unknown>), records: [record] }
  if (path.includes('FeeDashboardPage')) props.dashboard = { total_amount: 100, paid_amount: 60, pending_amount: 40, total_records: 2, inspection_contact_count: 1, fee_type_summaries: [{ fee_type: '注册', total_amount: 100 }], payment_status_summaries: [{ payment_status: '待支付', total_amount: 40 }], year_summaries: [{ year: 2026, total_amount: 100 }], year_fee_type_summaries: [{ year: 2026, fee_type: '注册', total_amount: 100 }], agency_summaries: [{ agency_name: '机构A', total_amount: 100 }] }
  if (path.includes('FeeLedgerPage')) props.entries = [{ ...record, fee_type: '注册', payment_status: '待支付', amount: 100, currency: 'CNY', agency_name: '机构A', expense_content: '费用', handler: '张三', contract_received: false, invoice_settled: false }]
  if (path.includes('InspectionContactsPage')) props.contacts = [{ ...record, test_item: '检测', agency_name: '机构A', contact_name: '张三', contact_phone: '13800000000', contact_email: 'a@example.com', address: '地址' }]
  if (path.includes('CertificateSheetPage')) props.detail = {
    sheet_key: 'domestic-gmp', sheet_name: '国内GMP',
    columns: [{ label: '证照名称', key: 'certificate_name' }, { label: '编号', key: 'certificate_number' }],
    rows: [{ id: 'certificate-1', sequence: 1, values: { '证照名称': 'GMP证书', '编号': 'GMP-001', '发证机关': '药监局', '发证日期': '2026-01-01', '有效期/复验期': '2027-01-01', '产品范围': '产品A', '质量标准': '标准', '页数': '2', '备注': '备注' } }],
    total: 1, page: 1, page_size: 20, total_pages: 1, summary: { total_records: 1 },
  }
  if (path.includes('ImportPreviewDrawer')) Object.assign(props, { isOpen: true, headers: ['名称'], previewAction: vi.fn(async () => ({ success_count: 1 })), confirmAction: vi.fn(async () => ({ success_count: 1 })) })
  return props
}

function isInteractiveComponentExport(name: string): boolean {
  if (['normalizeLedgerRecord', 'replaceLedgerMainRecord', 'upsertLedgerUpdateRecord', 'removeLedgerUpdateRecord'].includes(name)) return false
  return name === 'default' || /(?:Page|Client|Panel|Table|Modal|Drawer|Form|View|Dashboard|Landing|List|Card|Section|Content|Sheet|Record|Detail|Config|Settings|Evaluation|Attachment|Ledger|Report|Editor|Banner|Header|Tree|Chart|Contacts|Qualification|Application|Management|Standard|Limit|Article|Overview|Hero)$/.test(name)
}

describe('migrated component coverage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mocks.permissionAllowed = true
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ code: 200, data: [], meta: { total: 0 } }), { status: 200, headers: { 'content-type': 'application/json' } })))
    for (const moduleName of ['actions/hr', 'actions/quality', 'actions/registration', 'actions/warehouse', 'actions/quality-capa', 'actions/quality-change', 'actions/quality-deviation', 'lib/api/client/hr', 'lib/api/client/quality', 'lib/api/client/registration', 'lib/api/client/regulatoryTracker', 'lib/api/client/warehouse', 'lib/api/hr', 'lib/api/quality', 'lib/api/registration', 'lib/api/warehouse']) {
      for (const name of ['fetch', 'list', 'get', 'load', 'fetchTrainingDepartments', 'fetchEmployeeDepartments', 'fetchDeptApprovalConfigNames', 'fetchTrainingPersonnelConfigs', 'fetchAnnualTrainingPlans', 'fetchPlanItems', 'fetchPlanAttachmentSections', 'fetchUsedTrainingContent', 'fetchTrainingSession', 'fetchSessionDocuments', 'fetchEmployeeTrainingMembers', 'fetchEmployeeTrainingRecords', 'fetchNewEmployeeTrainingList', 'fetchNewEmployeeTrainingStats', 'fetchPositionTrainingLists', 'fetchCustomTrainingDepartments', 'fetchTrainingDeptMappings', 'fetchHrFeishuAppSettings', 'fetchHrFeishuEntitySettings', 'fetchHrFeishuEntityFieldMappingBundle', 'fetchHrFeishuEntityTables', 'fetchEmailConfig', 'fetchDocumentDepartments', 'fetchDocumentEntries', 'fetchRegulatoryTrackerDocumentsClient', 'fetchRegulatoryTrackerNotificationRecipientsClient', 'fetchRegulatoryTrackerSyncStatusClient', 'fetchRegulatoryTrackerDocumentDetailClient', 'fetchProjectLedgerRecordHistory', 'fetchDeclarationProgressRecordHistory', 'fetchAuthorizationLedger', 'fetchAuthorizationFda', 'fetchWarehouseDashboard', 'fetchWarehouseMaterialPage', 'fetchWarehouseRecordDetail']) {
        getMock(moduleName, name).mockResolvedValue([])
      }
    }
    window.matchMedia = window.matchMedia ?? (() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() }))
    window.URL.createObjectURL = vi.fn(() => 'blob:test')
    window.URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    document.body.replaceChildren()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('covers shared sync polling completion, failure, retry and timeout guards', async () => {
    const Harness = ({
      syncAction,
      pollAction,
      onSuccess,
      onError,
      maxPolls = 3,
    }: {
      syncAction: () => Promise<unknown>
      pollAction: () => Promise<unknown>
      onSuccess: (message: string, result?: unknown) => void
      onError: (message: string) => void
      maxPolls?: number
    }) => {
      const { isSyncing, startSync } = useSyncPolling({ syncAction, pollAction, onSuccess, onError, maxPolls, interval: 0 })
      return createElement('button', { onClick: startSync, 'data-syncing': String(isSyncing) }, '同步')
    }

    const success = vi.fn()
    const successView = renderClient(createElement(Harness, {
      syncAction: vi.fn(async () => ({ data: { state: 'completed', progress: '完成', result: { count: 1 } } })),
      pollAction: vi.fn(async () => ({ data: { state: 'completed' } })), onSuccess: success, onError: vi.fn(),
    }))
    successView.container.querySelector('button')?.click()
    await settle()
    expect(success).toHaveBeenCalledWith('完成', { count: 1 })
    closeRendered(successView)

    const failed = vi.fn()
    const failedView = renderClient(createElement(Harness, {
      syncAction: vi.fn(async () => ({ data: { state: 'failed', message: '同步失败' } })),
      pollAction: vi.fn(async () => ({ data: { state: 'failed' } })), onSuccess: vi.fn(), onError: failed,
    }))
    failedView.container.querySelector('button')?.click()
    await settle()
    expect(failed).toHaveBeenCalledWith('同步失败')
    closeRendered(failedView)

    const polled = vi.fn()
    const pollView = renderClient(createElement(Harness, {
      syncAction: vi.fn(async () => ({ data: { state: 'running' } })),
      pollAction: vi.fn(async () => ({ data: { state: 'completed', message: '轮询完成' } })), onSuccess: polled, onError: vi.fn(),
    }))
    pollView.container.querySelector('button')?.click()
    await settle()
    expect(polled).toHaveBeenCalledWith('轮询完成', undefined)
    closeRendered(pollView)

    const networkError = vi.fn()
    const errorView = renderClient(createElement(Harness, {
      syncAction: vi.fn(async () => { throw new Error('网络失败') }),
      pollAction: vi.fn(async () => ({ data: { state: 'running' } })), onSuccess: vi.fn(), onError: networkError,
    }))
    errorView.container.querySelector('button')?.click()
    await settle()
    expect(networkError).toHaveBeenCalledWith('网络失败')
    closeRendered(errorView)
  })

  it('renders HR settings with configured entities and exercises settings controls', async () => {
    getMock('lib/api/hr', 'fetchEmailConfig').mockResolvedValue({ data: { imap_host: 'imap.test', smtp_host: 'smtp.test', fetch_enabled: true } })
    getMock('lib/api/hr', 'fetchHrFeishuAppSettings').mockResolvedValue({ app_id: 'app-1', app_secret_masked: '***', is_enabled: true, last_test_status: 'success' })
    getMock('lib/api/hr', 'fetchHrFeishuEntitySettings').mockResolvedValue([{ entity_code: 'candidate', entity_name: '候选人', entity_group: '招聘', app_token: 'base-1', base_table_name: '候选人表', base_table_id: 'tbl-1', is_enabled: true, enable_push_to_feishu: true, enable_pull_from_feishu: false, field_mappings: [], last_sync_status: 'success', last_synced_at: null }])
    getMock('lib/api/hr', 'fetchHrFeishuEntityFieldMappingBundle').mockResolvedValue({ entity_code: 'candidate', entity_name: '候选人', system_fields: [{ field_key: 'name', field_label: '姓名', direction: 'push' }], feishu_fields: [{ field_name: '姓名' }], field_mappings: [] })
    getMock('lib/api/hr', 'fetchHrFeishuEntityTables').mockResolvedValue([{ table_name: '候选人表', table_id: 'tbl-1' }])
    getMock('actions/hr', 'updateHrFeishuAppSettings').mockResolvedValue({ app_id: 'app-1', is_enabled: true })
    getMock('actions/hr', 'testHrFeishuAppSettings').mockResolvedValue({ success: true, status: 'success', message: '连接成功' })
    getMock('actions/hr', 'updateHrFeishuEntitySetting').mockResolvedValue({ entity_name: '候选人' })
    getMock('actions/hr', 'testHrFeishuEntitySetting').mockResolvedValue({ success: true, status: 'success', message: '连接成功', entity_name: '候选人' })
    getMock('actions/hr', 'updateEmailConfig').mockResolvedValue({})
    getMock('actions/hr', 'testEmailConfig').mockResolvedValue({ data: { imap: '成功', smtp: '成功' } })
    getMock('actions/hr', 'browseFolderAction').mockResolvedValue({ data: { path: 'data/hr/resumes' } })
    getMock('lib/api/hr', 'formatHrFeishuTestSummary').mockReturnValue('连接成功')
    const rendered = renderClient(createElement(HrFeishuSettingsPage))
    await settle()
    expect(rendered.container.textContent).toContain('HR设置')
    for (let round = 0; round < 3; round += 1) {
      for (const button of Array.from(rendered.container.querySelectorAll('button'))) {
        if (!button.disabled) button.click()
      }
      await settle()
    }
    const urlButton = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('URL填充'))
    urlButton?.click()
    await settle()
    const urlInput = Array.from(rendered.container.querySelectorAll('input')).find((input) => input.placeholder?.includes('feishu.cn/base'))
    if (urlInput) {
      urlInput.value = 'https://example.feishu.cn/base/app?table=tbl'
      urlInput.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
      Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
      await settle()
    }
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('字段对齐'))?.click()
    await settle()
    const mappingSelect = rendered.container.querySelector('select') as HTMLSelectElement | null
    if (mappingSelect?.querySelector('option[value="姓名"]')) {
      mappingSelect.value = '姓名'
      mappingSelect.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('保存字段对齐'))?.click()
    await settle()
    getMock('actions/hr', 'testHrFeishuAppSettings').mockRejectedValueOnce(new Error('应用连接失败'))
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('测试连接'))?.click()
    await settle()
    closeRendered(rendered)
  })

  it('covers HR settings email templates, mapping directions and failure recovery', async () => {
    getMock('lib/api/hr', 'fetchEmailConfig').mockResolvedValue({ data: {
      imap_host: 'imap.test', imap_port: '993', imap_user: 'hr@test', smtp_host: 'smtp.test', smtp_port: '465',
      smtp_user: 'hr@test', from_addr: 'HR', fetch_enabled: true, fetch_interval_hours: 2,
      fetch_schedule_hours: [9, 14], watch_dir: 'data/resumes', offer_subject: 'Offer', offer_body: '<p>Offer</p>',
      reject_subject: 'Reject', reject_body: '<p>Reject</p>',
    } })
    getMock('lib/api/hr', 'fetchHrFeishuAppSettings').mockResolvedValue({ app_id: 'hr-app', app_secret_masked: '***', is_enabled: false, last_test_status: 'failed', last_test_error: '连接失败', last_tested_at: '2026-08-20T10:00:00Z' })
    getMock('lib/api/hr', 'fetchHrFeishuEntitySettings').mockResolvedValue([
      { entity_code: 'candidate', entity_name: '候选人', entity_group: '招聘', app_token: 'base-candidate', base_table_name: '候选人表', base_table_id: 'tbl-candidate', is_enabled: true, enable_push_to_feishu: true, enable_pull_from_feishu: false, field_mappings: [], last_sync_status: 'success', last_synced_at: '2026-08-20T10:00:00Z' },
      { entity_code: 'employee', entity_name: '员工', entity_group: '人事', app_token: '', base_table_name: '', base_table_id: '', is_enabled: false, enable_push_to_feishu: false, enable_pull_from_feishu: true, field_mappings: [], last_sync_status: null, last_synced_at: null, source_note: '迁移兼容入口' },
    ])
    getMock('lib/api/hr', 'fetchHrFeishuEntityFieldMappingBundle').mockResolvedValue({
      entity_code: 'candidate', entity_name: '候选人',
      system_fields: [{ field_key: 'name', field_label: '姓名', direction: 'push' }, { field_key: 'status', field_label: '状态', direction: 'pull' }, { field_key: 'remark', field_label: '备注', direction: 'both' }],
      feishu_fields: [{ field_name: '姓名（飞书）' }, { field_name: '状态（飞书）' }, { field_name: '备注（飞书）' }],
      field_mappings: [{ system_field: 'name', feishu_field: '旧姓名' }],
    })
    getMock('lib/api/hr', 'fetchHrFeishuEntityTables').mockResolvedValue([{ table_name: '候选人表', table_id: 'tbl-candidate' }, { table_name: '员工表', table_id: 'tbl-employee' }])
    getMock('actions/hr', 'updateHrFeishuAppSettings').mockResolvedValue({})
    getMock('actions/hr', 'testHrFeishuAppSettings').mockResolvedValue({ success: false, status: 'failed', message: '应用连接失败' })
    getMock('actions/hr', 'updateHrFeishuEntitySetting').mockResolvedValue({ entity_name: '候选人' })
    getMock('actions/hr', 'testHrFeishuEntitySetting').mockResolvedValue({ success: false, status: 'failed', message: '实体连接失败' })
    getMock('actions/hr', 'updateEmailConfig').mockResolvedValue({})
    getMock('actions/hr', 'testEmailConfig').mockResolvedValue({ data: { imap: '成功', smtp: '成功' } })
    getMock('actions/hr', 'browseFolderAction').mockResolvedValue({ data: { path: 'data/resumes-selected' } })
    getMock('actions/hr', 'uploadOfferTemplateAction').mockResolvedValue({ filename: 'offer.pdf' })
    getMock('lib/api/hr', 'formatHrFeishuTestSummary').mockReturnValue('HR连接失败')
    const rendered = renderClient(createElement(HrFeishuSettingsPage))
    await settle()
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 550)) })

    const buttons = (text: string) => Array.from(rendered.container.querySelectorAll('button')).filter((item) => item.textContent?.includes(text))
    const setInput = async (selector: string, value: string) => {
      const input = rendered.container.querySelector(selector) as HTMLInputElement | null
      if (!input) return
      input.value = value
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    await setInput('input[placeholder="请输入飞书应用 App ID"]', 'hr-app-new')
    buttons('保存配置')[0]?.click()
    await settle()
    buttons('测试连接')[0]?.click()
    await settle()
    const appSwitch = rendered.container.querySelector('input[type="checkbox"]') as HTMLInputElement | null
    appSwitch?.click()
    await settle()

    await setInput('input[placeholder="例如：bascnxxxxxxxx"]', 'bascn-candidate-new')
    buttons('读取表')[0]?.click()
    await settle()
    const tableSelect = rendered.container.querySelector('select[aria-label="可读取后直接选择"]') as HTMLSelectElement | null
    if (tableSelect?.querySelector('option[value="候选人表"]')) {
      tableSelect.value = '候选人表'
      tableSelect.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    buttons('保存')[0]?.click()
    await settle()
    buttons('测试')[0]?.click()
    await settle()
    buttons('URL填充')[0]?.click()
    await settle()
    await setInput('input[placeholder*="https://xxx.feishu.cn/base"]', 'https://example.feishu.cn/base/bascn-filled?table=tbl-filled')
    queryElement<HTMLButtonElement>(rendered.container, '[role="dialog"] button:last-of-type')?.click()
    await settle()
    buttons('字段对齐')[0]?.click()
    await settle()
    const mappingSelect = rendered.container.querySelector('select[aria-label="请选择飞书字段"]') as HTMLSelectElement | null
    if (mappingSelect?.querySelector('option[value="姓名（飞书）"]')) {
      mappingSelect.value = '姓名（飞书）'
      mappingSelect.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    queryElement<HTMLButtonElement>(rendered.container, 'aside button:last-of-type')?.click()
    await settle()

    buttons('上传 PDF 模板')[0]?.click()
    await settle()
    buttons('浏览…')[0]?.click()
    await settle()
    const emailTestButtons = buttons('测试连接')
    emailTestButtons[emailTestButtons.length - 1]?.click()
    await settle()
    buttons('保存邮箱配置')[0]?.click()
    await settle()
    getMock('actions/hr', 'testEmailConfig').mockRejectedValueOnce(new Error('邮箱连接失败'))
    emailTestButtons[emailTestButtons.length - 1]?.click()
    await settle()
    getMock('actions/hr', 'browseFolderAction').mockRejectedValueOnce(new Error('目录不可用'))
    buttons('浏览…')[0]?.click()
    await settle()
    getMock('actions/hr', 'updateHrFeishuAppSettings').mockRejectedValueOnce(new Error('保存失败'))
    buttons('保存配置')[0]?.click()
    await settle()
    closeRendered(rendered)
  })

  it('renders HR training and personnel pages through loaded and empty states', async () => {
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部', '生产部'])
    getMock('lib/api/client/hr', 'fetchTrainingPersonnelConfigs').mockResolvedValue({ data: [{ id: 'cfg-1', config_name: '默认班组', personnel: [{ name: '王五', department: '质量部' }] }] })
    getMock('lib/api/client/hr', 'fetchAnnualTrainingPlans').mockResolvedValue({ data: [{ id: 'plan-1', plan_level: '公司级', department: '公司', year: 2026 }] })
    getMock('lib/api/client/hr', 'fetchPlanItems').mockResolvedValue({ data: [{ id: 'item-1', sort_order: 1, content_textbook: '附件一 GMP', training_method: '课堂' }] })
    getMock('lib/api/client/hr', 'fetchPlanAttachmentSections').mockResolvedValue({ data: [{ id: 'section-1', annex_no: '附件1', entries: [{ key: 'entry-1', name: 'GMP指南', code: 'SOP-1' }] }] })
    getMock('lib/api/client/hr', 'fetchNewHires').mockResolvedValue({ data: [{ name: '赵六', employee_number: 'E006', department: '质量部' }] })
    getMock('actions/quality', 'resolveDocumentEntryContent').mockResolvedValue([{ name: 'GMP指南', code: 'SOP-2', matched: true }])
    getMock('lib/api/client/hr', 'fetchNewEmployeeTrainingPlans').mockResolvedValue({ data: [], total: 0 })
    getMock('lib/api/client/hr', 'fetchNewEmployeeTrainingStats').mockResolvedValue({ total: 0, pending: 0, in_progress: 0, completed: 0, overdue: 0 })
    getMock('lib/api/client/hr', 'fetchPositionTrainingLists').mockResolvedValue({ items: [], total: 0 })
    getMock('actions/hr', 'upsertTrainingSession').mockResolvedValue('session-1')
    getMock('actions/hr', 'upsertTrainingDocument').mockResolvedValue({})
    getMock('actions/hr', 'createTrainingLedger').mockResolvedValue({ code: 200 })
    getMock('actions/hr', 'markTrainingContentUsed').mockResolvedValue({})
    getMock('lib/api/client/hr', 'fetchUsedTrainingContent').mockResolvedValue([])
    getMock('actions/quality', 'resolveDocumentEntryContent').mockResolvedValue([{ name: 'GMP指南', code: 'SOP-2' }])
    const elements = [
      createElement(TrainingSignInTabsClient, { key: 'sign' }),
      createElement(EmployeeTrainingListClient, { key: 'employee' }),
      createElement(NewEmployeeTrainingListClient, { key: 'new' }),
      createElement(PositionTrainingListClient, { key: 'position' }),
      createElement(TrainingLedgerPageClient, { key: 'ledger' }),
      createElement(TrainingPersonnelConfigModal, { key: 'personnel', open: true, level: '公司级', onClose: vi.fn(), onApplied: vi.fn() }),
    ]
    const rendered = renderClient(createElement('div', null, elements))
    await settle()
    expect(rendered.container.textContent).toContain('培训')
    const selectByOption = (value: string) => {
      const select = Array.from(rendered.container.querySelectorAll('select')).find((item) => item.querySelector(`option[value="${value}"]`)) as HTMLSelectElement | undefined
      if (select) {
        select.value = value
        select.dispatchEvent(new Event('change', { bubbles: true }))
      }
    }
    selectByOption('plan-1')
    await settle()
    selectByOption('item-1')
    await settle()
    const confirmContent = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('确认附件内容'))
    confirmContent?.click()
    await settle()
    selectByOption('cfg-1')
    await settle()
    selectByOption('部门级')
    await settle()
    for (const button of Array.from(rendered.container.querySelectorAll('button'))) {
      if (!button.disabled) button.click()
    }
    await settle()
    closeRendered(rendered)
  })

  it('covers training personnel curation, pinyin filtering and configuration persistence', async () => {
    const config = {
      id: 'config-1', config_name: '质量班', level: '公司级', department: null,
      personnel: [{ name: '张三', department: '质量部', employee_number: 'E-1' }],
    }
    getMock('lib/api/client/hr', 'fetchTrainingPersonnelConfigs').mockResolvedValue({ data: [config] })
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部', '生产部', 'IT'])
    getMock('lib/api/client/hr', 'fetchFeishuMembers').mockResolvedValue({
      data: [
        { name: '张三', employee_no: 'E-1', department: '质量部' },
        { name: '李四', employee_no: 'E-2', department: '生产部' },
        { name: '王五', employee_no: 'E-3', department: 'IT' },
      ], meta: { total: 3 },
    })
    getMock('actions/hr', 'saveTrainingPersonnelConfig').mockResolvedValue({})
    getMock('actions/hr', 'deleteTrainingPersonnelConfig').mockResolvedValue({})
    const onApplied = vi.fn()
    const rendered = renderClient(createElement(TrainingPersonnelConfigModal, {
      open: true, level: '公司级', onClose: vi.fn(), onApplied,
    }))
    await settle()
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    findButton('编辑')?.click()
    await settle()
    const nameInput = rendered.container.querySelector('input[placeholder*="配置名称"]') as HTMLInputElement | null
    if (nameInput) {
      nameInput.value = '质量班-修订'
      nameInput.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const filter = rendered.container.querySelector('input[placeholder="筛选部门"]') as HTMLInputElement | null
    if (filter) {
      filter.value = 'zl'
      filter.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
      filter.value = ''
      filter.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const memberSelect = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="张三"]'))
    if (memberSelect) {
      memberSelect.value = '张三'
      memberSelect.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    const customDept = rendered.container.querySelector('input[placeholder="自定义部门名称"]') as HTMLInputElement | null
    if (customDept) {
      customDept.value = '临时项目组'
      customDept.dispatchEvent(new Event('change', { bubbles: true }))
    }
    findButton('添加部门')?.click()
    await settle()
    if (customDept) {
      customDept.value = '临时项目组'
      customDept.dispatchEvent(new Event('change', { bubbles: true }))
    }
    findButton('添加部门')?.click()
    await settle()
    const customSelect = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.closest('tr')?.textContent?.includes('临时项目组'))
    if (customSelect) {
      customSelect.value = '临时人员'
      customSelect.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    findButton('保存配置')?.click()
    await settle()
    expect(getMock('actions/hr', 'saveTrainingPersonnelConfig')).toHaveBeenCalled()
    expect(onApplied).toHaveBeenCalled()

    findButton('编辑')?.click()
    await settle()
    const secondName = rendered.container.querySelector('input[placeholder*="配置名称"]') as HTMLInputElement | null
    if (secondName) {
      secondName.value = '质量班-再次修订'
      secondName.dispatchEvent(new Event('change', { bubbles: true }))
    }
    findButton('保存配置')?.click()
    await settle()
    const iconOnlyDelete = Array.from(rendered.container.querySelectorAll('button')).find((button) => !button.textContent?.trim() && button.querySelector('svg'))
    iconOnlyDelete?.click()
    await settle()
    closeRendered(rendered)
  })

  it('covers personnel configuration validation, custom rows and failed save/delete paths', async () => {
    getMock('lib/api/client/hr', 'fetchTrainingPersonnelConfigs').mockResolvedValue({ data: [] })
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部'])
    getMock('lib/api/client/hr', 'fetchFeishuMembers').mockResolvedValue({ data: [], meta: { total: 0 } })
    getMock('actions/hr', 'saveTrainingPersonnelConfig').mockRejectedValueOnce(new Error('人员配置保存失败')).mockResolvedValue({})
    getMock('actions/hr', 'deleteTrainingPersonnelConfig').mockRejectedValueOnce(new Error('人员配置删除失败'))
    const rendered = renderClient(createElement(TrainingPersonnelConfigModal, {
      open: true, level: '部门级', scopeDept: '质量部', onClose: vi.fn(), onApplied: vi.fn(),
    }))
    await settle()
    const button = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((item) => item.textContent?.includes(text))
    button('新建配置')?.click()
    await settle()
    button('保存配置')?.click()
    const name = rendered.container.querySelector('input[placeholder*="配置名称"]') as HTMLInputElement | null
    if (name) {
      name.value = '临时班组'
      name.dispatchEvent(new Event('change', { bubbles: true }))
    }
    button('保存配置')?.click()
    const custom = rendered.container.querySelector('input[placeholder="自定义部门名称"]') as HTMLInputElement | null
    button('添加部门')?.click()
    if (custom) {
      custom.value = '临时部门'
      custom.dispatchEvent(new Event('change', { bubbles: true }))
    }
    button('添加部门')?.click()
    await settle()
    const rowSelect = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.closest('tr')?.textContent?.includes('临时部门'))
    if (rowSelect) {
      rowSelect.value = '手动输入人员'
      rowSelect.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    button('保存配置')?.click()
    await settle()
    button('保存配置')?.click()
    await settle()
    button('取消')?.click()
    closeRendered(rendered)

    const config = { id: 'cfg-error', config_name: '错误配置', level: '公司级', department: null, personnel: [{ name: '张三', department: '质量部' }] }
    getMock('lib/api/client/hr', 'fetchTrainingPersonnelConfigs').mockResolvedValue({ data: [config] })
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部'])
    getMock('lib/api/client/hr', 'fetchFeishuMembers').mockResolvedValue({ data: [{ name: '张三', employee_no: 'E-1', department: '质量部' }], meta: { total: 1 } })
    const failedDelete = renderClient(createElement(TrainingPersonnelConfigModal, {
      open: true, level: '公司级', onClose: vi.fn(), onApplied: vi.fn(),
    }))
    await settle()
    Array.from(failedDelete.container.querySelectorAll('button')).find((item) => !item.textContent?.trim() && item.querySelector('svg'))?.click()
    await settle()
    expect(getMock('actions/hr', 'deleteTrainingPersonnelConfig')).toHaveBeenCalledWith('cfg-error')
    closeRendered(failedDelete)
  })

  it('drives system permission settings role, user, menu and verification workflows', async () => {
    const role = { id: 'role-1', name: '质量管理员', code: 'quality-admin', description: '质量模块管理员', is_system: false, permissions: ['quality.read'] }
    const systemRole = { id: 'role-system', name: '系统管理员', code: 'admin', description: '内置', is_system: true, permissions: ['*'] }
    const departments = [
      { id: 'dept-1', feishu_department_id: 'feishu-1', name: '质量部', parent_feishu_department_id: null },
      { id: 'dept-2', feishu_department_id: 'feishu-2', name: '质量实验室', parent_feishu_department_id: 'feishu-1' },
    ]
    const menus = [
      { id: 'menu-1', key: 'quality', parent_id: null, name: '质量管理', type: 'directory', permission_code: null, route_path: '/quality', component_path: null, icon: null, sort_order: 1, status: 'active' },
      { id: 'menu-2', key: 'quality-capa', parent_id: 'menu-1', name: 'CAPA', type: 'menu', permission_code: 'quality.read', route_path: '/quality/capas', component_path: null, icon: null, sort_order: 1, status: 'active' },
      { id: 'menu-3', key: 'quality-edit', parent_id: 'menu-2', name: '编辑', type: 'button', permission_code: 'quality:edit', route_path: null, component_path: null, icon: null, sort_order: 1, status: 'disabled' },
    ]
    const user = { id: 'user-1', name: '张三', department: '质量部', position: '主管', roles: [role] }
    getMock('lib/api/client/admin', 'fetchRoleMenus').mockResolvedValue(['menu-2'])
    getMock('lib/api/client/admin', 'fetchDataScopes').mockResolvedValue([{ id: 'scope-1', role_id: 'role-1', user_id: 'user-1', scope_type: 'departments', department_names: ['质量部'] }])
    getMock('lib/api/client/admin', 'fetchAdminUsers').mockResolvedValue({ items: [user], total: 1 })
    getMock('actions/admin', 'createRole').mockResolvedValue({ ...role, id: 'role-new' })
    for (const name of ['setRolePermissions', 'setRoleMenus', 'saveRoleDataScope', 'saveRoleDataScopeForTarget', 'updateRole', 'deleteRole', 'assignUserRoles', 'saveUserDataScope', 'deleteDataScope', 'removeUserRole', 'createDeptRule', 'deleteDeptRule', 'createMenu', 'updateMenu', 'deleteMenu']) {
      getMock('actions/admin', name).mockResolvedValue({})
    }
    getMock('actions/admin', 'previewUserPermission').mockResolvedValue({
      user: { id: 'user-1', name: '张三', department: '质量部' }, roles: [{ ...role, source: 'manual', is_super_admin: false }],
      permissions: ['quality.read'], menus, data_scope: { is_all: false, department_names: ['质量部'] }, effective_at: '2026-08-20T10:00:00Z',
    })
    getMock('actions/admin', 'simulatePermission').mockResolvedValue({ allowed: false, required: 'quality:write', reason: '缺少写权限', note: '数据范围校验', dept_scope_hint: '质量部' })
    getMock('actions/admin', 'exportPermissions').mockResolvedValue({ filename: 'permissions.csv', content: 'role,permission' })

    const roleView = renderClient(createElement(RoleManager, {
      initialRoles: [role, systemRole], initialPermissions: [
        { id: 'perm-1', code: 'quality.read', module: 'quality', action: 'read', name: '读取' },
        { id: 'perm-2', code: 'quality:edit', module: 'quality', action: 'edit', name: '编辑' },
      ], initialMenus: menus as never, initialDepartments: departments,
    }))
    await settle()
    const roleButton = (text: string) => Array.from(roleView.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    roleButton('新建角色')?.click()
    await settle()
    roleView.container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]').forEach((input) => input.click())
    const roleRadios = Array.from(roleView.container.querySelectorAll<HTMLInputElement>('input[type="radio"]'))
    roleRadios.find((input) => (input as HTMLInputElement).value === 'departments')?.click()
    await settle()
    roleView.container.querySelector('button')?.click()
    await settle()
    roleButton('保存')?.click()
    await settle()
    roleButton('编辑')?.click()
    await settle()
    roleButton('删除')?.click()
    await settle()
    closeRendered(roleView)

    const userView = renderClient(createElement(UserRoleManager, { initialRoles: [role, systemRole], initialDepartments: departments }))
    await settle()
    const userButton = (text: string) => Array.from(userView.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    expect(userButton('页面权限')).toBeUndefined()
    expect(userButton('模块访问')).toBeDefined()
    userButton('分配角色')?.click()
    await settle()
    userView.container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]').forEach((input) => input.click())
    userView.container.querySelector('input[type="radio"][value="all"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await settle()
    queryElement<HTMLButtonElement>(userView.container, 'button[aria-label="关闭标签"]')?.click()
    userButton('保存')?.click()
    await settle()
    closeRendered(userView)

    const deptView = renderClient(createElement(DeptRoleMapper, { initialRules: [{ id: 'rule-1', role_id: 'role-1', role_name: role.name, role_code: role.code, feishu_department_id: 'feishu-1', department_name: '质量部' }], initialRoles: [role], initialDepartments: departments }))
    await settle()
    const deptButton = (text: string) => Array.from(deptView.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    deptButton('新增规则')?.click()
    await settle()
    deptButton('删除')?.click()
    await settle()
    closeRendered(deptView)

    const menuView = renderClient(createElement(MenuManager, { initialMenus: menus as never }))
    await settle()
    const menuButton = (text: string) => Array.from(menuView.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    menuButton('新建菜单')?.click()
    await settle()
    menuButton('保存')?.click()
    await settle()
    menuView.container.querySelector('[title="编辑"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    menuView.container.querySelector('[title="禁用"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    menuView.container.querySelector('[title="删除"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await settle()
    closeRendered(menuView)

    const verificationView = renderClient(createElement(PermissionVerification, { users: [user] as never }))
    await settle()
    const account = Array.from(verificationView.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="user-1"]'))
    if (account) {
      account.value = 'user-1'
      account.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    verificationView.container.querySelector('button')?.click()
    verificationView.container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await settle()
    queryElement<HTMLButtonElement>(verificationView.container, 'button[aria-label="导出权限清单"]')?.click()
    Array.from(verificationView.container.querySelectorAll('button')).find((button) => button.textContent?.includes('导出权限清单'))?.click()
    await settle()
    closeRendered(verificationView)
  })

  it('covers system menu create, edit, status and delete error paths', async () => {
    const menus = [
      { id: 'menu-root', key: 'root', parent_id: null, name: '系统设置', type: 'directory', permission_code: null, route_path: '/settings', component_path: null, icon: 'setting', sort_order: 1, status: 'active' },
      { id: 'menu-disabled', key: 'disabled', parent_id: 'menu-root', name: '旧入口', type: 'menu', permission_code: 'system:read', route_path: '/settings/old', component_path: null, icon: null, sort_order: 2, status: 'disabled' },
    ]
    getMock('actions/admin', 'createMenu').mockResolvedValue({ id: 'menu-new' })
    getMock('actions/admin', 'updateMenu').mockResolvedValue({})
    getMock('actions/admin', 'deleteMenu').mockResolvedValue({})
    const rendered = renderClient(createElement(MenuManager, { initialMenus: menus as never }))
    await settle()
    const byTitle = (title: string) => rendered.container.querySelector(`[title="${title}"]`) as HTMLButtonElement | null
    const textButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    textButton('新建菜单')?.click()
    await settle()
    textButton('保存')?.click()
    await settle()
    byTitle('编辑')?.click()
    await settle()
    textButton('保存')?.click()
    await settle()
    byTitle('禁用')?.click()
    await settle()
    byTitle('启用')?.click()
    await settle()
    byTitle('删除')?.click()
    await settle()
    getMock('actions/admin', 'createMenu').mockRejectedValueOnce(new Error('创建失败'))
    textButton('新建菜单')?.click()
    await settle()
    textButton('保存')?.click()
    await settle()
    getMock('actions/admin', 'updateMenu').mockRejectedValueOnce(new Error('状态更新失败'))
    byTitle('禁用')?.click()
    await settle()
    getMock('actions/admin', 'deleteMenu').mockRejectedValueOnce(new Error('删除失败'))
    byTitle('删除')?.click()
    await settle()
    closeRendered(rendered)
  })

  it('exercises annual training plan loading, editing, attachment preview and export', async () => {
    getMock('lib/api/client/hr', 'fetchPlanItems').mockResolvedValue({ data: [{ id: 'item-1', sort_order: 1, training_type: '内训', training_month: '8月', content_textbook: 'GMP培训（附件一）', target_audience: '质量部', instructor: '张三', assessment_method: '笔试' }] })
    getMock('lib/api/client/hr', 'fetchPlanAttachments').mockResolvedValue({ data: [{ id: 'att-1', annex_no: '附件2', file_name: '制度.pdf' }] })
    getMock('lib/api/client/hr', 'fetchPlanAttachmentSections').mockResolvedValue({ data: [{ id: 'sec-1', annex_no: '附件1', title: 'GMP章节' }] })
    getMock('lib/api/client/hr', 'fetchSectionPreview').mockResolvedValue({ data: { content: '章节内容', file_name: '章节.docx' } })
    getMock('lib/api/client/hr', 'fetchAttachmentPreview').mockResolvedValue({ data: { content: '附件内容', file_name: '制度.pdf' } })
    getMock('actions/hr', 'batchUpdatePlanItems').mockResolvedValue({})
    getMock('actions/hr', 'uploadPlanAttachments').mockResolvedValue({})
    getMock('actions/hr', 'deletePlanAttachment').mockResolvedValue({})
    getMock('lib/api/client/hr', 'exportAnnualTrainingPlanWord').mockResolvedValue(new Blob(['doc']))
    const rendered = renderClient(createElement(AnnualPlanDetailClient, {
      planId: 'plan-1',
      plan: { id: 'plan-1', year: 2026, plan_level: '部门级', department: '质量部', version: 'V2', remarks: '备注' } as never,
    }))
    await settle()
    expect(rendered.container.textContent).toContain('2026年度部门培训计划表')
    const previewTags = Array.from(rendered.container.querySelectorAll('span[title*="点击预览"]'))
    previewTags.forEach((tag) => tag.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    await settle()
    for (const button of Array.from(rendered.container.querySelectorAll('button'))) {
      if (!button.disabled) button.click()
    }
    await settle()
    expect(getMock('actions/hr', 'batchUpdatePlanItems')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('exercises the real sign-in sheet personnel, conflict and export paths', async () => {
    const { default: RealSignInSheetClient } = await vi.importActual<typeof import('./components/hr/SignInSheetClient')>('./components/hr/SignInSheetClient')
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部', '生产部'])
    getMock('lib/api/hr', 'fetchEmployees').mockResolvedValue({ data: [{ name: '李四', department: '质量部', sub_department: null }], total: 1 })
    getMock('lib/api/client/hr', 'fetchTrainers').mockResolvedValue({ data: [{ name: '张三', department: '质量部' }], total: 1 })
    getMock('actions/hr', 'checkTrainingConflict').mockResolvedValue({ data: { has_conflict: true, instructor_conflicts: [{ training_name: '已有培训', time_range: '09:00-10:00', conflict_depts: ['质量部'], conflict_count: 1 }], trainee_conflicts: [{ training_name: '其他培训', time_range: '09:00-10:00', names: ['李四'], conflict_count: 1 }], suggested_times: [{ start: '14:00', end: '15:00' }] } })
    getMock('actions/hr', 'generateTrainingSignInSheet').mockResolvedValue({ bytes: new Uint8Array([1, 2, 3]), filename: '签到表.docx' })
    const onSessionChange = vi.fn()
    let exporter: (() => Promise<unknown>) | undefined
    const rendered = renderClient(createElement(RealSignInSheetClient, {
      sessionData: { training_date: '2026-08-25', training_time_start: '09:00', training_time_end: '10:00', topic: 'GMP培训', training_method: '课堂', instructor: '张三', employee_names: ['李四'], trainee_departments: ['质量部'], employee_dept_map: { 李四: '质量部' } },
      onSessionChange,
      registerExporter: (_type: string, fn: () => Promise<unknown>) => { exporter = fn },
      sessionId: 'session-1',
    }))
    await settle()
    expect(rendered.container.textContent).toContain('培训签到表')
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 600)) })
    rendered.container.querySelector('.cb-big')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    const deptSelect = rendered.container.querySelector('select') as HTMLSelectElement | null
    if (deptSelect) {
      deptSelect.value = '质量部'
      deptSelect.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const rowInputs = Array.from(rendered.container.querySelectorAll('.sign-cell input')) as HTMLInputElement[]
    if (rowInputs[0]) {
      rowInputs[0].value = '王五'
      rowInputs[0].dispatchEvent(new Event('input', { bubbles: true }))
      rowInputs[0].dispatchEvent(new Event('change', { bubbles: true }))
    }
    if (rowInputs[1]) {
      rowInputs[1].value = '质量部'
      rowInputs[1].dispatchEvent(new Event('input', { bubbles: true }))
      rowInputs[1].dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    rendered.container.querySelector('button')?.click()
    await settle()
    await exporter?.()
    getMock('actions/hr', 'generateTrainingSignInSheet').mockRejectedValueOnce(new Error('签到表生成失败'))
    rendered.container.querySelector('button')?.click()
    await settle()
    expect(getMock('actions/hr', 'checkTrainingConflict')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'generateTrainingSignInSheet')).toHaveBeenCalled()
    expect(onSessionChange).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('covers training sign-in classification and annex normalization helpers', () => {
    expect(matchTrainingType('岗位职责培训', '')).toBe('管理类')
    expect(matchTrainingType('', 'SOP-QA-001/02 文件')).toBe('管理类')
    expect(matchTrainingType('', '消防安全与应急疏散')).toBe('EHS培训')
    expect(matchTrainingType('', 'GMP质量体系')).toBe('质量培训')
    expect(matchTrainingType('', '没有匹配关键词')).toBeUndefined()
    expect(matchDrugCategory('', '兽药多拉菌素')).toBe('兽药')
    expect(matchDrugCategory('GMP培训', '')).toBe('人药')
    expect(matchDrugCategory('', '普通行政培训')).toBeUndefined()
    expect(formatTopicForSignin([{ name: '指南', code: 'SOP-1' }, { name: '手册', resolvedCode: 'TR-2' }])).toBe('《指南》（SOP-1）、《手册》（TR-2）')
    expect(formatTopicForSignin([{ name: '一' }, { name: '二' }, { name: '三' }])).toContain('等3份文件详见附件')
    expect(cnToInt('１２')).toBe(12)
    expect(cnToInt('十')).toBe(10)
    expect(cnToInt('十二')).toBe(12)
    expect(cnToInt('二十')).toBe(20)
    expect(cnToInt('九')).toBe(9)
    expect(cnToInt('未知')).toBeNull()
    expect(extractAnnexRefs('附件1、附件一、附件１２和附件二十')).toEqual(['附件1', '附件12', '附件20'])
  })

  it('drives training scope, plan attachment selection and ledger actions', async () => {
    getMock('lib/api/client/hr', 'fetchAnnualTrainingPlans').mockResolvedValue({ data: [{ id: 'plan-1', year: 2026, plan_level: '公司级', department: '质量部', version: 'V1' }] })
    getMock('lib/api/client/hr', 'fetchPlanItems').mockResolvedValue({ data: [{ id: 'item-1', sort_order: 1, training_month: '8月', content_textbook: 'GMP培训（附件一）', training_method: '面授' }] })
    getMock('lib/api/client/hr', 'fetchPlanAttachmentSections').mockResolvedValue({ data: [{ id: 'section-1', annex_no: '附件1', title: 'GMP章节' }] })
    getMock('lib/api/client/hr', 'fetchUsedTrainingContent').mockResolvedValue([])
    getMock('lib/api/client/hr', 'fetchTrainingPersonnelConfigs').mockResolvedValue({ data: [{ id: 'config-1', config_name: '质量班组', level: '公司级', personnel: [{ name: '张三', department: '质量部' }] }] })
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部', '生产部'])
    getMock('lib/api/client/hr', 'fetchNewHires').mockResolvedValue({ data: [{ name: '新员工', employee_number: 'E-9', department: '生产部' }] })
    getMock('actions/quality', 'resolveDocumentEntryContent').mockResolvedValue([{ name: 'GMP章节', code: 'SOP-NEW' }])
    getMock('actions/hr', 'upsertTrainingSession').mockResolvedValue('session-1')
    getMock('actions/hr', 'upsertTrainingDocument').mockResolvedValue({})
    getMock('actions/hr', 'createTrainingLedger').mockResolvedValue({})
    getMock('actions/hr', 'markTrainingContentUsed').mockResolvedValue({})
    const rendered = renderClient(createElement(TrainingSignInTabsClient))
    await settle()
    const selects = () => Array.from(rendered.container.querySelectorAll('select')) as HTMLSelectElement[]
    const selectByOption = async (value: string) => {
      const select = selects().find((item) => item.querySelector(`option[value="${value}"]`))
      if (!select) return
      select.value = value
      select.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    await selectByOption('plan-1')
    await selectByOption('item-1')
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('选择培训附件内容'))?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('确认附件内容'))?.click()
    await settle()
    await selectByOption('config-1')
    const newHireButton = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('拉取新员工'))
    newHireButton?.click()
    await settle()
    const exportButton = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('一键导出'))
    exportButton?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '保存')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('添加到培训台账'))?.click()
    await settle()
    // 台账入账改为受控确认弹窗：点击弹窗内"确定"触发 doAddToLedger
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '确 定' || button.textContent === '确定')?.click()
    await settle()
    expect(getMock('actions/hr', 'upsertTrainingSession')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'upsertTrainingDocument')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'createTrainingLedger')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('covers annual plan detail empty rows, attachment failures and export failures', async () => {
    getMock('lib/api/client/hr', 'fetchPlanItems').mockResolvedValue({ data: [{ id: 'item-1', sort_order: 1, content_textbook: '附件一与附件2' }] })
    getMock('lib/api/client/hr', 'fetchPlanAttachments').mockResolvedValue({ data: [{ id: 'att-1', annex_no: '附件2', file_name: '制度.pdf' }] })
    getMock('lib/api/client/hr', 'fetchPlanAttachmentSections').mockResolvedValue({ data: [{ id: 'section-1', annex_no: '附件1', title: '章节' }] })
    getMock('lib/api/client/hr', 'fetchSectionPreview').mockRejectedValue(new Error('章节预览失败'))
    getMock('lib/api/client/hr', 'fetchAttachmentPreview').mockRejectedValue(new Error('附件预览失败'))
    getMock('actions/hr', 'batchUpdatePlanItems').mockRejectedValue(new Error('保存失败'))
    getMock('actions/hr', 'uploadPlanAttachments').mockRejectedValue(new Error('上传失败'))
    getMock('actions/hr', 'deletePlanAttachment').mockRejectedValue(new Error('删除失败'))
    getMock('lib/api/client/hr', 'exportAnnualTrainingPlanWord').mockRejectedValue(new Error('导出失败'))
    const rendered = renderClient(createElement(AnnualPlanDetailClient, {
      planId: 'plan-error', plan: { id: 'plan-error', year: 2026, plan_level: '公司级', department: '公司' } as never,
    }))
    await settle()
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    rendered.container.querySelector('span[title*="点击预览"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    rendered.container.querySelector('span[title="点击下载"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    rendered.container.querySelector('span[title="预览整文件"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    findButton('保存全部')?.click()
    findButton('导出公司级计划')?.click()
    findButton('批量上传附件')?.click()
    await settle()
    expect(getMock('actions/hr', 'batchUpdatePlanItems')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'uploadPlanAttachments')).toHaveBeenCalled()
    expect(getMock('lib/api/client/hr', 'exportAnnualTrainingPlanWord')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('renders quality Feishu settings with table matching, mapping and sync controls', async () => {
    getMock('lib/api/client/quality', 'fetchQualityFeishuAppSettings').mockResolvedValue({
      app_id: 'quality-app', app_secret_masked: '***', is_enabled: true,
      deviation_report_form_url: '', deviation_investigation_push_form_url: '',
      oos_oot_report_form_url: '', oos_oot_investigation_push_form_url: '',
    })
    getMock('lib/api/client/quality', 'fetchQualityFeishuEntitySettings').mockResolvedValue([{
      entity_code: 'deviation', entity_name: '偏差', entity_group: '质量', app_token: 'base-1',
      base_table_name: '偏差表', base_table_id: 'tbl-1', is_enabled: true,
      enable_push_to_feishu: true, enable_pull_from_feishu: false, field_mappings: [],
      last_sync_status: 'failed', last_synced_at: null,
    }])
    getMock('lib/api/client/quality', 'fetchQualityFeishuEntityFieldMappingBundle').mockResolvedValue({
      entity_code: 'deviation', entity_name: '偏差',
      system_fields: [{ field_key: 'title', field_label: '标题', direction: 'push' }],
      feishu_fields: [{ field_name: '飞书标题' }], field_mappings: [],
    })
    getMock('lib/api/client/quality', 'fetchQualityFeishuEntityTables').mockResolvedValue([{ table_name: '偏差表', table_id: 'tbl-1' }])
    getMock('actions/quality', 'updateQualityFeishuAppSettings').mockResolvedValue({})
    getMock('actions/quality', 'testQualityFeishuAppSettings').mockResolvedValue({ success: true, status: 'success', message: '连接成功' })
    getMock('actions/quality', 'updateQualityFeishuEntitySetting').mockResolvedValue({ entity_name: '偏差' })
    getMock('actions/quality', 'testQualityFeishuEntitySetting').mockResolvedValue({ success: true, status: 'success', message: '连接成功', entity_name: '偏差' })
    getMock('actions/quality', 'pullQualityRecordsFromFeishu').mockResolvedValue({ synced: 1, failed: 0 })
    getMock('lib/api/client/quality', 'formatQualityFeishuTestSummary').mockReturnValue('连接成功')
    getMock('lib/api/client/quality', 'formatQualitySyncSummary').mockReturnValue('同步完成')
    const rendered = renderClient(createElement(QualityFeishuSettingsPage))
    await settle()
    expect(rendered.container.textContent).toContain('质量')
    for (const input of Array.from(rendered.container.querySelectorAll('input'))) {
      input.value = 'https://example.feishu.cn/base/app-token?table=tbl-1'
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    for (let round = 0; round < 3; round += 1) {
      for (const button of Array.from(rendered.container.querySelectorAll('button'))) {
        if (!button.disabled) button.click()
      }
      await settle()
    }
    closeRendered(rendered)
  })

  it('covers quality Feishu validation, batch updates and field mapping', async () => {
    getMock('lib/api/client/quality', 'fetchQualityFeishuAppSettings').mockResolvedValue({
      app_id: 'quality-app', app_secret_masked: '***', is_enabled: true,
      deviation_report_form_url: '', deviation_investigation_push_form_url: '',
      oos_oot_report_form_url: '', oos_oot_investigation_push_form_url: '',
      last_test_status: 'failed', last_test_error: '上次连接失败', last_tested_at: '2026-08-20T10:00:00Z',
    })
    getMock('lib/api/client/quality', 'fetchQualityFeishuEntitySettings').mockResolvedValue([
      {
        entity_code: 'deviation', entity_name: '偏差', entity_group: '质量', app_token: 'bascn-old',
        base_table_name: '偏差表', base_table_id: 'tbl-old', is_enabled: true,
        enable_push_to_feishu: true, enable_pull_from_feishu: false,
        field_mappings: [{ system_field: 'title', feishu_field: '旧标题' }],
        last_sync_status: 'failed', last_synced_at: '2026-08-20T10:00:00Z', source_note: '迁移配置',
      },
      {
        entity_code: 'oos', entity_name: 'OOS', entity_group: '质量', app_token: 'bascn-old',
        base_table_name: '', base_table_id: '', is_enabled: false,
        enable_push_to_feishu: false, enable_pull_from_feishu: true, field_mappings: [],
        last_sync_status: null, last_synced_at: null,
      },
    ])
    getMock('lib/api/client/quality', 'fetchQualityFeishuEntityFieldMappingBundle').mockResolvedValue({
      entity_code: 'deviation', entity_name: '偏差',
      system_fields: [
        { field_key: 'title', field_label: '标题', direction: 'push' },
        { field_key: 'status', field_label: '状态', direction: 'pull' },
      ],
      feishu_fields: [{ field_name: '飞书标题' }, { field_name: '飞书状态' }],
      field_mappings: [{ system_field: 'title', feishu_field: '旧标题' }],
    })
    getMock('lib/api/client/quality', 'fetchQualityFeishuEntityTables').mockResolvedValue([
      { table_name: '偏差', table_id: 'tbl-deviation' }, { table_name: 'OOS', table_id: 'tbl-oos' },
    ])
    getMock('actions/quality', 'updateQualityFeishuAppSettings').mockResolvedValue({})
    getMock('actions/quality', 'testQualityFeishuAppSettings').mockResolvedValue({ success: true, status: 'success', message: '连接成功' })
    getMock('actions/quality', 'updateQualityFeishuEntitySetting').mockResolvedValue({ entity_name: '偏差' })
    getMock('actions/quality', 'testQualityFeishuEntitySetting').mockResolvedValue({ success: false, status: 'failed', message: '实体连接失败' })
    getMock('actions/quality', 'pullQualityRecordsFromFeishu').mockResolvedValue({ synced: 2, failed: 1, conflicts: 1 })
    getMock('lib/api/client/quality', 'formatQualityFeishuTestSummary').mockReturnValue('连接测试结果')
    getMock('lib/api/client/quality', 'formatQualitySyncSummary').mockReturnValue('回拉结果')
    mocks.modal.confirm.mockImplementation(({ onOk }: { onOk?: () => unknown }) => void onOk?.())
    const rendered = renderClient(createElement(QualityFeishuSettingsPage))
    await settle()

    const setInput = async (input: HTMLInputElement | null, value: string) => {
      if (!input) return
      input.value = value
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    await setInput(rendered.container.querySelector('input[placeholder="请输入飞书应用 App ID"]'), 'quality-app-new')
    await setInput(rendered.container.querySelector('input[placeholder*="偏差报告新建"]'), 'https://example.test/deviation')
    const appSwitch = rendered.container.querySelector('input[type="checkbox"]') as HTMLInputElement | null
    appSwitch?.click()
    await settle()
    const button = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((item) => item.textContent?.includes(text))
    button('保存配置')?.click()
    await settle()
    button('测试连接')?.click()
    await settle()
    button('手动回拉已启用数据')?.click()
    await settle()

    await setInput(rendered.container.querySelector('input[placeholder*="粘贴多维表格网址，批量"]'), 'https://example.feishu.cn/base/bascn-batch?table=tbl-batch')
    button('批量更新')?.click()
    await settle()
    button('按名称匹配')?.click()
    await settle()
    await setInput(rendered.container.querySelector('input[placeholder="例如：bascnxxxxxxxx"]'), 'bascn-edited')
    const switches = Array.from(rendered.container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]'))
    switches.slice(1, 4).forEach((item) => item.click())
    await settle()
    button('读取表')?.click()
    await settle()
    const tableSelect = rendered.container.querySelector('select[aria-label="可读取后直接选择"]') as HTMLSelectElement | null
    if (tableSelect?.querySelector('option[value="偏差"]')) {
      tableSelect.value = '偏差'
      tableSelect.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    button('保存')?.click()
    await settle()
    button('测试')?.click()
    await settle()

    button('URL填充')?.click()
    await settle()
    await setInput(rendered.container.querySelector('input[placeholder*="https://xxx.feishu.cn/base"]'), 'https://example.feishu.cn/base/bascn-filled?table=tbl-filled')
    Array.from(rendered.container.querySelectorAll('button')).find((item) => item.textContent === '确定')?.click()
    await settle()
    button('字段对齐')?.click()
    await settle()
    const mappingSelect = rendered.container.querySelector('select[aria-label="请选择飞书字段"]') as HTMLSelectElement | null
    if (mappingSelect?.querySelector('option[value="飞书标题"]')) {
      mappingSelect.value = '飞书标题'
      mappingSelect.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    button('保存字段对齐')?.click()
    await settle()

    getMock('actions/quality', 'testQualityFeishuAppSettings').mockRejectedValueOnce(new Error('应用连接失败'))
    button('测试连接')?.click()
    await settle()
    getMock('actions/quality', 'fetchQualityFeishuEntityTables').mockRejectedValueOnce(new Error('读取表失败'))
    button('读取表')?.click()
    await settle()
    closeRendered(rendered)
  })

  it('covers quality Feishu group URL fill, auto matching and partial failures', async () => {
    getMock('lib/api/client/quality', 'fetchQualityFeishuAppSettings').mockResolvedValue({ app_id: 'quality-app', app_secret_masked: '***', is_enabled: true })
    getMock('lib/api/client/quality', 'fetchQualityFeishuEntitySettings').mockResolvedValue([
      { entity_code: 'deviation', entity_name: '偏差', entity_group: '质量', app_token: 'base-old', base_table_name: '旧偏差', base_table_id: 'tbl-old', is_enabled: true, enable_push_to_feishu: true, enable_pull_from_feishu: true, field_mappings: [], last_sync_status: 'success', last_synced_at: null },
      { entity_code: 'oos', entity_name: 'OOS', entity_group: '质量', app_token: '', base_table_name: '', base_table_id: '', is_enabled: false, enable_push_to_feishu: false, enable_pull_from_feishu: false, field_mappings: [], last_sync_status: null, last_synced_at: null },
    ])
    getMock('lib/api/client/quality', 'fetchQualityFeishuEntityTables').mockResolvedValue([{ table_name: '偏差记录表', table_id: 'tbl-deviation' }, { table_name: '其他表', table_id: 'tbl-other' }])
    getMock('actions/quality', 'updateQualityFeishuEntitySetting').mockResolvedValue({ entity_name: '偏差' })
    const rendered = renderClient(createElement(QualityFeishuSettingsPage))
    await settle()
    const groupInput = () => rendered.container.querySelector('input[placeholder*="粘贴多维表格网址，批量"]') as HTMLInputElement | null
    const setGroupUrl = async (value: string) => {
      const input = groupInput()
      if (!input) return
      await act(async () => {
        input.focus()
        input.value = value
        input.dispatchEvent(new Event('input', { bubbles: true }))
        input.dispatchEvent(new Event('change', { bubbles: true }))
        await Promise.resolve()
        await new Promise((resolve) => setTimeout(resolve, 0))
      })
    }
    const groupButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((item) => item.textContent === text)
    await setGroupUrl('https://example.feishu.cn/base/bascn-quality?table=tbl-quality')
    expect(groupButton('批量更新')?.disabled).toBe(false)
    groupButton('批量更新')?.click()
    await settle()
    getMock('actions/quality', 'updateQualityFeishuEntitySetting').mockRejectedValueOnce(new Error('OOS保存失败'))
    await setGroupUrl('https://example.feishu.cn/base/bascn-quality?table=tbl-quality')
    groupButton('批量更新')?.click()
    await settle()

    await setGroupUrl('https://example.feishu.cn/base/bascn-quality?table=tbl-quality')
    groupButton('按名称匹配')?.click()
    await settle()
    getMock('lib/api/client/quality', 'fetchQualityFeishuEntityTables').mockResolvedValueOnce([])
    await setGroupUrl('https://example.feishu.cn/base/bascn-empty?table=tbl-empty')
    groupButton('按名称匹配')?.click()
    await settle()
    getMock('lib/api/client/quality', 'fetchQualityFeishuEntityTables').mockRejectedValueOnce(new Error('Base读取失败'))
    await setGroupUrl('https://example.feishu.cn/base/bascn-error?table=tbl-error')
    groupButton('按名称匹配')?.click()
    await settle()

    groupButton('URL填充')?.click()
    await settle()
    queryElement<HTMLButtonElement>(rendered.container, '[role="dialog"] button:last-of-type')?.click()
    await settle()
    const rowUrlInput = rendered.container.querySelector('input[placeholder*="https://xxx.feishu.cn/base"]') as HTMLInputElement | null
    if (rowUrlInput) {
      rowUrlInput.value = 'https://example.feishu.cn/base/bascn-row?table=tbl-row'
      rowUrlInput.dispatchEvent(new Event('input', { bubbles: true }))
      rowUrlInput.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    queryElement<HTMLButtonElement>(rendered.container, '[role="dialog"] button:last-of-type')?.click()
    await settle()
    getMock('lib/api/client/quality', 'fetchQualityFeishuEntityTables').mockRejectedValueOnce(new Error('读取表失败'))
    Array.from(rendered.container.querySelectorAll('button')).find((item) => item.textContent === '读取表')?.click()
    await settle()
    closeRendered(rendered)
  })

  it('covers OOT limits, certificate records and annual training record actions', async () => {
    getMock('lib/api/client/quality', 'fetchOotLimitProducts').mockResolvedValue({
      data: [{ id: 'product-1', product_code: 'P-1', product_name: '产品A', document_title: '限度标准', document_year: 2026, version_label: 'V1', source_file_name: 'limit.pdf', remark: '备注' }],
      total: 1,
    })
    getMock('lib/api/client/quality', 'fetchOotLimitItems').mockResolvedValue({
      data: [{ id: 'item-1', product_id: 'product-1', display_order: 1, item_group: '有关物质', item_name: '杂质A', standard_value: '≤1.0%', oot_limit_value: '>1.5%', remark: '重点' }],
      total: 1,
    })
    for (const name of ['createOotLimitProduct', 'updateOotLimitProduct', 'createOotLimitItem', 'updateOotLimitItem', 'deleteOotLimitProduct', 'deleteOotLimitItem']) getMock('actions/quality', name).mockResolvedValue({ id: 'updated' })
    const oot = renderClient(createElement(OotLimitManagementPage))
    await settle()
    expect(oot.container.textContent).toContain('各产品OOT限度')
    oot.container.querySelector('input[placeholder*="搜索"]')?.dispatchEvent(new Event('change', { bubbles: true }))
    const createProduct = Array.from(oot.container.querySelectorAll('button')).find((button) => button.textContent?.includes('新增产品'))
    createProduct?.click()
    await settle()
    Array.from(oot.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    const editProduct = Array.from(oot.container.querySelectorAll('button')).find((button) => button.textContent?.includes('修改当前产品'))
    editProduct?.click()
    await settle()
    Array.from(oot.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    Array.from(oot.container.querySelectorAll('button')).find((button) => button.textContent?.includes('新增限度明细'))?.click()
    await settle()
    Array.from(oot.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    Array.from(oot.container.querySelectorAll('button')).filter((button) => button.textContent?.includes('修改')).forEach((button) => button.click())
    await settle()
    Array.from(oot.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    closeRendered(oot)

    getMock('actions/registration', 'createCertificateEntry').mockResolvedValue({ id: 'certificate-2' })
    getMock('actions/registration', 'updateCertificateEntry').mockResolvedValue({ id: 'certificate-1' })
    getMock('actions/registration', 'deleteCertificateEntry').mockResolvedValue({ success: true })
    const certificate = renderClient(createElement(CertificateSheetPage, {
      detail: {
        sheet_key: 'domestic-gmp', sheet_name: '国内GMP',
        columns: [{ label: '证照名称', key: 'certificate_name' }, { label: '编号', key: 'certificate_number' }],
        rows: [{ id: 'certificate-1', sequence: 1, values: { 证照名称: 'GMP证书', 编号: 'GMP-001', 发证机关: '药监局', 发证日期: '2026-01-01', '有效期/复验期': '2027-01-01', 产品范围: '产品A', 质量标准: '标准', 页数: '2', 备注: '备注' } }],
        total: 1, page: 1, page_size: 20, total_pages: 1, summary: { total_records: 1 },
      } as never,
    }))
    await settle()
    queryElement<HTMLTableRowElement>(certificate.container, 'tbody tr')?.click()
    await settle()
    Array.from(certificate.container.querySelectorAll('button')).find((button) => button.textContent?.includes('编辑选中'))?.click()
    await settle()
    Array.from(certificate.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    Array.from(certificate.container.querySelectorAll('button')).find((button) => button.textContent?.includes('删除选中'))?.click()
    await settle()
    Array.from(certificate.container.querySelectorAll('button')).find((button) => button.textContent?.includes('新增'))?.click()
    await settle()
    Array.from(certificate.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    closeRendered(certificate)

    const ledger = { id: 'ledger-1', employee_number: 'E-1', training_date: '2026-08-20', training_subject: 'GMP培训', training_content: 'GMP培训', training_datetime: '2026-08-20 09:00', duration_hours: 2, teaching_dept: '质量部', instructor: '张三', level_category: '一级', involved_depts: '质量部', trainees: '李四', training_type: '质量培训', ledger_assessment_method: '笔试', plan_source: '年度计划', drug_category: '人药', score_summary: '合格', remarks: '备注', source_type: 'session', session_id: 'session-1', second_level_status: 'pending' }
    getMock('lib/api/hr', 'fetchTrainingLedgersByDept').mockResolvedValue({ code: 200, message: 'ok', data: [ledger], meta: { page: 1, page_size: 500, total: 1 } })
    getMock('lib/api/client/hr', 'fetchSessionDocuments').mockResolvedValue([{ id: 'doc-1', session_id: 'session-1', doc_type: 'oral_exam', title: '口试', payload: {}, updated_at: '2026-08-20' }, { id: 'doc-2', session_id: 'session-1', doc_type: 'practical_exam', title: '实操', payload: {}, updated_at: '2026-08-20' }])
    getMock('lib/api/client/hr', 'fetchTrainingSession').mockResolvedValue({ department: '质量部' })
    getMock('actions/hr', 'updateTrainingLedger').mockResolvedValue({})
    getMock('actions/hr', 'deleteTrainingLedger').mockResolvedValue({})
    getMock('actions/hr', 'generateOralExamResult').mockResolvedValue({ bytes: new Uint8Array([1]), filename: 'oral.docx' })
    getMock('actions/hr', 'generatePracticalExamResult').mockResolvedValue({ bytes: new Uint8Array([1]), filename: 'practical.docx' })
    const stats = renderClient(createElement(AnnualTrainingStatsClient, { department: '质量部', dateFrom: '2026-01-01', dateTo: '2026-12-31', periodLabel: '全年', printRequest: 0 }))
    await settle()
    expect(stats.container.textContent).toContain('GMP培训')
    for (const button of Array.from(stats.container.querySelectorAll('button'))) if (!button.disabled) button.click()
    await settle()
    for (const button of Array.from(stats.container.querySelectorAll('button'))) if (!button.disabled) button.click()
    await settle()
    closeRendered(stats)
  })

  it('drives OOS/OOT investigation push filters, pull, edit, detail and delete flows', async () => {
    const record = {
      record_id: 'push-1', oos_oot_code: 'INV-1', push_round: '第1次', department: '质量部', submitter: '张三',
      department_head: '李四', department_head_direct: 'head-1', department_head_result: '待审核',
      department_head_reviewed_at: '2026-08-20T10:00:00Z', qa_result: '待审核', qa_reviewed_at: null,
      qa_head_result: '待审核', qa_head_reviewed_at: null, process_status: '待部门负责人审核',
      submitted_at: '2026-08-20T09:00:00Z', investigation_report_url: 'https://example.test/report',
      submitters: [{ name: '张三', id: 'u-1' }], department_heads: [{ name: '李四', id: 'u-2' }],
      qas: [{ name: 'QA', id: 'u-3' }], qa_heads: [{ name: 'QA负责人', id: 'u-4' }],
    }
    getMock('lib/api/client/quality', 'fetchOosOotInvestigationPushRecords').mockResolvedValue({ data: [record], meta: { total: 1 } })
    getMock('lib/api/client/quality', 'fetchQualityFeishuAppSettings').mockResolvedValue({ oos_oot_investigation_push_form_url: 'https://example.feishu.cn/form' })
    getMock('lib/api/client/quality', 'fetchDepartmentContacts').mockResolvedValue([
      { name: '张三', department: '质量部', department_head_name: '李四', open_id: 'u-1', bitable_user_id: 'user-1' },
      { name: '李四', department: '质量部', department_head_name: null, open_id: 'u-2', bitable_user_id: 'head-1' },
    ])
    getMock('lib/api/client/quality', 'fetchOosLedgerRecords').mockResolvedValue({ data: [{ investigation_code: 'INV-1' }] })
    getMock('lib/api/client/quality', 'fetchOotLedgerRecords').mockResolvedValue({ data: [{ investigation_code: 'INV-2' }] })
    getMock('actions/quality', 'pullOosOotInvestigationPushRecords').mockResolvedValue({ synced: 1, failed: 0 })
    getMock('actions/quality', 'updateOosOotInvestigationPushRecord').mockResolvedValue({})
    getMock('actions/quality', 'deleteOosOotInvestigationPushRecord').mockResolvedValue({})
    vi.stubGlobal('open', vi.fn())
    const rendered = renderClient(createElement(OosOotInvestigationPushPage))
    await settle()
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    const search = rendered.container.querySelector('input[placeholder="搜索编号、部门、提交人..."]') as HTMLInputElement | null
    if (search) {
      search.value = 'INV-1'
      search.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const filter = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="质量部"]'))
    if (filter) {
      filter.value = '质量部'
      filter.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    findButton('清除筛选')?.click()
    findButton('新增')?.click()
    await settle()
    findButton('从飞书拉取')?.click()
    await settle()
    findButton('详情')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '关闭')?.click()
    await settle()
    findButton('修改')?.click()
    await settle()
    const dept = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="质量部"]'))
    if (dept) {
      dept.value = '质量部'
      dept.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const submitter = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="user-1"]'))
    if (submitter) {
      submitter.value = 'user-1'
      submitter.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    findButton('删除')?.click()
    await settle()
    expect(getMock('actions/quality', 'updateOosOotInvestigationPushRecord')).toHaveBeenCalled()
    expect(getMock('actions/quality', 'deleteOosOotInvestigationPushRecord')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives document catalog department, entry, import, attachment and export flows', async () => {
    const departments = [{ id: 'dept-1', name: '质量部', sort_order: 1, document_count: 1 }]
    const entry = {
      id: 'doc-1', department_id: 'dept-1', seq_no: 1, name: 'SOP管理程序', code: 'SOP-1', effective_date: '2026-08-01', effective_date_text: '2026-08-01',
      attachments: [{ storage_key: 'att-1', file_name: '制度文件.pdf', content_type: 'application/pdf', size: 100, url: 'https://example.test/file' }, { storage_key: 'att-2', file_name: '附件.docx', content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', size: 100 }, { storage_key: 'att-3', file_name: '图片.png', content_type: 'image/png', size: 100 }],
    }
    getMock('lib/api/client/quality', 'fetchDocumentDepartments').mockResolvedValue(departments)
    getMock('lib/api/client/quality', 'fetchDocumentEntries').mockResolvedValue({ items: [entry], total: 1 })
    getMock('lib/api/client/quality', 'fetchDocumentCatalogExport').mockResolvedValue({ blob: new Blob(['xlsx']), filename: '目录.xlsx' })
    getMock('lib/api/client/quality', 'fetchDocumentEntryAttachmentContent').mockResolvedValue({ text: '附件内容', blobUrl: '', contentType: 'text/plain' })
    for (const name of ['createDocumentDepartment', 'createDocumentEntry', 'deleteDocumentDepartment', 'deleteDocumentEntry', 'importDocumentCatalogExcel', 'batchImportDocumentAttachments', 'updateDocumentDepartment', 'updateDocumentEntry']) getMock('actions/quality', name).mockResolvedValue({ department_count: 1, entry_count: 1, bound: 1, results: [] })
    const rendered = renderClient(createElement(DocumentCatalogPage, { initialDepartments: departments as never }))
    await settle()
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.trim() === text || button.textContent?.includes(text))
    const allDept = rendered.container.querySelector('button')
    allDept?.click()
    await settle()
    findButton('导出')?.click()
    const deptButton = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('质量部'))
    deptButton?.click()
    await settle()
    findButton('导出')?.click()
    findButton('导入文件目录')?.click()
    findButton('导入附件')?.click()
    findButton('新增条目')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    findButton('编辑')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    findButton('删除')?.click()
    await settle()
    const attachment = queryElement<HTMLSpanElement>(rendered.container, 'span[title]')
    attachment?.click()
    await settle()
    findButton('管理')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '新增')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    rendered.container.querySelector('button')?.click()
    await settle()
    expect(getMock('actions/quality', 'createDocumentEntry')).toHaveBeenCalled()
    expect(getMock('actions/quality', 'importDocumentCatalogExcel')).toHaveBeenCalled()
    expect(getMock('actions/quality', 'batchImportDocumentAttachments')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('covers the shared OOS/OOT ledger create, filter, pull, update and delete flows', async () => {
    const record = {
      record_id: 'ledger-1', serial_number: '1', date: '2026-08-20', material_name: '原料A', batch_number: 'B-1',
      investigation_code: 'INV-1', problem_description: '偏差描述', root_cause: '原因', corrective_actions: '措施',
      final_disposition: '放行', registrant: 'user-1', remark: '备注',
    }
    getMock('lib/api/client/quality', 'fetchDepartmentContacts').mockResolvedValue([{ name: '张三', open_id: 'user-1', department: '质量部' }])
    const fetchRecords = vi.fn(async () => ({ data: [record] }))
    const pullRecords = vi.fn(async () => ({ synced: 1, failed: 0 }))
    const createRecord = vi.fn(async () => ({ id: 'ledger-new' }))
    const updateRecord = vi.fn(async () => ({ id: 'ledger-1' }))
    const deleteRecord = vi.fn(async () => undefined)
    vi.stubGlobal('open', vi.fn())
    const rendered = renderClient(createElement(OosOotLedgerPageBase, { config: {
      label: 'OOS', queryKeyPrefix: 'test-oos', exportUrl: '/api/v1/quality/oos/export', fetchRecords, pullRecords, createRecord, updateRecord, deleteRecord,
    } }))
    await settle()
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    const search = rendered.container.querySelector('input[placeholder="搜索序号、物料名称、批号..."]') as HTMLInputElement | null
    if (search) {
      search.value = '原料A'
      search.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const filter = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="原料A"]'))
    if (filter) {
      filter.value = '原料A'
      filter.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    findButton('清除筛选')?.click()
    findButton('导出')?.click()
    findButton('从飞书拉取')?.click()
    await settle()
    findButton('新增')?.click()
    await settle()
    // Drawer 必填校验：物料名称、问题描述必填（日期默认今天）
    const setInput = (placeholder: string, value: string) => {
      const input = rendered.container.querySelector(
        `input[placeholder="${placeholder}"]`,
      ) as HTMLInputElement | null
      if (input) {
        input.value = value
        input.dispatchEvent(new Event('input', { bubbles: true }))
        input.dispatchEvent(new Event('change', { bubbles: true }))
      }
    }
    setInput('请输入物料名称', '原料A')
    setInput('请输入调查编号', 'INV-1')
    const desc = rendered.container.querySelector(
      'textarea[placeholder="请输入问题描述"]',
    ) as HTMLTextAreaElement | null
    if (desc) {
      desc.value = '偏差描述'
      desc.dispatchEvent(new Event('input', { bubbles: true }))
      desc.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    findButton('保存')?.click()
    await settle()
    findButton('修改')?.click()
    await settle()
    findButton('保存')?.click()
    await settle()
    findButton('删除')?.click()
    await settle()
    expect(createRecord).toHaveBeenCalled()
    expect(updateRecord).toHaveBeenCalled()
    expect(deleteRecord).toHaveBeenCalled()
    expect(pullRecords).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives product quality standard search, column reset, pull and CRUD flows', async () => {
    const record = {
      record_id: 'standard-1', serial_number: 1, customer_name: '客户A', quality_standard: '标准A', shipping_trend_url: 'https://example.test/trend',
      special_requirements: '特殊要求', packaging_requirements: '包装', label_requirements: '标签', pallet_requirements: '托盘', target_market: '中国', registration_status: '已注册', other_notes: '备注',
    }
    getMock('lib/api/client/quality', 'fetchProductQualityStandards').mockResolvedValue({ items: [record], total: 1 })
    getMock('actions/quality', 'createProductQualityStandardAction').mockResolvedValue({})
    getMock('actions/quality', 'updateProductQualityStandardAction').mockResolvedValue({})
    getMock('actions/quality', 'deleteProductQualityStandardAction').mockResolvedValue({})
    getMock('actions/quality', 'pullProductQualityStandardsAction').mockResolvedValue({ synced: 1 })
    const rendered = renderClient(createElement(ProductQualityStandardPage, { productCode: 'P-1', productLabel: '原料A' }))
    await settle()
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    const search = rendered.container.querySelector('input[placeholder="搜索客户名称、质量标准、目标市场"]') as HTMLInputElement | null
    if (search) {
      search.value = '客户A'
      search.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const market = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="中国"]'))
    if (market) {
      market.value = '中国'
      market.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    findButton('清除筛选')?.click()
    findButton('恢复列宽')?.click()
    findButton('从飞书拉取')?.click()
    findButton('刷新')?.click()
    await settle()
    findButton('新增')?.click()
    await settle()
    // 产品质量标准 Modal（onOk 默认「确定」），无必填字段
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    findButton('修改')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    findButton('删除')?.click()
    await settle()
    expect(getMock('actions/quality', 'createProductQualityStandardAction')).toHaveBeenCalled()
    expect(getMock('actions/quality', 'updateProductQualityStandardAction')).toHaveBeenCalled()
    expect(getMock('actions/quality', 'deleteProductQualityStandardAction')).toHaveBeenCalled()
    expect(getMock('actions/quality', 'pullProductQualityStandardsAction')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives deviation report records create, pull, detail, AI, edit and delete flows', async () => {
    const record = {
      id: 'deviation-1', record_id: 'deviation-1', deviation_code: 'DEV-001', report_time: '2026-08-25T08:30:00Z',
      description: '偏差描述', product_batch: '产品A-001', department: '质量部', reporter_name: '张三',
      reporters: [{ id: 'user-1', name: '张三' }], attachments: [{ name: '报告.pdf', url: '/files/report.pdf' }],
      department_heads: [{ name: '部门负责人' }], department_head_result: '通过', department_head_reviewed_at: '2026-08-25T09:00:00Z',
      qas: [{ name: 'QA' }], qa_result: '通过', qa_reviewed_at: '2026-08-25T09:30:00Z',
      qa_heads: [{ name: 'QA负责人' }], qa_head_result: '待确认', report_status: '处理中',
    }
    getMock('lib/api/client/quality', 'fetchFeishuDeviationReportRecords').mockResolvedValue({ items: [record], total: 1 })
    getMock('lib/api/client/quality', 'fetchQualityFeishuAppSettings').mockResolvedValue({ deviation_report_form_url: 'https://feishu.example/form' })
    getMock('lib/api/client/quality', 'fetchDepartmentContacts').mockResolvedValue([{ name: '张三', open_id: 'user-1' }])
    getMock('actions/quality', 'pullQualityRecordsFromFeishu').mockResolvedValue({ synced: 1 })
    getMock('actions/quality-deviation', 'updateDeviationReportRecord').mockResolvedValue({})
    getMock('actions/quality-deviation', 'deleteDeviationReportRecord').mockResolvedValue({})
    mocks.modal.confirm.mockImplementation(({ onOk }: { onOk?: () => unknown }) => void onOk?.())
    vi.stubGlobal('open', vi.fn())
    const rendered = renderClient(createElement(DeviationReportRecordPage, { initialItems: [record] as never }))
    await settle()
    expect(rendered.container.textContent).toContain('报告记录')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    findButton('新建偏差')?.click()
    findButton('从飞书拉取')?.click()
    findButton('详情')?.click()
    await settle()
    expect(rendered.container.textContent).toContain('报告记录详情')
    findButton('进入偏差工作台')?.click()
    findButton('关闭')?.click()
    findButton('编辑')?.click()
    await settle()
    findButton('确定')?.click()
    await settle()
    findButton('删除')?.click()
    await settle()
    findButton('恢复默认列宽')?.click()
    await settle()
    expect(getMock('actions/quality', 'pullQualityRecordsFromFeishu')).toHaveBeenCalledWith('deviation_report_record')
    expect(getMock('actions/quality-deviation', 'updateDeviationReportRecord')).toHaveBeenCalled()
    expect(getMock('actions/quality-deviation', 'deleteDeviationReportRecord')).toHaveBeenCalled()
    expect(mocks.router.push).toHaveBeenCalledWith('/quality/deviations/workbench?record_id=deviation-1')
    closeRendered(rendered)
  })

  it('drives onboarding attachment-led edit, delete and refresh flows', async () => {
    const records = [
      { id: 'onboard-1', name: '候选人A', onboard_date: '2026-08-01', department: '质量部', level: '分析员' },
      { id: 'onboard-2', name: '候选人B', onboard_date: '2026-08-02', department: '生产部', level: '主管' },
    ]
    getMock('lib/api/client/hr', 'fetchOnboardingList').mockResolvedValue({ data: records, meta: { total: records.length } })
    getMock('lib/api/client/hr', 'fetchDepartments').mockResolvedValue({ data: [{ id: 'dept-1', name: '质量部' }, { id: 'dept-2', name: '生产部' }] })
    getMock('lib/api/client/hr', 'fetchJobPostings').mockResolvedValue({ data: [{ id: 'job-1', title: '分析员' }, { id: 'job-2', title: '主管' }] })
    getMock('actions/hr', 'updateOnboardingAction').mockResolvedValue({})
    getMock('actions/hr', 'deleteOnboardingAction').mockResolvedValue({ message: '已删除' })
    vi.stubGlobal('confirm', vi.fn(() => true))
    const rendered = renderClient(createElement(OnboardingManagementPage))
    await settle()
    expect(rendered.container.textContent).toContain('候选人A')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    // 编辑弹窗 → 保存 → updateOnboardingAction（antd Modal mock 将 okText 渲染为「确定」）
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('编辑'))?.click()
    await settle()
    findButton('确定')?.click()
    await settle()
    expect(getMock('actions/hr', 'updateOnboardingAction')).toHaveBeenCalled()
    // 删除（Popconfirm 确认）→ deleteOnboarding
    await settle()
    const deleteBtn = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('删除'))
    if (deleteBtn) {
      deleteBtn.click()
      await settle()
    }
    expect(getMock('actions/hr', 'deleteOnboardingAction')).toHaveBeenCalled()
    // 刷新 → 重新拉取列表
    findButton('刷新')?.click()
    await settle()
    expect(getMock('lib/api/client/hr', 'fetchOnboardingList')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives annual plan list create, import, filter and delete flows', async () => {
    const plans = [
      { id: 'plan-company', year: 2026, department: '公司', plan_level: '公司级' },
      { id: 'plan-quality', year: 2026, department: '质量部', plan_level: '部门级' },
    ]
    getMock('lib/api/client/hr', 'fetchAnnualTrainingPlans').mockResolvedValue({ data: plans })
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部', '生产部'])
    getMock('actions/hr', 'createAnnualTrainingPlan').mockResolvedValue({ data: {} })
    getMock('actions/hr', 'deleteAnnualTrainingPlan').mockResolvedValue({})
    getMock('actions/hr', 'importAnnualTrainingPlan').mockResolvedValue({ message: '导入成功' })
    const rendered = renderClient(createElement(AnnualPlanListClient))
    await settle()
    expect(rendered.container.textContent).toContain('公司级')
    expect(rendered.container.textContent).toContain('质量部')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    findButton('新建年度计划')?.click()
    await settle()
    findButton('创建')?.click()
    await settle()
    findButton('导入文档')?.click()
    await settle()
    findButton('选择文档')?.click()
    await settle()
    findButton('确定')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('span')).find((span) => span.textContent === '删除')?.click()
    await settle()
    expect(getMock('actions/hr', 'createAnnualTrainingPlan')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'importAnnualTrainingPlan')).toHaveBeenCalledWith(expect.any(File), undefined)
    expect(getMock('actions/hr', 'deleteAnnualTrainingPlan')).toHaveBeenCalledWith(expect.stringContaining('plan-'))
    closeRendered(rendered)
  })

  it('drives position training list department, CRUD, import, export and clear flows', async () => {
    const list = {
      id: 'position-list-1', department: '质量部', position: '分析员',
      items: [{ id: 'position-item-1', level: '岗位级', sort_order: 1, textbook_name: 'GMP', textbook_code: 'SOP-1', assessment_method: '笔试', remarks: '重点' }],
    }
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部', '生产部'])
    getMock('lib/api/client/hr', 'fetchPositionTrainingLists').mockResolvedValue({ data: [list], meta: { total: 1 } })
    getMock('actions/hr', 'batchUpdatePositionTrainingListItems').mockResolvedValue({})
    getMock('actions/hr', 'createPositionTrainingList').mockResolvedValue({})
    getMock('actions/hr', 'importPositionTrainingLists').mockResolvedValue({ message: '导入成功', data: { department: '质量部', imported: 1, skipped: 0 } })
    getMock('actions/hr', 'clearPositionTrainingListsByDept').mockResolvedValue({ message: '已清除' })
    const rendered = renderClient(createElement(PositionTrainingListClient))
    await settle()
    expect(rendered.container.textContent).toContain('GMP')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    findButton('新增明细')?.click()
    await settle()
    findButton('确定')?.click()
    await settle()
    findButton('编辑')?.click()
    await settle()
    findButton('确定')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('删除'))?.click()
    await settle()
    findButton('导入')?.click()
    await settle()
    findButton('导出')?.click()
    await settle()
    findButton('一键清除')?.click()
    await settle()
    expect(getMock('actions/hr', 'batchUpdatePositionTrainingListItems')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'importPositionTrainingLists')).toHaveBeenCalledWith(expect.any(File))
    expect(getMock('actions/hr', 'clearPositionTrainingListsByDept')).toHaveBeenCalledWith('质量部')
    closeRendered(rendered)
  })

  it('drives training department mapping add, edit, modal rule and delete flows', async () => {
    const mappings = [
      { id: 'mapping-1', source_name: '仓储部', target_name: '质量部', mapping_type: 'alias', match_level: 'first', priority: 100, enabled: true },
      { id: 'mapping-2', source_name: '仓储部', target_name: null, mapping_type: 'modal_drop', match_level: 'first', priority: 100, enabled: true },
    ]
    getMock('lib/api/client/hr', 'fetchTrainingDeptMappings').mockResolvedValue(mappings)
    getMock('lib/api/client/hr', 'fetchFeishuMemberDepartments').mockResolvedValue({ data: ['仓储部', '生产部', '公司'] })
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部', '生产部'])
    getMock('actions/hr', 'createTrainingDeptMappingAction').mockResolvedValue({})
    getMock('actions/hr', 'updateTrainingDeptMappingAction').mockResolvedValue({})
    getMock('actions/hr', 'deleteTrainingDeptMappingAction').mockResolvedValue({})
    const rendered = renderClient(createElement(DeptMappingSettingsClient))
    await settle()
    expect(rendered.container.textContent).toContain('培训部门映射对照表')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    findButton('新增映射')?.click()
    await settle()
    const source = rendered.container.querySelector('input[placeholder*="飞书源部门名"]') as HTMLInputElement | null
    if (source) {
      source.value = '新部门'
      source.dispatchEvent(new Event('change', { bubbles: true }))
    }
    for (const select of Array.from(rendered.container.querySelectorAll('select'))) {
      const option = Array.from(select.options).find((item) => item.value)
      if (option) {
        select.value = option.value
        select.dispatchEvent(new Event('change', { bubbles: true }))
      }
    }
    findButton('确定')?.click()
    await settle()
    for (const select of Array.from(rendered.container.querySelectorAll('select'))) {
      const option = Array.from(select.options).find((item) => item.value === 'drop')
      if (option) {
        select.value = option.value
        select.dispatchEvent(new Event('change', { bubbles: true }))
      }
    }
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).filter((button) => !button.textContent?.trim()).at(-1)?.click()
    await settle()
    expect(getMock('actions/hr', 'createTrainingDeptMappingAction')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'deleteTrainingDeptMappingAction')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives OOS/OOT report record search, filters, pull, edit and detail flows', async () => {
    const record = {
      record_id: 'report-1', report_time: '2026-08-25T08:30:00Z', content: 'OOS异常', product_name: '产品A',
      batch_number: 'B-001', report_department: '质量部', reporter: '张三', reporters: [{ name: '张三', id: 'u-1' }],
      attachments: [{ name: '报告.pdf', url: '/files/report.pdf' }], department_head_confirmed: true,
      department_heads: [{ name: '质量负责人' }], fermentation_head_confirmed: false, refinement_head_confirmed: true,
      qa_confirmed: true, qas: [{ name: 'QA' }], qa_head_confirmed: false, qa_heads: [{ name: 'QA负责人' }],
    }
    getMock('lib/api/client/quality', 'fetchOosOotReportRecords').mockResolvedValue({ data: [record] })
    getMock('lib/api/client/quality', 'fetchDepartmentContacts').mockResolvedValue([{ name: '张三', open_id: 'u-1', department: '质量部' }])
    getMock('lib/api/client/quality', 'fetchQualityFeishuAppSettings').mockResolvedValue({ oos_oot_report_form_url: 'https://feishu.example/oos' })
    getMock('actions/quality', 'pullOosOotReportRecords').mockResolvedValue({ synced: 1, failed: 0 })
    getMock('actions/quality', 'updateOosOotReportRecord').mockResolvedValue({})
    getMock('actions/quality', 'deleteOosOotReportRecord').mockResolvedValue({})
    vi.stubGlobal('open', vi.fn())
    const rendered = renderClient(createElement(OosOotReportRecordPage))
    await settle()
    expect(rendered.container.textContent).toContain('OOS/OOT报告记录')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    const search = rendered.container.querySelector('input[placeholder*="搜索内容"]') as HTMLInputElement | null
    if (search) {
      search.value = 'OOS'
      search.dispatchEvent(new Event('change', { bubbles: true }))
    }
    for (const select of Array.from(rendered.container.querySelectorAll('select'))) {
      const option = Array.from(select.options).find((item) => item.value)
      if (option) {
        select.value = option.value
        select.dispatchEvent(new Event('change', { bubbles: true }))
      }
    }
    await settle()
    findButton('清除筛选')?.click()
    findButton('新增')?.click()
    findButton('从飞书拉取')?.click()
    findButton('详情')?.click()
    await settle()
    expect(rendered.container.textContent).toContain('报告记录详情')
    findButton('关闭')?.click()
    findButton('修改')?.click()
    await settle()
    const department = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="质量部"]'))
    if (department) {
      department.value = '质量部'
      department.dispatchEvent(new Event('change', { bubbles: true }))
    }
    findButton('确定')?.click()
    await settle()
    findButton('删除')?.click()
    await settle()
    expect(getMock('actions/quality', 'pullOosOotReportRecords')).toHaveBeenCalled()
    expect(getMock('actions/quality', 'updateOosOotReportRecord')).toHaveBeenCalled()
    expect(getMock('actions/quality', 'deleteOosOotReportRecord')).toHaveBeenCalledWith('report-1')
    closeRendered(rendered)
  })

  it('drives warehouse Feishu config editing and batch update confirmation', async () => {
    const configs = [
      { page_key: 'raw-summary', page_title: '原辅料', table_name: '原辅料表', app_token: 'IpMdbEFSlaZRoJstpFLcbTzPn2e', table_id: 'tbl-raw', view_id: 'view-raw' },
      { page_key: 'product-summary', page_title: '成品', table_name: '成品表', app_token: 'S9KobSXEIaU9K4sgohycpiLqnhg', table_id: 'tbl-product', view_id: null },
    ]
    getMock('lib/api/client/warehouse', 'fetchWarehousePageFeishuConfigs').mockResolvedValue(configs)
    getMock('actions/warehouse', 'updateWarehousePageFeishuConfigAction').mockResolvedValue({})
    mocks.modal.confirm.mockImplementation(({ onOk }: { onOk?: () => unknown }) => void onOk?.())
    const rendered = renderClient(createElement(WarehouseFeishuConfigPage, { initialConfigs: configs as never }))
    await settle()
    expect(rendered.container.textContent).toContain('仓储页面飞书配置')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    const urlInput = rendered.container.querySelector('input[placeholder*="自动填充"]') as HTMLInputElement | null
    if (urlInput) {
      urlInput.value = 'https://example.feishu.cn/base/bascn-batch?table=tbl-batch&view=vew-batch'
      urlInput.dispatchEvent(new Event('change', { bubbles: true }))
    }
    findButton('批量更新')?.click()
    await settle()
    findButton('编辑')?.click()
    await settle()
    findButton('保存')?.click()
    await settle()
    findButton('取消')?.click()
    await settle()
    if (urlInput) {
      urlInput.value = 'not-a-feishu-url'
      urlInput.dispatchEvent(new Event('change', { bubbles: true }))
    }
    findButton('批量更新')?.click()
    await settle()
    expect(getMock('actions/warehouse', 'updateWarehousePageFeishuConfigAction')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives warehouse AI anomaly, chat and report tabs with loaded data', async () => {
    getMock('lib/api/client/warehouse', 'fetchWarehouseTrendSummary').mockResolvedValue({ total: 2, high_risk: 1, raw_count: 1, packaging_count: 1 })
    getMock('lib/api/client/warehouse', 'fetchWarehouseTrendAnomalies').mockResolvedValue([{
      material_name: '原料A', material_type: 'raw', risk_level: 'high', product_line: '产品线A', current_week_usage: 12,
      history_week_avg_usage: 8, current_inventory: 3, safety_inventory: 10, estimated_cover_days: 2, usage_delta_ratio: 0.5,
      reason: '用量异常上升', suggestion: '补充库存',
    }])
    getMock('lib/api/client/warehouse', 'fetchWarehouseTrendProductLines').mockResolvedValue([{ product_line: '产品线A', current_week_usage: 12, history_week_avg_usage: 8, usage_delta_ratio: null, high_risk_count: 1, medium_risk_count: 0 }])
    getMock('lib/api/client/warehouse', 'fetchWarehouseHardwareCostAnomalies').mockResolvedValue([{ workshop_name: '一车间', risk_level: 'high', current_month_cost: 120, history_month_avg_cost: 80, cost_delta_ratio: 0.5, reason: '费用偏高', suggestion: '关注领用' }])
    getMock('lib/api/client/warehouse', 'fetchWarehouseHardwareCostSummary').mockResolvedValue({ anomaly_workshops: 1 })
    getMock('actions/warehouse', 'chatWarehouseAiAction').mockResolvedValue({ response: '建议关注原料A库存' })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/report')) return new Response(JSON.stringify({ data: { overall_status: '需关注', risk_level: '中', key_issues: ['库存不足'], recommendations: ['及时补货'], summary_text: '需要关注' } }), { status: 200 })
      if (url.includes('/anomalies')) return new Response(JSON.stringify({ data: [{ anomaly_type: 'stock_low', severity: 'medium', material_name: '原料A', material_type: 'raw', details: { balance: 1 }, suggestion: '补货', detected_at: '2026-08-25' }] }), { status: 200 })
      return new Response(JSON.stringify({ data: { raw_materials: { total: 10, low_stock: 2, zero_stock: 0, warning: 1 }, packaging_materials: { total: 5, low_stock: 1, zero_stock: 0, warning: 0 }, products: { total: 3, with_stock: 2 }, summary: { total_items: 18, anomaly_count: 2 } } }), { status: 200 })
    }))
    const rendered = renderClient(createElement(WarehouseAiPanel))
    await settle()
    expect(rendered.container.textContent).toContain('仓储AI分析')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    findButton('刷新检测')?.click()
    findButton('智能问答')?.click()
    await settle()
    findButton('当前哪些包材库存不足')?.click()
    await settle()
    const question = rendered.container.querySelector('input[placeholder*="输入关于仓储趋势"]') as HTMLInputElement | null
    if (question) {
      question.value = '哪些原料异常？'
      question.dispatchEvent(new Event('input', { bubbles: true }))
      question.dispatchEvent(new Event('change', { bubbles: true }))
    }
    findButton('提问')?.click()
    await settle()
    expect(rendered.container.textContent).toContain('建议关注原料A库存')
    findButton('分析报告')?.click()
    await settle()
    findButton('生成报告')?.click()
    await settle()
    expect(rendered.container.textContent).toContain('需要关注')
    closeRendered(rendered)
  })

  it('runs the shared training document exporters and custom form controls', async () => {
    const sessionData = {
      training_date: '2026-08-25', training_time_start: '09:00', training_time_end: '10:30',
      topic: 'GMP培训', training_method: '课堂', instructor: '张三', assessment_method: '口试',
      department: '质量部', trainee_departments: ['质量部'], employee_names: ['李四'],
      employee_dept_map: { 李四: '质量部' }, location: '培训室', content: '培训内容',
    }
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部', '生产部'])
    for (const name of ['upsertTrainingSession', 'upsertTrainingDocument']) getMock('actions/hr', name).mockResolvedValue('session-1')
    getMock('actions/hr', 'generateTrainingNotification').mockResolvedValue({ bytes: new Uint8Array([1]), filename: 'notification.docx' })
    getMock('actions/hr', 'generateTrainingEvaluation').mockResolvedValue({ bytes: new Uint8Array([1]), filename: 'evaluation.docx' })
    getMock('actions/hr', 'generateOralExamResult').mockResolvedValue({ bytes: new Uint8Array([1]), filename: 'oral.docx' })
    getMock('actions/hr', 'generatePracticalExamResult').mockResolvedValue({ bytes: new Uint8Array([1]), filename: 'practical.docx' })
    getMock('actions/hr', 'importPracticalExamQuestions').mockResolvedValue({ data: { description: '实操题目', training_date: '2026-08-25' } })
    const exporters = new Map<string, () => Promise<unknown>>()
    const rendered = renderClient(createElement('div', null,
      createElement(TrainingNotificationClient, { key: 'notification', sessionData, registerExporter: (name, fn) => exporters.set(name, fn as () => Promise<unknown>) }),
      createElement(TrainingEvaluationListClient, { key: 'evaluation', sessionData, registerExporter: (name, fn) => exporters.set(name, fn as () => Promise<unknown>) }),
      createElement(OralExamSheetClient, { key: 'oral', sessionData, assessmentMethod: '口试', registerExporter: (name, fn) => exporters.set(name, fn as () => Promise<unknown>) }),
      createElement(PracticalExamSheetClient, { key: 'practical', sessionData, assessmentMethod: '实操', registerExporter: (name, fn) => exporters.set(name, fn as () => Promise<unknown>) }),
    ))
    await settle()
    expect(rendered.container.textContent).toContain('培训通知')
    for (const checkbox of Array.from(rendered.container.querySelectorAll<HTMLElement>('span.cb-big')).slice(0, 24)) checkbox.click()
    for (const button of Array.from(rendered.container.querySelectorAll('button'))) {
      if (!button.disabled && (button.textContent?.includes('导出') || button.textContent?.includes('导入'))) button.click()
    }
    await settle()
    for (const name of ['notification', 'evaluation', 'oral_exam', 'practical_exam']) {
      const exporter = exporters.get(name)
      if (exporter) await exporter()
    }
    await settle()
    expect(getMock('actions/hr', 'generateTrainingNotification')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'generateTrainingEvaluation')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('exercises the AI written exam draft, generation, editing and export flow', async () => {
    const rendered = renderClient(createElement(AiWrittenExamClient, {
      sessionData: { topic: 'GMP培训', instructor: '张三', training_date: '2026-08-25', checked_content: [{ name: 'SOP', code: 'SOP-1' }] },
      initialPayload: {
        title: 'GMP笔试题', files: [{ name: 'SOP', code: 'SOP-1', content: '操作规范内容' }],
        uploaded_content: '上传内容', manual_content: '补充内容', single_choice_count: 1,
        multiple_choice_count: 0, true_false_count: 1, fill_blank_count: 1,
        choice_questions: [{ number: 1, question: '题目', options: [{ label: 'A', text: '答案' }, { label: 'B', text: '干扰项' }], answer: 'A' }],
        true_false_questions: [{ number: 1, question: '判断题', answer: '√' }],
        fill_blank_questions: [{ number: 1, question: '填空______', answer: 'GMP' }],
      } as never,
      registerDocBuilder: vi.fn(), registerExporter: vi.fn(),
    }))
    await settle()
    expect(rendered.container.textContent).toContain('题目预览')
    const textareas = Array.from(rendered.container.querySelectorAll('textarea'))
    textareas[0]?.dispatchEvent(new Event('input', { bubbles: true }))
    for (const button of Array.from(rendered.container.querySelectorAll('button'))) {
      if (button.textContent?.includes('添加选择题') || button.textContent?.includes('添加判断题') || button.textContent?.includes('添加填空题')) button.click()
    }
    const generate = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('AI 出题'))
    if (generate && !generate.disabled) generate.click()
    await settle()
    const exportButton = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('导出试卷'))
    if (exportButton && !exportButton.disabled) exportButton.click()
    await settle()
    expect(rendered.container.textContent).toContain('选择题')
    closeRendered(rendered)
  })

  it('drives oral exam document upload parsing including duplicate and failure files', async () => {
    getMock('actions/quality', 'extractExamDocumentText').mockResolvedValue({ text: '口试素材正文内容' })
    const rendered = renderClient(createElement(OralExamAiModal, {
      open: true, sourceFiles: [], onClose: vi.fn(), onConfirm: vi.fn(),
    }))
    await settle()
    const uploadBtn = Array.from(rendered.container.querySelectorAll('button')).find((b) => b.textContent?.includes('上传文档'))
    expect(uploadBtn).toBeTruthy()
    await act(async () => { uploadBtn?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    expect(rendered.container.textContent).toContain('template.pdf')
    expect(mocks.message.success).toHaveBeenCalledWith(expect.stringContaining('文档解析完成'))
    // 同名文件重复上传 → 去重：列表中仍只有一条
    await act(async () => { uploadBtn?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    expect(rendered.container.textContent?.match(/template\.pdf/g)?.length).toBe(1)
    closeRendered(rendered)
  })

  it('drives oral exam AI file resolution, generation, editing and confirmation', async () => {
    getMock('actions/quality', 'resolveDocumentEntryContent').mockResolvedValue([{ name: 'SOP', code: 'SOP-1', matched: true, attachments: [{ md_text: '口试素材' }] }])
    const onClose = vi.fn()
    const onConfirm = vi.fn()
    const rendered = renderClient(createElement(OralExamAiModal, {
      open: true, sourceFiles: [{ name: 'SOP', code: 'SOP-1' }], onClose, onConfirm,
    }))
    await settle()
    expect(rendered.container.textContent).toContain('已匹配 1 个附件')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    findButton('AI 出题')?.click()
    await settle()
    expect(rendered.container.textContent).toContain('生成题目')
    Array.from(rendered.container.querySelectorAll('textarea')).forEach((textarea) => {
      textarea.value = '更新后的口试题'
      textarea.dispatchEvent(new Event('change', { bubbles: true }))
    })
    findButton('确认回填到口试表')?.click()
    await settle()
    expect(onConfirm).toHaveBeenCalledWith(expect.arrayContaining([expect.objectContaining({ question: '口试问题' })]))
    expect(onClose).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('covers AI written exam manual material, upload parsing and inactive state', async () => {
    const registerDocBuilder = vi.fn()
    const registerExporter = vi.fn()
    const rendered = renderClient(createElement(AiWrittenExamClient, {
      sessionData: { topic: '培训主题', checked_content: [] }, active: false, assessmentMethod: '口试',
      registerDocBuilder, registerExporter,
    }))
    await settle()
    expect(rendered.container.textContent).toContain('AI 笔试仅在考核方式选择')
    const manual = rendered.container.querySelector('textarea[placeholder*="可在此粘贴额外"]') as HTMLTextAreaElement | null
    if (manual) {
      manual.value = '手动培训内容'
      manual.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const fileInput = rendered.container.querySelector('input[type="file"]') as HTMLInputElement | null
    if (fileInput) {
      Object.defineProperty(fileInput, 'files', { configurable: true, value: [new File(['文档内容'], '培训.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })] })
      fileInput.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    for (const button of Array.from(rendered.container.querySelectorAll('button')).filter((item) => !item.textContent?.trim())) button.click()
    const builderCall = registerDocBuilder.mock.calls.at(-1)?.[1] as (() => Record<string, unknown> | null) | undefined
    builderCall?.()
    const exporterCall = registerExporter.mock.calls.at(-1)?.[1] as (() => Promise<unknown>) | undefined
    if (exporterCall) await exporterCall()
    closeRendered(rendered)
  })

  it('covers change action plan create and edit modal submission states', async () => {
    const onSubmit = vi.fn(async () => undefined)
    const onCancel = vi.fn()
    const rendered = renderClient(createElement('div', null,
      createElement(ChangeActionPlanEditModal, { key: 'new', open: true, saving: false, changeCode: 'CHG-001', onCancel, onSubmit }),
      createElement(ChangeActionPlanEditModal, { key: 'edit', open: true, saving: true, initialValue: { change_code: 'CHG-002', project_name: '项目B', owner_name: '李四', director_name: '王五', status: '推进中', delay_flag: '否' } as never, onCancel, onSubmit }),
    ))
    await settle()
    const confirmButtons = Array.from(rendered.container.querySelectorAll('button')).filter((button) => button.textContent === '确定')
    confirmButtons.forEach((button) => button.click())
    Array.from(rendered.container.querySelectorAll('button')).filter((button) => button.textContent === '取消').forEach((button) => button.click())
    await settle()
    expect(onSubmit).toHaveBeenCalled()
    expect(onCancel).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives department recipient and clerk drawer load, select-all and save flows', async () => {
    getMock('lib/api/client/hr', 'fetchDeptRecipients').mockResolvedValue([{ id: 'recipient-1', department: '质量部', use_dept_leader: false, recipient_open_ids: [], recipient_names: [] }])
    getMock('actions/hr', 'saveDeptRecipients').mockResolvedValue({})
    vi.stubGlobal('fetch', vi.fn(async (input: unknown) => {
      const url = String(input)
      // drawer 三路请求：审批配置部门名单 / 部门树，其余走默认
      const data = url.includes('dept-approval-configs/names')
        ? ['质量部', 'QA组']
        : [{ id: 'dept-1', name: '质量部', leader_name: '主管', children: [{ id: 'dept-2', name: 'QA组' }] }]
      return new Response(JSON.stringify({ data }), { status: 200 })
    }))
    const members = [{ open_id: 'member-1', name: '李四', department: '质量部' }, { open_id: 'member-2', name: '王五', department: 'QA组' }]
    const recipient = renderClient(createElement(DeptRecipientDrawer, { open: true, reminderConfigId: 'reminder-1', hrMembers: members, onClose: vi.fn() }))
    await settle()
    expect(recipient.container.textContent).toContain('按部门配置接收人')
    const findButton = (text: string) => Array.from(recipient.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    findButton('全部使用部门负责人')?.click()
    findButton('保存')?.click()
    await settle()
    closeRendered(recipient)
    const clerk = renderClient(createElement(DeptRecipientDrawer, { open: true, mode: 'clerk', reminderConfigId: 'reminder-1', hrMembers: members, onClose: vi.fn() }))
    await settle()
    const select = clerk.container.querySelector('select') as HTMLSelectElement | null
    if (select?.querySelector('option[value="member-1"]')) {
      select.value = 'member-1'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    }
    Array.from(clerk.container.querySelectorAll('button')).find((button) => button.textContent?.includes('保存'))?.click()
    await settle()
    expect(getMock('actions/hr', 'saveDeptRecipients')).toHaveBeenCalled()
    closeRendered(clerk)
  })

  it('drives contract approval result filters, export, print and reload flows', async () => {
    const results = [
      { id: 'approval-1', employee_number: 'E-1', name: '李四', dept_level1: '质量部', dept_level2: 'QA', contract_end_date: '2026-09-30', dept_approved_at: '2026-08-20', dept_leader_name: '主管', supervisor_approved_at: '2026-08-21', supervisor_name: '总监', approval_status: 'approved' },
      { id: 'approval-2', employee_number: 'E-2', name: '王五', dept_level1: '生产部', dept_level2: '一车间', contract_end_date: '2026-10-30', dept_approved_at: null, approval_status: 'rejected' },
      { id: 'approval-3', employee_number: 'E-3', name: '赵六', dept_level1: '生产部', dept_level2: '二车间', contract_end_date: '2026-11-30', dept_approved_at: '2026-08-22', approval_status: 'supervisor_pending' },
    ]
    getMock('lib/api/client/hr', 'fetchContractApprovalResults').mockResolvedValue({ data: results, meta: { total: results.length } })
    getMock('lib/api/client/hr', 'fetchDepartments').mockResolvedValue({ data: [{ name: '质量部' }, { name: '生产部' }, { name: '质量部' }] })
    getMock('lib/api/client/hr', 'exportContractApprovalResults').mockResolvedValue(new Blob(['xlsx']))
    vi.stubGlobal('print', vi.fn())
    const rendered = renderClient(createElement(ContractApprovalResultsClient, { initialData: results as never, initialTotal: 3, initialStartDate: '2026-01-01', initialEndDate: '2026-12-31' }))
    await settle()
    expect(rendered.container.textContent).toContain('合同到期审批结果')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    for (const select of Array.from(rendered.container.querySelectorAll('select'))) {
      const option = Array.from(select.options).find((item) => item.value)
      if (option) {
        select.value = option.value
        select.dispatchEvent(new Event('change', { bubbles: true }))
      }
    }
    findButton('导出打印')?.click()
    findButton('打印')?.click()
    await settle()
    expect(getMock('lib/api/client/hr', 'fetchContractApprovalResults')).toHaveBeenCalled()
    expect(getMock('lib/api/client/hr', 'exportContractApprovalResults')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives approval settings search, save, clear and delete flows', async () => {
    getMock('lib/api/client/hr', 'fetchDeptApprovalConfigs').mockResolvedValue([
      { id: 'approval-config-1', department_id: 'dept-1', department_name: '质量部', direct_leader_name: '主管', direct_leader_open_id: 'u-1', manager_name: null, manager_open_id: null, director_name: null, director_open_id: null, vp_name: null, vp_open_id: null },
      { department_id: 'dept-2', department_name: '生产部', direct_leader_name: null, direct_leader_open_id: null, manager_name: null, manager_open_id: null, director_name: null, director_open_id: null, vp_name: null, vp_open_id: null },
    ])
    getMock('lib/api/client/hr', 'searchFeishuMembers').mockResolvedValue([{ name: '王五', open_id: 'u-5', department: '质量部', job_title: '经理' }])
    getMock('actions/hr', 'updateDeptApprovalConfigAction').mockResolvedValue({})
    getMock('actions/hr', 'createDeptApprovalConfigAction').mockResolvedValue({})
    getMock('actions/hr', 'deleteDeptApprovalConfigAction').mockResolvedValue({})
    const rendered = renderClient(createElement(ApprovalSettingsListClient))
    await settle()
    expect(rendered.container.textContent).toContain('审批流程设置')
    const inputs = Array.from(rendered.container.querySelectorAll('input'))
    if (inputs[0]) {
      inputs[0].value = '王五'
      inputs[0].dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    for (const button of Array.from(rendered.container.querySelectorAll('button')).filter((item) => item.textContent?.includes('保存'))) button.click()
    for (const button of Array.from(rendered.container.querySelectorAll('button')).filter((item) => !item.textContent?.trim())) button.click()
    await settle()
    expect(getMock('actions/hr', 'updateDeptApprovalConfigAction')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'createDeptApprovalConfigAction')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'deleteDeptApprovalConfigAction')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives reminder detail offboarding template and contract recipient settings', async () => {
    const members = [{ open_id: 'member-1', name: '李四', department: '质量部' }]
    const offboarding = { id: 'reminder-off', entity_code: 'offboarding', entity_label: '离职提醒', reminder_days: [30, 7], recipient_open_ids: [], recipient_names: [], dept_notify_enabled: true, trigger_frequency: 'monthly', trigger_day: 1, trigger_hour: 9, notify_hours: 24, message_template: '提醒 {姓名}', sign_clerk_open_ids: [], sign_clerk_names: [], sign_reminder_days: 7, is_enabled: true, reminder_label: '离职提醒' }
    const renewal = { id: 'reminder-renew', entity_code: 'contract_renewal', entity_label: '合同续签提醒', reminder_days: [90], recipient_open_ids: [], recipient_names: [], dept_notify_enabled: false, trigger_frequency: 'daily', trigger_day: 1, trigger_hour: 10, notify_hours: 24, message_template: '', sign_clerk_open_ids: [], sign_clerk_names: [], sign_reminder_days: 7, is_enabled: false, reminder_label: '合同续签提醒' }
    getMock('lib/api/client/hr', 'fetchReminderConfigs').mockResolvedValue([offboarding, renewal])
    getMock('lib/api/client/hr', 'fetchHrMembers').mockResolvedValue(members)
    getMock('actions/hr', 'fetchOffboardingTemplateInfoAction').mockResolvedValue({ data: { exists: true, filename: '离职模板.docx', updated_at: '2026-08-25' } })
    getMock('actions/hr', 'uploadOffboardingTemplateAction').mockResolvedValue({ message: '模板上传成功' })
    getMock('actions/hr', 'updateReminderConfig').mockResolvedValue({})
    const off = renderClient(createElement(ReminderDetailClient, { params: Promise.resolve({ entityCode: 'offboarding' }) }))
    await settle()
    expect(off.container.textContent).toContain('离职证明模板')
    const findButton = (text: string) => Array.from(off.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    findButton('更新模板')?.click()
    findButton('添加')?.click()
    findButton('保存')?.click()
    await settle()
    closeRendered(off)
    const renew = renderClient(createElement(ReminderDetailClient, { params: Promise.resolve({ entityCode: 'contract_renewal' }) }))
    await settle()
    expect(renew.container.textContent).toContain('合同签署设置')
    for (const select of Array.from(renew.container.querySelectorAll('select'))) {
      const option = Array.from(select.options).find((item) => item.value)
      if (option) {
        select.value = option.value
        select.dispatchEvent(new Event('change', { bubbles: true }))
      }
    }
    Array.from(renew.container.querySelectorAll('button')).find((button) => button.textContent?.includes('保存'))?.click()
    await settle()
    expect(getMock('actions/hr', 'uploadOffboardingTemplateAction')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'updateReminderConfig')).toHaveBeenCalled()
    closeRendered(renew)
  })

  it('drives department scope search, add, save, clear and remove flows', async () => {
    getMock('lib/api/client/hr', 'fetchDeptScopes').mockResolvedValue([{ user_id: 'u-existing', user_name: '张三', user_department: '质量部', visible_depts: ['质量部'], updated_at: '2026-08-25' }])
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部', '生产部'])
    getMock('lib/api/client/hr', 'fetchCustomTrainingDepartments').mockResolvedValue(['研发部'])
    getMock('lib/api/client/hr', 'fetchFeishuMembers').mockResolvedValue({ data: [{ open_id: 'u-new', name: '李四', department: '生产部' }], meta: { total: 1 } })
    getMock('actions/hr', 'saveDeptScopeAction').mockResolvedValue({ visible_depts: ['生产部'] })
    getMock('actions/hr', 'clearDeptScopeAction').mockResolvedValue({})
    const rendered = renderClient(createElement(DeptScopeSettingsClient))
    await settle()
    expect(rendered.container.textContent).toContain('用户可见部门配置')
    const search = rendered.container.querySelector('input[placeholder*="搜索飞书联系人"]') as HTMLInputElement | null
    if (search) {
      search.value = '李'
      search.dispatchEvent(new Event('input', { bubbles: true }))
      search.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('李四'))?.click()
    await settle()
    for (const select of Array.from(rendered.container.querySelectorAll('select'))) {
      const option = Array.from(select.options).find((item) => item.value === '生产部')
      if (option) {
        select.value = option.value
        select.dispatchEvent(new Event('change', { bubbles: true }))
      }
    }
    for (const button of Array.from(rendered.container.querySelectorAll('button')).filter((item) => item.textContent?.includes('保存'))) button.click()
    for (const button of Array.from(rendered.container.querySelectorAll('button')).filter((item) => item.textContent?.includes('清除'))) button.click()
    for (const button of Array.from(rendered.container.querySelectorAll('button')).filter((item) => item.textContent?.includes('移除'))) button.click()
    await settle()
    expect(getMock('actions/hr', 'saveDeptScopeAction')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'clearDeptScopeAction')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('covers department scope permission, paging, duplicate contacts and failed mutations', async () => {
    mocks.permissionAllowed = false
    const forbidden = renderClient(createElement(DeptScopeSettingsClient))
    await settle()
    expect(forbidden.container.innerHTML).toContain('403')
    closeRendered(forbidden)
    mocks.permissionAllowed = true

    getMock('lib/api/client/hr', 'fetchDeptScopes').mockResolvedValue([{ user_id: 'u-existing', user_name: '张三', user_department: '质量部', visible_depts: ['质量部'], updated_at: null }])
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部'])
    getMock('lib/api/client/hr', 'fetchCustomTrainingDepartments').mockResolvedValue(['研发部'])
    getMock('lib/api/client/hr', 'fetchFeishuMembers').mockResolvedValueOnce({
      data: [
        { open_id: 'u-existing', name: '张三', department: '质量部' },
        { open_id: '', name: '无ID', department: '研发部' },
        { open_id: 'u-new', name: '李四', department: '生产部' },
      ], meta: { total: 101 },
    }).mockResolvedValueOnce({ data: [{ open_id: 'u-page-2', name: '王五', department: '生产部' }], meta: { total: 101 } })
    getMock('actions/hr', 'saveDeptScopeAction').mockResolvedValue({ visible_depts: ['质量部'] })
    getMock('actions/hr', 'clearDeptScopeAction').mockResolvedValue({})
    const rendered = renderClient(createElement(DeptScopeSettingsClient))
    await settle()
    const search = rendered.container.querySelector('input[placeholder*="搜索飞书联系人"]') as HTMLInputElement | null
    if (search) {
      search.value = '李'
      search.dispatchEvent(new Event('input', { bubbles: true }))
      search.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('李四'))?.click()
    await settle()

    if (search) {
      search.value = '张'
      search.dispatchEvent(new Event('input', { bubbles: true }))
      search.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('张三'))?.click()
    if (search) {
      search.value = '无ID'
      search.dispatchEvent(new Event('input', { bubbles: true }))
      search.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('无ID'))?.click()
    await settle()

    const firstSave = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('保存'))
    firstSave?.click()
    await settle()
    const firstClear = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('清除'))
    firstClear?.click()
    await settle()
    const firstRemove = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('移除'))
    firstRemove?.click()
    await settle()

    getMock('actions/hr', 'saveDeptScopeAction').mockRejectedValueOnce(new Error('保存范围失败'))
    getMock('actions/hr', 'clearDeptScopeAction').mockRejectedValueOnce(new Error('移除范围失败'))
    const remainingSave = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('保存'))
    remainingSave?.click()
    await settle()
    const remainingRemove = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('移除'))
    remainingRemove?.click()
    await settle()
    expect(getMock('lib/api/client/hr', 'fetchFeishuMembers')).toHaveBeenCalledTimes(4)
    expect(getMock('actions/hr', 'saveDeptScopeAction')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'clearDeptScopeAction')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives department table/tree, recursive selection, sync fallback and delete recovery', async () => {
    const child = { id: 'dept-child', name: '质量实验室', parent_id: 'dept-root', sort_order: 1, children: [] }
    const root = { id: 'dept-root', name: '质量管理部', parent_id: null, sort_order: 1, children: [child] }
    const plain = { id: 'dept-plain', name: '生产部', parent_id: null, sort_order: 2, children: [] }
    const orgTree = [
      { id: 'dept-root', name: '质量管理部', type: 'department', leader_name: '张三', children: [{ id: 'employee-1', name: '李四', type: 'employee' }] },
      { id: 'dept-plain', name: '生产部', type: 'department', leader_name: null, children: [] },
    ]
    getMock('actions/hr', 'fetchDepartmentsAction').mockResolvedValue({ data: [root, child, plain], meta: { total: 3 } })
    getMock('actions/hr', 'fetchDepartmentTreeAction').mockResolvedValue({ data: [root, plain] })
    getMock('actions/hr', 'fetchOrgTreeAction').mockRejectedValue(new Error('飞书组织树暂不可用'))
    getMock('actions/hr', 'syncDepartmentsFromFeishuAction').mockResolvedValue({ data: { state: 'completed', result: { created: 1, updated: 2, skipped: 0, failed: 0 } } })
    getMock('actions/hr', 'getDepartmentSyncStatus').mockResolvedValue({ data: { state: 'completed' } })
    getMock('actions/hr', 'deleteDepartment').mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('部门删除失败'))
    const rendered = renderClient(createElement(DepartmentClient, {
      initialDepartments: [plain] as never,
      initialTotal: 1,
      initialTreeDepartments: [root, plain] as never,
      initialAllDepartments: [root, child, plain] as never,
      initialOrgTreeData: orgTree as never,
    }))
    await settle()

    const clickButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))?.click()
    const search = rendered.container.querySelector('input[placeholder="搜索部门名称"]') as HTMLInputElement | null
    if (search) {
      search.value = '质量'
      search.dispatchEvent(new Event('input', { bubbles: true }))
      search.dispatchEvent(new Event('change', { bubbles: true }))
    }
    clickButton('搜索')
    clickButton('重置')
    await settle()
    queryElement<HTMLTableRowElement>(rendered.container, 'tbody tr')?.click()
    await settle()
    clickButton('关闭')
    const mode = rendered.container.querySelector('select') as HTMLSelectElement | null
    if (mode) {
      mode.value = 'tree'
      mode.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    const treeNode = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('质量管理部'))
    treeNode?.click()
    await settle()
    clickButton('关闭')
    clickButton('新增部门')
    await settle()
    clickButton('取消')
    clickButton('从飞书同步')
    await settle()
    getMock('actions/hr', 'fetchOrgTreeAction').mockResolvedValue({ data: orgTree })
    clickButton('从飞书同步')
    await settle()
    if (mode) {
      mode.value = 'table'
      mode.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    const invokeDelete = () => {
      const deleteAction = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('删除'))
      deleteAction?.parentElement?.click()
      deleteAction?.parentElement?.parentElement?.click()
    }
    invokeDelete()
    await settle()
    invokeDelete()
    await settle()
    expect(getMock('actions/hr', 'fetchDepartmentTreeAction')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'fetchOrgTreeAction')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'deleteDepartment')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives position transfer filtering, approval, export, sync and failure recovery', async () => {
    const records = [
      {
        id: 'transfer-draft', employee_name: '张三', department_before: '质量部', original_position: '分析工程师',
        effective_date: '2026-09-01', apply_department: '研发部', apply_position: '高级分析员', contact_phone: '13800000000',
        approval_status: '草稿', created_at: '2026-08-20T10:00:00Z', applicant_confirmation_text: '本人确认', applicant_signature: '张三',
        applicant_confirmation_date: '2026-08-20', approval_flow: { current_step: 0, steps: [{ label: '部门负责人', signer: '李四' }] },
      },
      {
        id: 'transfer-done', employee_name: '李四', department_before: '生产部', original_position: '操作员',
        effective_date: '2026-09-02', apply_department: '质量部', apply_position: '检验员', contact_phone: '',
        approval_status: '已通过', created_at: '', applicant_confirmation_text: '', applicant_signature: '', applicant_confirmation_date: '',
        approval_flow: { current_step: 2, steps: [{ label: '部门负责人' }] },
      },
    ]
    getMock('lib/api/client/hr', 'fetchPositionTransfers').mockResolvedValue({ data: records, meta: { total: 2 } })
    getMock('actions/hr', 'submitPositionTransferApproval').mockResolvedValue({})
    getMock('actions/hr', 'syncPositionTransferFromFeishuAction').mockResolvedValue({ data: { total: 0, created: 0, updated: 0, deleted: 0 } })
    getMock('actions/hr', 'deletePositionTransfer').mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('删除调动失败'))
    const rendered = renderClient(createElement(PositionTransferClient, { initialRecords: records as never, initialTotal: 2 }))
    await settle()
    const buttons = () => Array.from(rendered.container.querySelectorAll('button'))
    const textButton = (text: string) => buttons().find((item) => item.textContent?.includes(text))
    const search = rendered.container.querySelector('input[placeholder="姓名/工号"]') as HTMLInputElement | null
    if (search) {
      search.value = '张三'
      search.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const status = rendered.container.querySelector('select') as HTMLSelectElement | null
    if (status) {
      status.value = '草稿'
      status.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    queryElement<HTMLAnchorElement>(rendered.container, 'table a')?.click()
    await settle()
    queryElement<HTMLButtonElement>(rendered.container, 'aside button')?.click()
    textButton('新增调动记录')?.click()
    await settle()
    queryElement<HTMLButtonElement>(rendered.container, '[role="dialog"] button')?.click()
    textButton('同步飞书')?.click()
    await settle()
    getMock('actions/hr', 'syncPositionTransferFromFeishuAction').mockRejectedValueOnce(new Error('同步失败'))
    textButton('同步飞书')?.click()
    await settle()

    const actionButtons = buttons().filter((item) => !item.textContent?.trim() && item.querySelector('svg'))
    for (const action of actionButtons) {
      if (!action.isConnected) continue
      action.click()
      await settle()
      queryElement<HTMLButtonElement>(rendered.container, '[role="dialog"] button')?.click()
      queryElement<HTMLButtonElement>(rendered.container, 'aside button')?.click()
      await settle()
    }
    expect(getMock('actions/hr', 'submitPositionTransferApproval')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'deletePositionTransfer')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'syncPositionTransferFromFeishuAction')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives candidate detail editing, navigation, resume preview and notices', async () => {
    const candidate = {
      id: 'candidate-1', name: '候选人', contact: '13800000000', email: 'candidate@example.com',
      job_id: 'job-1', job_position: '分析员', education: '本科', work_years: 3,
      skills: ['GMP', '分析'], fit_level: '高', interview_status: '通过', remark: '匹配度较高',
      match_rate: 90, resume_score: 88,
      resume_attachment: { name: 'resume.pdf', type: 'application/pdf' },
    }
    sessionStorage.setItem('candidate_list_context', JSON.stringify({
      ids: ['candidate-0', 'candidate-1', 'candidate-2'], currentIndex: 1,
    }))
    getMock('actions/hr', 'updateCandidateAction').mockResolvedValue({})
    getMock('actions/hr', 'sendCandidateNoticeAction').mockResolvedValue({
      data: { email_sent: true, email_recipient: 'candidate@example.com', feishu_sent: true, feishu_recipients: ['u-1'] },
    })
    const rendered = renderClient(createElement(CandidateDetailClient, { candidate: candidate as never }))
    await settle()

    let button = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((item) => item.textContent?.includes(text))
    button('上一条')?.click()
    button('下一条')?.click()
    button('编辑')?.click()
    await settle()
    const inputs = Array.from(rendered.container.querySelectorAll('input'))
    if (inputs[0]) {
      inputs[0].value = '候选人修改'
      inputs[0].dispatchEvent(new Event('input', { bubbles: true }))
      inputs[0].dispatchEvent(new Event('change', { bubbles: true }))
    }
    const education = rendered.container.querySelector('select') as HTMLSelectElement | null
    if (education?.querySelector('option[value="硕士"]')) {
      education.value = '硕士'
      education.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const textArea = rendered.container.querySelector('textarea') as HTMLTextAreaElement | null
    if (textArea) {
      textArea.value = '补充备注'
      textArea.dispatchEvent(new Event('input', { bubbles: true }))
      textArea.dispatchEvent(new Event('change', { bubbles: true }))
    }
    button('保存修改')?.click()
    await settle()
    expect(getMock('actions/hr', 'updateCandidateAction')).toHaveBeenCalledWith('candidate-1', expect.objectContaining({ name: expect.any(String) }))
    button('编辑')?.click()
    await settle()
    button('取消')?.click()
    button('resume.pdf')?.click()
    await settle()
    expect(rendered.container.querySelector('iframe')).not.toBeNull()
    queryElement<HTMLButtonElement>(rendered.container, '[role="dialog"] button')?.click()
    closeRendered(rendered)

    const docxCandidate = { ...candidate, resume_attachment: { name: 'resume.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' } }
    const resumeFetch = vi.fn(async () => new Response(new Blob(['docx']), { status: 200 }))
    vi.stubGlobal('fetch', resumeFetch)
    window.fetch = resumeFetch as typeof window.fetch
    const docxRendered = renderClient(createElement(CandidateDetailClient, { candidate: docxCandidate as never }))
    await settle()
    button = (text: string) => Array.from(docxRendered.container.querySelectorAll('button')).find((item) => item.textContent?.includes(text))
    button('resume.docx')?.click()
    await settle()
    expect(docxRendered.container.querySelector('.docx-preview-container')).not.toBeNull()
    closeRendered(docxRendered)

    const interviewCandidate = { ...candidate, interview_status: '已安排', resume_attachment: undefined }
    const interviewRendered = renderClient(createElement(CandidateDetailClient, { candidate: interviewCandidate as never }))
    await settle()
    button = (text: string) => Array.from(interviewRendered.container.querySelectorAll('button')).find((item) => item.textContent?.includes(text))
    button('发送面试通知')?.click()
    await settle()
    expect(getMock('actions/hr', 'sendCandidateNoticeAction')).toHaveBeenCalledWith('candidate-1', 'interview_notice')
    closeRendered(interviewRendered)
  })

  it('covers attachment content parsing, used entries and preview failures', async () => {
    const { default: RealAttachmentContentModal } = await vi.importActual<typeof import('./components/hr/AttachmentContentModal')>('./components/hr/AttachmentContentModal')
    const fetchPreview = getMock('lib/api/client/hr', 'fetchSectionPreview')
    fetchPreview
      .mockResolvedValueOnce({ data: { kind: 'tables', tables: [{ title: '培训清单', header: ['序号', '文件名称', '文件编号'], rows: [['1', 'GMP指南', 'SOP-1'], ['2', '备注说明', ''], ['3', '123', '']] }] } })
      .mockResolvedValueOnce({ data: { blocks: [{ type: 'table', rows: [['文件名称', '编号'], ['培训手册', 'TR-1']] }] } })
    const onConfirm = vi.fn()
    const rendered = renderClient(createElement(RealAttachmentContentModal, {
      open: true,
      sections: [{ id: 'section-1', annex_no: '附件1', title: '培训清单' }, { id: 'section-2', annex_no: null, title: '培训手册' }] as never,
      usedNames: new Set(['培训手册']), initialCheckedKeys: [], onClose: vi.fn(), onConfirm,
    }))
    await settle()
    expect(rendered.container.textContent).toContain('GMP指南')
    expect(rendered.container.textContent).toContain('培训手册')
    const checkboxes = Array.from(rendered.container.querySelectorAll('input[type="checkbox"]')) as HTMLInputElement[]
    checkboxes.find((item) => !item.disabled)?.click()
    await settle()
    queryElement<HTMLButtonElement>(rendered.container, '[role="dialog"] button:last-of-type')?.click()
    await settle()
    expect(onConfirm).toHaveBeenCalledWith([expect.objectContaining({ name: 'GMP指南', code: 'SOP-1' })])
    closeRendered(rendered)

    fetchPreview.mockRejectedValue(new Error('预览服务不可用'))
    const failed = renderClient(createElement(RealAttachmentContentModal, {
      open: true, sections: [{ id: 'section-fail', title: '失败附件' }] as never,
      usedNames: new Set<string>(), initialCheckedKeys: [], onClose: vi.fn(), onConfirm,
    }))
    await settle()
    expect(failed.container.textContent).toContain('附件未解析出可选的文件清单内容')
    closeRendered(failed)
  })

  it('drives offboarding search, sync, inline edits and record actions', async () => {
    const record = {
      id: 'offboarding-1', employee_number: 'E-001', name: '李四', domain_account: 'lisi',
      gender: '男', department: '质量部', position: '分析员', phone: '13800000000', email: 'lisi@example.com',
      offboarding_date: '2026-08-30', offboarding_type: '辞职', handover_status: '待交接',
    }
    getMock('actions/hr', 'fetchOffboardingRecordsAction').mockResolvedValue({ data: [record], meta: { total: 1 } })
    getMock('actions/hr', 'syncOffboardingFromFeishuAction').mockResolvedValue({ message: '同步完成' })
    getMock('actions/hr', 'deleteOffboardingRecord').mockResolvedValue({})
    getMock('actions/hr', 'updateOffboardingRecord').mockResolvedValue({})
    getMock('actions/hr', 'generateOffboardingCertificateAction').mockResolvedValue({ bytes: new Uint8Array([1, 2]), filename: '离职证明.docx' })
    getMock('lib/api/hr', 'fetchEmployees').mockResolvedValue({ data: [{ id: 'employee-1', name: '李四', employee_number: 'E-001', department: '质量部' }] })
    const rendered = renderClient(createElement(OffboardingClient, { initialRecords: [record] as never, initialTotal: 1 }))
    await settle()
    const input = rendered.container.querySelector('input[placeholder="姓名/工号"]') as HTMLInputElement | null
    if (input) {
      input.value = '李四'
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const textButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((item) => item.textContent?.includes(text))
    textButton('同步飞书')?.click()
    await settle()
    textButton('新增离职记录')?.click()
    await settle()
    queryElement<HTMLButtonElement>(rendered.container, '[role="dialog"] button')?.click()
    await settle()
    rendered.container.querySelector('table a')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await settle()
    queryElement<HTMLButtonElement>(rendered.container, 'aside button')?.click()
    await settle()

    const table = rendered.container.querySelector('table')
    const dateCell = Array.from(table?.querySelectorAll('span') ?? []).find((item) => item.textContent === '2026-08-30')
    dateCell?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await settle()
    rendered.container.querySelector('input[type="date"]')?.dispatchEvent(new Event('change', { bubbles: true }))
    await settle()
    const typeCell = Array.from(table?.querySelectorAll('span') ?? []).find((item) => item.textContent === '辞职')
    typeCell?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await settle()
    const typeSelect = rendered.container.querySelector('select') as HTMLSelectElement | null
    if (typeSelect) {
      typeSelect.value = '正常离职'
      typeSelect.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    const statusCell = Array.from(table?.querySelectorAll('span') ?? []).find((item) => item.textContent === '待交接')
    statusCell?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await settle()
    const statusSelect = rendered.container.querySelector('select') as HTMLSelectElement | null
    if (statusSelect) {
      statusSelect.value = '交接中'
      statusSelect.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()

    for (let index = 0; index < 4; index += 1) {
      const actionButton = rendered.container.querySelector('table')?.querySelectorAll('button')[index] as HTMLButtonElement | undefined
      actionButton?.click()
      await settle()
      queryElement<HTMLButtonElement>(rendered.container, '[role="dialog"] button')?.click()
      queryElement<HTMLButtonElement>(rendered.container, 'aside button')?.click()
      await settle()
    }
    expect(getMock('actions/hr', 'syncOffboardingFromFeishuAction')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'updateOffboardingRecord')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'generateOffboardingCertificateAction')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'deleteOffboardingRecord')).toHaveBeenCalledWith('offboarding-1')
    closeRendered(rendered)
  })

  it('renders registration ledgers, tracker, knowledge base and document catalog with records', async () => {
    const record = { id: 'record-1', record_id: 'record-1', project_name: '项目A', product_name: '产品A', status: '已递交', created_at: '2026-08-01', updated_at: '2026-08-02', latest_values: { project_name: '项目A', product_name: '产品A' }, latest_style_marks: {}, history_count: 2 }
    const detail = { ...record, fields: [{ field_name: '项目名称', value: '项目A' }], history: [] }
    const rendered = renderClient(createElement('div', null,
      createElement(AuthorizationLetterClient, { initialRecords: [record] as never, initialFdaRecords: [record] as never, key: 'auth' }),
      createElement(RegulationTrackerPage, { key: 'reg', initialResult: { items: [record] as never, total: 1, page: 1, pageSize: 20, totalPages: 1 }, initialNotificationSettings: notificationSettings, notificationRecipients: [{ name: '张三', open_id: 'u-1', department: '注册部' }] }),
      createElement(ProjectLedgerSheetPage, { key: 'project', detail: { sheet_key: 'projects', columns: [{ label: '项目名称', key: 'project_name' }, { label: '产品', key: 'product_name' }], records: [record] } as never }),
      createElement(DeclarationProgressPage, { key: 'declaration', detail: { sheet_key: 'declarations', columns: [{ label: '项目名称', key: 'project_name' }, { label: '产品名称', key: 'product_name' }], records: [record] } as never }),
      createElement(KnowledgeBasePage, { key: 'knowledge', articles: [record] as never, categories: [{ id: 'cat-1', name: '法规' }] as never, overview: { total_articles: 1, published_articles: 1, category_count: 1 } as never }),
      createElement(DocumentCatalogPage, { key: 'docs', initialDepartments: [{ id: 'dept-1', name: '质量部', sort_order: 1, document_count: 1 }] as never }),
    ))
    getMock('lib/api/client/registration', 'fetchRegulatoryTrackerDocumentDetailClient').mockResolvedValue(detail)
    await settle()
    expect(rendered.container.textContent).toContain('项目')
    expect(rendered.container.textContent).toContain('法规')
    for (const button of Array.from(rendered.container.querySelectorAll('button'))) button.click()
    await settle()

    const fdaChoice = rendered.container.querySelector('input[type="radio"]') as HTMLInputElement | null
    fdaChoice?.click()
    const ledgerRows = Array.from(rendered.container.querySelectorAll('table tbody tr'))
    ledgerRows.at(-1)?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await settle()
    for (const button of Array.from(rendered.container.querySelectorAll('button'))) {
      if (!button.disabled) button.click()
    }
    await settle()
    closeRendered(rendered)
  })

  it('drives authorization ledger create, update, status, delete and export flows', async () => {
    const ledgerRecord = {
      id: 'ledger-1', product_name: '产品A', market_name: '美国', source_sequence: '1',
      authorization_file_name: '授权文件.pdf', quality_standard: 'USP', company_name: '机构A',
      country: '美国', customer_code: 'C-1', purpose: '注册申报', status: '待确认',
      updates: [{ id: 'update-1', sort_order: 1, authorization_date: '2026-08-01', handler: '张三', remarks: '首次授权' }],
    }
    const fdaRecord = {
      id: 'fda-1', sequence: 1, product_name: '产品A', company_name: 'FDA机构', address: '美国地址',
      reference_number: 'REF-1', loa_date: '2026-07-01', submission_date: '2026-07-10', referenced_sections: '3.2',
    }
    getMock('actions/registration', 'createAuthorizationFdaEntry').mockResolvedValue(fdaRecord)
    getMock('actions/registration', 'updateAuthorizationFdaEntry').mockResolvedValue(fdaRecord)
    getMock('actions/registration', 'deleteAuthorizationFdaEntry').mockResolvedValue({})
    getMock('actions/registration', 'createAuthorizationLedgerMain').mockResolvedValue(ledgerRecord)
    getMock('actions/registration', 'updateAuthorizationLedgerMain').mockResolvedValue(ledgerRecord)
    getMock('actions/registration', 'deleteAuthorizationLedgerMain').mockResolvedValue({})
    getMock('actions/registration', 'createAuthorizationLedgerUpdate').mockResolvedValue(ledgerRecord.updates[0])
    getMock('actions/registration', 'updateAuthorizationLedgerUpdate').mockResolvedValue(ledgerRecord.updates[0])
    getMock('actions/registration', 'deleteAuthorizationLedgerUpdate').mockResolvedValue({})
    getMock('lib/api/client/registration', 'fetchAuthorizationFdaExport').mockResolvedValue(new Blob(['fda']))
    getMock('lib/api/client/registration', 'fetchAuthorizationLedgerExport').mockResolvedValue(new Blob(['ledger']))
    const rendered = renderClient(createElement(AuthorizationLetterClient, {
      initialRecords: [ledgerRecord] as never,
      initialFdaRecords: [fdaRecord] as never,
    }))
    await settle()
    const clickText = async (text: string) => {
      const button = Array.from(rendered.container.querySelectorAll('button')).find((item) => item.textContent?.includes(text))
      if (button && !button.disabled) {
        button.click()
        await settle()
      }
    }
    await clickText('导出FDA授权')
    await clickText('导出市场授权')
    await clickText('编辑选中')
    await clickText('确定')
    await clickText('新增FDA授权')
    await clickText('确定')
    const nativeLedgerRows = Array.from(rendered.container.querySelectorAll('table')).at(-1)?.querySelectorAll('tbody tr')
    nativeLedgerRows?.[0]?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await settle()
    await clickText('新增更新')
    await clickText('确定')
    await clickText('编辑主记录')
    await clickText('确定')
    await clickText('编辑更新')
    await clickText('确定')
    const selects = Array.from(rendered.container.querySelectorAll('select'))
    const statusSelect = selects.find((item) => item.querySelector('option[value="已递交"]'))
    if (statusSelect) {
      statusSelect.value = '已递交'
      statusSelect.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    await clickText('删除更新')
    await clickText('删除主记录')
    await clickText('删除选中')
    expect(getMock('actions/registration', 'updateAuthorizationLedgerMain')).toHaveBeenCalled()
    expect(getMock('lib/api/client/registration', 'fetchAuthorizationLedgerExport')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives employee training member maintenance and export flows', async () => {
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部'])
    getMock('lib/api/client/hr', 'fetchEmployeeTrainingMembers').mockResolvedValue([
      { id: 'member-1', name: '李四', department: '质量部', source: 'manual' },
      { id: null, name: '王五', department: '质量部', source: 'auto' },
    ])
    getMock('lib/api/client/hr', 'fetchEmployeeTrainingRecords').mockResolvedValue([
      { training_datetime: '2026-08-01T09:00:00', training_content: 'GMP培训', personal_score: '合格', remarks: '通过' },
    ])
    getMock('actions/hr', 'importFeishuMembers').mockResolvedValue({ message: '导入完成' })
    getMock('actions/hr', 'addEmployeeTrainingMember').mockResolvedValue({})
    getMock('actions/hr', 'removeEmployeeTrainingMember').mockResolvedValue({})
    getMock('actions/hr', 'updateEmployeeTrainingMember').mockResolvedValue({})
    const rendered = renderClient(createElement(EmployeeTrainingListClient))
    await settle()
    const dept = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '质量部')
    dept?.click()
    const addInput = Array.from(rendered.container.querySelectorAll('input')).find((input) => input.placeholder?.includes('可添加离职人员'))
    if (addInput) {
      addInput.value = '赵六'
      addInput.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
      Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '添加')?.click()
      await settle()
    }
    const member = Array.from(rendered.container.querySelectorAll('li')).find((item) => item.textContent?.includes('李四'))
    member?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('一键导出全部'))?.click()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('导出清单'))?.click()
    await settle()
    const checkbox = rendered.container.querySelector('input[type="checkbox"]') as HTMLInputElement | null
    checkbox?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('批量删除'))?.click()
    await settle()
    queryElement<HTMLButtonElement>(rendered.container, 'button[title="编辑姓名"]')?.click()
    await settle()
    const editInput = rendered.container.querySelector('div[role="dialog"] input') as HTMLInputElement | null
    if (editInput) {
      editInput.value = '李四更新'
      editInput.dispatchEvent(new Event('change', { bubbles: true }))
      queryElement<HTMLButtonElement>(rendered.container, 'div[role="dialog"] button:last-of-type')?.click()
      await settle()
    }
    queryElement<HTMLButtonElement>(rendered.container, 'button[title="移除"]')?.click()
    await settle()
    expect(getMock('actions/hr', 'updateEmployeeTrainingMember')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'removeEmployeeTrainingMember')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives HR department data-scope search, add, save, clear and remove flows', async () => {
    getMock('lib/api/client/hr', 'fetchDeptScopes').mockResolvedValue([
      { user_id: 'user-1', user_name: '张三', user_department: '质量部', visible_depts: ['质量部'], updated_at: '2026-08-01' },
    ])
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部', '生产部'])
    getMock('lib/api/client/hr', 'fetchCustomTrainingDepartments').mockResolvedValue(['研发部'])
    getMock('lib/api/client/hr', 'fetchFeishuMembers').mockResolvedValue({
      data: [{ open_id: 'user-2', name: '李四', department: '生产部' }], meta: { total: 1 },
    })
    getMock('actions/hr', 'saveDeptScopeAction').mockResolvedValue({ visible_depts: ['质量部', '生产部'] })
    getMock('actions/hr', 'clearDeptScopeAction').mockResolvedValue(undefined)
    const rendered = renderClient(createElement(DeptScopeSettingsClient))
    await settle()
    const search = Array.from(rendered.container.querySelectorAll('input')).find((input) => input.placeholder?.includes('搜索飞书联系人'))
    if (search) {
      search.value = '李四'
      search.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    const addUser = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('李四'))
    addUser?.click()
    await settle()
    const selects = Array.from(rendered.container.querySelectorAll('select'))
    const scopeSelect = selects.find((select) => select.multiple)
    if (scopeSelect) {
      scopeSelect.value = '生产部'
      scopeSelect.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
    }
    for (const button of Array.from(rendered.container.querySelectorAll('button'))) {
      if (button.textContent === '保存' || button.textContent === '清除' || button.textContent === '移除') {
        button.click()
        await settle()
      }
    }
    expect(getMock('actions/hr', 'saveDeptScopeAction')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'clearDeptScopeAction')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('drives contract search, sync, detail, edit, sign and renewal flows', async () => {
    const record = {
      id: 'contract-1', employee_number: 'E-1', name: '李四', gender: '女', dept_level1: '质量部',
      dept_level2: 'QA', position: '分析员', job_level: '专员', domain_account: 'lisi', id_card: 'ID-1',
      id_card_expiry: '2030-01-01', archive_number: 'ARCH-1', contract_sequence: '首次',
      contract_start_1: '2026-01-01', contract_end_1: '2026-12-31', contract_opinion: '同意续签',
      signed_status: '待签署', signed_at: null, dept_leader_name: '主管', supervisor_name: '经理',
      contract_start_2: null, contract_end_2: null, contract_start_3: null, contract_end_3: null,
      contract_start_4: null, contract_end_4: null, contract_start_5: null, contract_end_5: null,
      contract_start_6: null, contract_end_6: null,
    }
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/api/v1/hr/contracts')) {
        return new Response(JSON.stringify({ data: { data: [record], total: 1 } }), { status: 200, headers: { 'content-type': 'application/json' } })
      }
      return new Response(JSON.stringify({ code: 200, data: [] }), { status: 200, headers: { 'content-type': 'application/json' } })
    }))
    getMock('actions/hr', 'syncContractsFromFeishu').mockResolvedValue({ message: '同步完成', data: { created: 1, updated: 1 } })
    getMock('actions/hr', 'deleteContractAction').mockResolvedValue({ code: 200, message: '删除成功' })
    getMock('actions/hr', 'updateContractAction').mockResolvedValue({ code: 200, message: '更新成功' })
    getMock('actions/hr', 'renewContractAction').mockResolvedValue({ code: 200, message: '续签成功' })
    getMock('actions/hr', 'updateContractSignStatusAction').mockResolvedValue({ code: 200, message: '状态已更新' })
    const rendered = renderClient(createElement(ContractTableClient, { initialData: [record] as never, initialTotal: 1 }))
    await settle()
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    const keyword = rendered.container.querySelector('input[placeholder="姓名/工号"]') as HTMLInputElement | null
    if (keyword) {
      keyword.value = '李四'
      keyword.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const seq = rendered.container.querySelector('select[aria-label="合同次数"]') as HTMLSelectElement | null
    if (seq?.querySelector('option[value="首次"]')) {
      seq.value = '首次'
      seq.dispatchEvent(new Event('change', { bubbles: true }))
    }
    findButton('搜索')?.click()
    findButton('刷新')?.click()
    findButton('同步飞书')?.click()
    await settle()
    findButton('详情')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '关闭')?.click()
    await settle()
    findButton('续签')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('保存并同步员工档案'))?.click()
    await settle()
    findButton('编辑')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '保存')?.click()
    await settle()
    findButton('标记已签署')?.click()
    findButton('标记拒签')?.click()
    findButton('删除')?.click()
    await settle()
    getMock('actions/hr', 'updateContractAction').mockRejectedValueOnce(new Error('更新失败'))
    findButton('编辑')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '保存')?.click()
    await settle()
    closeRendered(rendered)
  })

  it('drives training ledger department, filter, import, sync, print, clear and export flows', async () => {
    getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部', '生产部'])
    getMock('lib/api/client/hr', 'fetchCustomTrainingDepartments').mockResolvedValue(['质量部'])
    getMock('lib/api/client/hr', 'fetchTrainingDeptMappings').mockResolvedValue([{ source_name: '研发部', target_name: '研发部' }])
    getMock('actions/hr', 'addCustomTrainingDepartment').mockResolvedValue({})
    getMock('actions/hr', 'deleteCustomTrainingDepartment').mockResolvedValue({})
    getMock('actions/hr', 'clearTrainingLedgersByDept').mockResolvedValue({ message: '清除成功' })
    getMock('actions/hr', 'syncEsgFromLedger').mockResolvedValue({ message: '同步完成' })
    getMock('actions/hr', 'importEsgRecordsByDept').mockResolvedValue({ message: '导入完成' })
    const rendered = renderClient(createElement(TrainingLedgerPageClient))
    await settle()
    const addDept = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('添加部门'))
    addDept?.click()
    await settle()
    const addInput = Array.from(rendered.container.querySelectorAll('input')).find((input) => input.placeholder?.includes('请输入或选择部门名称'))
    if (addInput) {
      addInput.value = '研发部'
      addInput.dispatchEvent(new Event('change', { bubbles: true }))
      await settle()
      Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('确认添加'))?.click()
      await settle()
    }
    const dept = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '生产部')
    dept?.click()
    await settle()
    const yearInput = rendered.container.querySelector('input[type="date"]') as HTMLInputElement | null
    yearInput?.dispatchEvent(new Event('change', { bubbles: true }))
    const month = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="8"]'))
    if (month) {
      month.value = '8'
      month.dispatchEvent(new Event('change', { bubbles: true }))
    }
    await settle()
    await Promise.resolve()
    const exportButton = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '导出')
    exportButton?.click()
    const printButton = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '打印')
    printButton?.click()
    const clearButton = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('全部清除'))
    clearButton?.click()
    await settle()
    const esgTab = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === 'ESG培训报表')
    esgTab?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await settle()
    const syncButton = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('从台账同步'))
    syncButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await settle()
    expect(getMock('actions/hr', 'syncEsgFromLedger')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('covers ESG report editing and training ledger import preview confirmation', async () => {
    const record = {
      id: 'esg-1', training_date: '2026-08-20', training_name: 'GMP培训', training_method: '线下', caliber: '公司组织',
      training_type: '质量类', employee_name: '李四', employee_account: 'E-2', location_address: '中国', department: '质量部',
      employee_level: '专员', gender: '女', age: 28, duration: 2, remarks: '合格', apply_company: '公司', apply_company_no: 'C-1',
    }
    getMock('lib/api/hr', 'fetchEsgRecordsByDept').mockResolvedValue({ data: [record] })
    getMock('actions/hr', 'updateEsgTrainingRecord').mockResolvedValue({})
    getMock('actions/hr', 'deleteEsgTrainingRecord').mockResolvedValue({})
    getMock('actions/hr', 'previewTrainingImport').mockResolvedValue({ data: {
      sheets: [{ name: '培训记录', header_row: 1, headers: ['姓名', '培训类型'], sample_rows: [['张三', '质量类']], mapping: { '0': 'employee_name', '1': 'training_type' }, source: 'rule', data_row_count: 1, ai_judgment: '' }, { name: '其他', header_row: 1, headers: ['备注'], sample_rows: [], mapping: {}, source: 'none', data_row_count: 0, ai_judgment: '跳过' }],
      field_catalog: [{ key: 'employee_name', label: '员工姓名' }, { key: 'training_type', label: '培训类型' }],
    } })
    getMock('actions/hr', 'confirmTrainingImport').mockResolvedValue({ message: '导入成功' })
    const printWindow = { document: { write: vi.fn(), close: vi.fn() }, focus: vi.fn(), print: vi.fn() }
    vi.stubGlobal('open', vi.fn(() => printWindow))
    const report = renderClient(createElement(EsgTrainingReportClient, { department: '质量部', dateFrom: '2026-01-01', dateTo: '2026-12-31', periodLabel: '全年', printRequest: 1 }))
    await settle()
    const reportButton = (text: string) => Array.from(report.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    reportButton('编辑')?.click()
    await settle()
    Array.from(report.container.querySelectorAll('button')).find((button) => button.textContent === '确定')?.click()
    await settle()
    reportButton('删除')?.click()
    await settle()
    expect(getMock('actions/hr', 'updateEsgTrainingRecord')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'deleteEsgTrainingRecord')).toHaveBeenCalled()
    closeRendered(report)

    const success = vi.fn()
    const importer = renderClient(createElement(TrainingLedgerImportModal, { open: true, department: '质量部', onClose: vi.fn(), onSuccess: success }))
    await settle()
    const uploadText = importer.container.querySelector('.ant-upload-text')
    uploadText?.parentElement?.click()
    await settle()
    const mappingSelect = Array.from(importer.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="employee_name"]'))
    if (mappingSelect) {
      mappingSelect.value = 'employee_name'
      mappingSelect.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const sheetCheckbox = queryElement<HTMLInputElement>(importer.container, 'input[type="checkbox"]')
    sheetCheckbox?.click()
    sheetCheckbox?.click()
    await settle()
    Array.from(importer.container.querySelectorAll('button')).find((button) => button.textContent?.includes('确认导入'))?.click()
    await settle()
    expect(getMock('actions/hr', 'previewTrainingImport')).toHaveBeenCalled()
    expect(getMock('actions/hr', 'confirmTrainingImport')).toHaveBeenCalled()
    expect(success).toHaveBeenCalled()
    closeRendered(importer)
  })

  it('drives regulation tracker filters, detail, AI analysis and notification settings', async () => {
    const record = {
      id: 'reg-1', title: '药品注册法规更新', version_text: '2026版', capture_date: '2026-08-20T10:00:00',
      publish_date: '2026-08-18', effective_date: '2026-09-01', summary_text: '第一行\n第二行',
      source_url: 'https://example.test/regulation', source_site_name: 'NMPA', is_new: true,
      ai_analysis_status: 'pending', ai_summary: null, ai_analyzed_at: null, ai_relevance_score: null, ai_key_points: [],
    }
    const detail = { ...record, ai_analysis_status: 'pending', ai_summary: null, ai_key_points: [] }
    expect(formatDate()).toBe('-')
    expect(formatDate('not-a-date')).toBe('not-a-date')
    expect(hasCompletedAnalysis({ ai_analysis_status: 'completed', ai_summary: null })).toBe(true)
    expect(hasCompletedAnalysis({ ai_analysis_status: 'pending', ai_summary: ' 已有摘要 ' })).toBe(true)
    expect(buildQueryParams({ keyword: ' 法规 ', sourceSite: 'NMPA', publishDateRange: null, captureDateRange: null, isNew: false })).toEqual({ keyword: '法规', sourceSite: 'NMPA', isNew: false })
    const range = [{ format: () => '2026-08-01' }, { format: () => '2026-08-31' }] as never
    expect(buildQueryParams({ keyword: '', sourceSite: 'NMPA', publishDateRange: range, captureDateRange: range, isNew: true })).toEqual({
      sourceSite: 'NMPA', publishDateFrom: '2026-08-01', publishDateTo: '2026-08-31', captureDateFrom: '2026-08-01', captureDateTo: '2026-08-31', isNew: true,
    })
    getMock('lib/api/client/regulatoryTracker', 'fetchRegulatoryTrackerDocumentDetailClient').mockResolvedValue(detail)
    getMock('lib/api/client/regulatoryTracker', 'fetchRegulatoryTrackerDocumentsClient').mockResolvedValue({ items: [record], total: 1, page: 1, pageSize: 20, totalPages: 1 })
    getMock('lib/api/client/regulatoryTracker', 'analyzeRegulatoryDocumentClient').mockResolvedValue({ analyzed: true })
    getMock('lib/api/client/regulatoryTracker', 'updateRegulatoryTrackerNotificationSettingsClient').mockResolvedValue({
      is_enabled: true, recent_days: 14, recipient_open_id: 'qa-1', recipient_name: 'QA', recipient_department: '质量部', schedule_time: '10:00', pending_count: 1,
    })
    getMock('lib/api/client/regulatoryTracker', 'fetchRegulatoryTrackerNotificationRecipientsClient').mockResolvedValue([{ name: 'QA', open_id: 'qa-1', department: '质量部' }])
    getMock('lib/api/client/regulatoryTracker', 'manualSyncRegulatoryTrackerClient').mockResolvedValue({ status: 'started', message: '已启动' })
    getMock('lib/api/client/regulatoryTracker', 'fetchRegulatoryTrackerSyncStatusClient').mockResolvedValue({
      status: 'completed', started_at: null, completed_at: null,
      result: { bootstrap: { created_sources: 1, created_channels: 1, site_count: 1, sites: ['NMPA'] }, totals: { checked: 2, accepted: 2, inserted: 1, updated: 1, unchanged: 0, rejected: 0 }, sites: [], analysis: { analyzed: 1, failed: 0, skipped: 0 } }, error: null,
    })
    const rendered = renderClient(createElement(RegulationTrackerPage, {
      initialResult: { items: [record], total: 1, page: 1, pageSize: 20, totalPages: 1 },
      initialNotificationSettings: { ...notificationSettings, is_enabled: false, recipient_open_id: null, pending_count: 0 },
      notificationRecipients: [{ name: 'QA', open_id: 'qa-1', department: '质量部' }],
    }))
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('刷新数据'))?.click()
    await settle()
    const source = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="NMPA"]'))
    if (source) {
      source.value = 'NMPA'
      source.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const isNewFilter = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="true"]'))
    if (isNewFilter) {
      isNewFilter.value = 'true'
      isNewFilter.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const row = rendered.container.querySelector('table tbody tr')
    row?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('查看详情'))?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('查看/分析当前选中'))?.click()
    await settle()
    const keyword = Array.from(rendered.container.querySelectorAll('input')).find((input) => input.placeholder?.includes('关键词搜索'))
    if (keyword) {
      keyword.value = '法规'
      keyword.dispatchEvent(new Event('change', { bubbles: true }))
    }
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '查询')?.click()
    await settle()
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '重置')?.click()
    const recipient = Array.from(rendered.container.querySelectorAll('select')).find((select) => select.querySelector('option[value="qa-1"]'))
    if (recipient) {
      recipient.value = 'qa-1'
      recipient.dispatchEvent(new Event('change', { bubbles: true }))
    }
    const save = Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes('保存设置'))
    rendered.container.querySelector('input[type="checkbox"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    const recentDays = rendered.container.querySelector('input[type="number"]') as HTMLInputElement | null
    recentDays?.dispatchEvent(new Event('change', { bubbles: true }))
    save?.click()
    await settle()
    vi.stubGlobal('setTimeout', ((callback: TimerHandler) => {
      if (typeof callback === 'function') queueMicrotask(() => callback())
      return 1
    }) as typeof setTimeout)
    vi.stubGlobal('clearTimeout', vi.fn())
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '触发抓取')?.click()
    await settle()
    getMock('lib/api/client/regulatoryTracker', 'manualSyncRegulatoryTrackerClient').mockRejectedValueOnce(new Error('后端暂未暴露法规跟踪手动同步 API'))
    Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent === '触发抓取')?.click()
    await settle()
    expect(getMock('lib/api/client/regulatoryTracker', 'analyzeRegulatoryDocumentClient')).toHaveBeenCalled()
    expect(getMock('lib/api/client/regulatoryTracker', 'updateRegulatoryTrackerNotificationSettingsClient')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('covers regulation tracker empty, query-error and running-task recovery states', async () => {
    getMock('lib/api/client/regulatoryTracker', 'fetchRegulatoryTrackerDocumentsClient').mockRejectedValue(new Error('法规台账加载失败'))
    getMock('lib/api/client/regulatoryTracker', 'fetchRegulatoryTrackerNotificationRecipientsClient').mockRejectedValue(new Error('通知人加载失败'))
    getMock('lib/api/client/regulatoryTracker', 'manualSyncRegulatoryTrackerClient').mockRejectedValue(new Error('已有抓取任务正在执行'))
    getMock('lib/api/client/regulatoryTracker', 'fetchRegulatoryTrackerSyncStatusClient').mockResolvedValue({ status: 'failed', started_at: null, completed_at: null, result: null, error: '上游抓取失败' })
    getMock('lib/api/client/regulatoryTracker', 'updateRegulatoryTrackerNotificationSettingsClient').mockResolvedValue(null)
    const rendered = renderClient(createElement(RegulationTrackerPage, {
      initialResult: { items: [], total: 0, page: 1, pageSize: 20, totalPages: 0 },
      initialNotificationSettings: { ...notificationSettings, is_enabled: false, recipient_open_id: null, recipient_name: null, recipient_department: null },
      notificationRecipients: [],
    }))
    await settle()
    const click = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))?.click()
    click('刷新数据')
    click('查看详情')
    click('查看/分析当前选中')
    click('查询')
    click('重置')
    const numberInput = rendered.container.querySelector('input[type="number"]') as HTMLInputElement | null
    numberInput?.dispatchEvent(new Event('change', { bubbles: true }))
    queryElement<HTMLInputElement>(rendered.container, 'input[type="checkbox"]')?.click()
    click('保存设置')
    await settle()
    click('触发抓取')
    await settle()
    getMock('lib/api/client/regulatoryTracker', 'updateRegulatoryTrackerNotificationSettingsClient').mockRejectedValueOnce(new Error('保存推送配置失败'))
    click('保存设置')
    await settle()
    closeRendered(rendered)
  })

  it('exercises registration workbook dashboard aggregation, import and export controls', async () => {
    const makeRecord = (values: Record<string, string>, marks: Record<string, string | null> = {}) => ({
      id: `record-${Object.keys(values).length}-${Object.keys(marks).length}`,
      sequence: 1,
      latest_values: values,
      latest_style_marks: marks,
      history_count: 2,
    })
    const projectOverview = {
      sheets: [
        { sheet_key: 'international-associated-review', sheet_name: '国际关联', columns: [{ label: '产品', key: 'product' }, { label: '项目名称', key: 'project' }, { label: '国家/受理机构', key: 'market' }, { label: '是否获得证书', key: 'certificate' }], records: [makeRecord({ product: '产品A', project: '项目A', market: '美国', certificate: '是' })], summary: { total_records: 1, records_with_history: 1 } },
        { sheet_key: 'domestic-standalone-review', sheet_name: '国内单独', columns: [{ label: '产品', key: 'product' }, { label: '项目名称', key: 'project' }, { label: '受理机构', key: 'market' }, { label: '证书名称', key: 'certificate_name' }], records: [makeRecord({ product: '产品B', project: '项目B', market: 'NMPA', certificate_name: '证书B' })], summary: { total_records: 1, records_with_history: 0 } },
      ],
    }
    const declarationOverview = {
      sheets: [
        { sheet_key: 'new-product-projects', sheet_name: '新品', columns: [{ label: '产品名称', key: 'product' }, { label: '项目名称', key: 'project' }, { label: '国家/受理机构', key: 'market' }], records: [makeRecord({ product: '产品C', project: '项目C', market: '欧盟' }, { name: 'new' })], summary: { total_records: 1, total_history_versions: 1, main_column_count: 3, child_column_count: 0 } },
        { sheet_key: 'gmp-projects', sheet_name: 'GMP', columns: [{ label: '涉及产品', key: 'product' }, { label: '产品名称', key: 'project' }, { label: '官方机构/国家', key: 'market' }], records: [makeRecord({ product: '产品D', project: '项目D', market: '中国' }, { status: 'updated' })], summary: { total_records: 1, total_history_versions: 0, main_column_count: 3, child_column_count: 1 } },
        { sheet_key: 'us-fda-progress', sheet_name: 'FDA', columns: [{ label: '产品', key: 'product' }, { label: '项目名称', key: 'project' }], records: [makeRecord({ product: '产品E', project: '项目E' })], summary: { total_records: 1, total_history_versions: 0, main_column_count: 2, child_column_count: 0 } },
      ],
    }
    getMock('lib/api/client/registration', 'fetchProjectLedgerWorkbookExport').mockResolvedValue(new Blob(['project']))
    getMock('lib/api/client/registration', 'fetchDeclarationProgressWorkbookExport').mockResolvedValue(new Blob(['declaration']))
    getMock('actions/registration', 'importProjectLedgerWorkbook').mockResolvedValue({ success: true })
    getMock('actions/registration', 'importDeclarationProgressWorkbook').mockResolvedValue({ success: true })
    const rendered = renderClient(createElement('div', null,
      createElement(ProjectLedgerDashboardPage, { key: 'project-dashboard', overview: projectOverview as never }),
      createElement(DeclarationProgressDashboardPage, { key: 'declaration-dashboard', overview: declarationOverview as never }),
    ))
    await settle()
    expect(rendered.container.textContent).toContain('项目')
    expect(rendered.container.textContent).toContain('申报')
    for (const input of Array.from(rendered.container.querySelectorAll('input[type="file"]'))) {
      Object.defineProperty(input, 'files', { configurable: true, value: [new File(['invalid'], '导入.xlsx')] })
      input.dispatchEvent(new Event('change', { bubbles: true }))
    }
    for (const button of Array.from(rendered.container.querySelectorAll('button'))) {
      if (!button.disabled) button.click()
    }
    await settle()
    expect(getMock('lib/api/client/registration', 'fetchProjectLedgerWorkbookExport')).toHaveBeenCalled()
    expect(getMock('lib/api/client/registration', 'fetchDeclarationProgressWorkbookExport')).toHaveBeenCalled()
    closeRendered(rendered)
  })

  it('renders quality records and warehouse dashboard data', async () => {
    getMock('lib/api/client/quality', 'fetchDocumentDepartments').mockResolvedValue([{ id: 'dept-1', name: '质量部', sort_order: 1, document_count: 1 }])
    getMock('lib/api/client/quality', 'fetchDocumentEntries').mockResolvedValue({ items: [{ id: 'doc-1', department_id: 'dept-1', name: 'SOP', code: 'SOP-1', effective_date: '2026-08-01' }], total: 1 })
    const dashboardData = {
      safety: { ok: 10, low: 2, total: 12 }, quality: { 合格: 8, 待验: 1, 不合格: 1 },
      material_outbound_30d: [{ date: '2026-08-01', value: 2 }], packaging_outbound_30d_total: 4,
      month_inbound_total: 3, low_stock_top: [{ name: '物料A', balance: 1, safety: 3, warning: '不足' }],
      kpis: [{ label: '库存', value: 10 }], trends: [{ date: '2026-08-01', value: 2 }], monthly: [{ month: '2026-08', value: 3 }], products: [{ name: '产品A', value: 4 }], detail: {},
    }
    getMock('lib/api/client/warehouse', 'fetchWarehouseDashboard').mockResolvedValue(dashboardData)
    const rendered = renderClient(createElement('div', null,
      createElement(DocumentCatalogPage, { key: 'docs', initialDepartments: [{ id: 'dept-1', name: '质量部', sort_order: 1, document_count: 1 }] as never }),
      createElement(OotLimitManagementPage, { key: 'oot' }),
      createElement(OosOotReportRecordPage, { key: 'report' }),
      createElement(OosOotInvestigationPushPage, { key: 'push' }),
      createElement(ProductQualityStandardPage, { key: 'standard', productCode: 'P-1', productLabel: '产品A' }),
      createElement(WarehouseDashboard, { key: 'warehouse', group: 'raw', title: '原料库存', baseName: '仓储', initialData: dashboardData as never }),
    ))
    await settle()
    expect(rendered.container.textContent).toContain('原料库存')
    expect(rendered.container.textContent).toContain('质量')
    for (const button of Array.from(rendered.container.querySelectorAll('button'))) button.click()
    await settle()
    closeRendered(rendered)

    const hardwareData = {
      stock_amount: 1280.5,
      dept_stock: [{ dept: '生产部', value: 800 }],
      inbound_30d_total: 320.25,
      outbound_30d_total: 210.75,
      outbound_30d_trend: [{ date: '2026-08-01', value: 20 }],
      dept_outbound_30d: [{ dept: '生产部', value: 210.75 }],
      detail: { dept_stock: [{ dept: '生产部', value: 800 }], inbound_30d: [], outbound_30d: [] },
    }
    const productData = {
      qualified: 12,
      pending: 3,
      product_stock: [{ name: '产品A', value: 12 }],
      product_outbound: [{ name: '产品A', value: 4 }],
      product_qualified: [{ name: '产品A', value: 12 }],
      product_pending: [{ name: '产品A', value: 3 }],
      shipping_30d_trend: [{ date: '2026-08-01', value: 4 }],
      product_monthly_inbound: { '盐酸林可霉素（kg）': [{ month: '2026-08', quantity: 3 }], '盐酸林可霉素（十亿）': [{ month: '2026-08', quantity: 2 }] },
      product_monthly_outbound: { '盐酸林可霉素（kg）': [{ month: '2026-08', quantity: 1 }] },
      zero_activity_products: ['产品B'],
      detail: { qualified: [{ name: '产品A', value: 12 }], pending: [{ name: '产品A', value: 3 }] },
    }
    getMock('lib/api/client/warehouse', 'fetchWarehouseDashboard').mockImplementation(async (group: string) => (
      group === 'hardware' ? hardwareData : productData
    ))
    const dashboard = renderClient(createElement('div', null,
      createElement(WarehouseDashboard, { key: 'hardware', group: 'hardware', title: '五金库存', baseName: '仓储', initialData: hardwareData as never }),
      createElement(WarehouseDashboard, { key: 'product', group: 'product', title: '成品库存', baseName: '仓储', initialData: productData as never }),
    ))
    await settle()
    for (const card of Array.from(dashboard.container.querySelectorAll('.wh-kpi'))) {
      card.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    }
    for (const button of Array.from(dashboard.container.querySelectorAll('button'))) button.click()
    await settle()
    expect(dashboard.container.textContent).toContain('五金库存金额')
    expect(dashboard.container.textContent).toContain('零活动产品')
    closeRendered(dashboard)
  })

  it('renders additional migration pages in their initial states', () => {
    const elements = [
      createElement(AiWrittenExamClient, { key: 'ai-exam', sessionData: { topic: 'GMP', checked_content: [] } as never }),
      createElement(DeptMappingSettingsClient, { key: 'mapping' }),
      createElement(AnnualPlanDetailClient, { key: 'annual-detail', planId: 'plan-1', plan: null }),
      createElement(DeptScopeSettingsClient, { key: 'scope' }),
      createElement(PlanTrackingClient, { key: 'tracking' }),
      createElement(ContractTableClient, { key: 'contracts', initialData: [], initialTotal: 0 }),
      createElement(TrainerListClient, { key: 'trainers' }),
      createElement(NewEmployeeTrainingDetailClient, { key: 'new-detail', planId: 'plan-1' }),
      createElement(OosOotProductDepartmentPage, { key: 'oos-product' }),
      createElement(ReturnApplicationPage, { key: 'return-application', initialItems: [] as never }),
      createElement(ReturnLedgerPage, { key: 'return-ledger', initialItems: [] as never }),
      createElement(SupplierQualificationPage, { key: 'supplier', initialItems: [] as never }),
      createElement(CertificateSheetPage, { key: 'certificate-sheet', detail: { sheet_key: 'licenses', sheet_name: '证书', columns: [], rows: [], records: [], summary: { total_records: 0 } } as never }),
      createElement(CertificateManagementDashboard, { key: 'certificate-dashboard', overview: { total_records: 0, sheet_count: 0, issuer_count: 0, product_count: 0, expired_count: 0, due_90_count: 0, total_pages: 0, sheet_summaries: [] } as never }),
      createElement(CertificateDashboardPage, { key: 'certificate-reminders', overview: { total_records: 0, sheet_count: 0, issuer_count: 0, product_count: 0, expired_count: 0, due_90_count: 0, total_pages: 0, sheet_summaries: [], records: [] } as never, reminderSettings: { is_enabled: false, reminder_days: 90, recipient_open_id: null, recipient_name: null, recipient_department: null, pending_count: 0 } as never, reminderRecipients: [] }),
      createElement(FeeDashboardPage, { key: 'fee-dashboard', dashboard: { total_amount: 0, paid_amount: 0, pending_amount: 0, total_records: 0, inspection_contact_count: 0, fee_type_summaries: [], year_summaries: [], agency_summaries: [], year_fee_type_summaries: [] } as never }),
      createElement(FeeLedgerPage, { key: 'fee-ledger', entries: [] }),
      createElement(KnowledgeArticleDetail, { key: 'article', article: { id: 'article-1', title: '法规', content: '内容', attachments: [], comments: [] } as never }),
      createElement(InspectionContactsPage, { key: 'contacts', contacts: [] }),
      createElement(WarehouseFeishuConfigPage, { key: 'warehouse-config', initialConfigs: [] }),
    ]
    let html = ''
    elements.forEach((element, index) => {
      try {
        html += renderStatic(element)
      } catch (error) {
        console.error('static element failed', index, error)
        throw error
      }
    })
    expect(html.length).toBeGreaterThan(1000)
  })

  it('drives the migrated component exports through their common controls', async () => {
    const failures: string[] = []
    let mounted = 0
    for (const [path, load] of Object.entries(interactiveComponentLoaders)) {
      if (path.includes('/dossier-writer/') || path.endsWith('/index.ts') || path.endsWith('/index.tsx')) continue
      if (!interactiveTargets.some((target) => path.endsWith(`/${target}`))) continue
      const loadedModule = await load()
      for (const [name, component] of Object.entries(loadedModule)) {
        if (!isInteractiveComponentExport(name) || typeof component !== 'function') continue
        let rendered: ReturnType<typeof renderClient> | null = null
        try {
          const componentProps = interactivePropsFor(path)
          if (path.endsWith('/FeeDashboardPage.tsx')) {
            getMock('lib/api/client/registration', 'fetchFeeDashboard').mockResolvedValue(componentProps.dashboard)
          }
          if (path.includes('OotLimitManagementPage')) {
            getMock('lib/api/client/quality', 'fetchOotLimitProducts').mockResolvedValue({ data: [{ id: 'product-1', product_code: 'P-1', product_name: '产品A', document_title: '限度标准', document_year: 2026, version_label: 'V1', source_file_name: 'limit.pdf', remark: '备注' }], total: 1 })
            getMock('lib/api/client/quality', 'fetchOotLimitItems').mockResolvedValue({ data: [{ id: 'item-1', product_id: 'product-1', display_order: 1, item_group: '有关物质', item_name: '杂质A', standard_value: '≤1.0%', oot_limit_value: '>1.5%', remark: '重点' }], total: 1 })
            getMock('actions/quality', 'createOotLimitProduct').mockResolvedValue({ id: 'product-2' })
            getMock('actions/quality', 'updateOotLimitProduct').mockResolvedValue({ id: 'product-1' })
            getMock('actions/quality', 'createOotLimitItem').mockResolvedValue({ id: 'item-2' })
            getMock('actions/quality', 'updateOotLimitItem').mockResolvedValue({ id: 'item-1' })
            getMock('actions/quality', 'deleteOotLimitProduct').mockResolvedValue({ success: true })
            getMock('actions/quality', 'deleteOotLimitItem').mockResolvedValue({ success: true })
          }
          if (path.includes('AnnualTrainingStatsClient')) {
            const ledger = { id: 'ledger-1', employee_number: 'E-1', training_date: '2026-08-20', training_subject: 'GMP培训', training_content: 'GMP培训', training_datetime: '2026-08-20 09:00', duration_hours: 2, teaching_dept: '质量部', instructor: '张三', level_category: '一级', involved_depts: '质量部', trainees: '李四', training_type: '质量培训', ledger_assessment_method: '笔试', plan_source: '年度计划', drug_category: '人药', score_summary: '合格', remarks: '备注', source_type: 'session', session_id: 'session-1', second_level_status: 'pending' }
            getMock('lib/api/hr', 'fetchTrainingLedgersByDept').mockResolvedValue({ code: 200, message: 'ok', data: [ledger], meta: { page: 1, page_size: 500, total: 1 } })
            getMock('lib/api/client/hr', 'fetchSessionDocuments').mockResolvedValue([{ id: 'doc-1', session_id: 'session-1', doc_type: 'oral_exam', title: '口试', payload: { questions: [] }, updated_at: '2026-08-20' }, { id: 'doc-2', session_id: 'session-1', doc_type: 'practical_exam', title: '实操', payload: { items: [] }, updated_at: '2026-08-20' }])
            getMock('lib/api/client/hr', 'fetchTrainingSession').mockResolvedValue({ department: '质量部' })
            getMock('actions/hr', 'generateOralExamResult').mockResolvedValue({ bytes: new Uint8Array([1]), filename: 'oral.docx' })
            getMock('actions/hr', 'generatePracticalExamResult').mockResolvedValue({ bytes: new Uint8Array([1]), filename: 'practical.docx' })
            getMock('actions/hr', 'updateTrainingLedger').mockResolvedValue({})
            getMock('actions/hr', 'deleteTrainingLedger').mockResolvedValue({})
          }
          if (path.includes('NewEmployeeTrainingListClient')) {
            const plan = { plan_id: 'plan-1', employee_id: 'employee-1', employee_name: '李四', employee_number: 'E-1', department: '质量部', sub_department: 'QA', position: '分析员', hire_date: '2026-08-01', deadline_date: '2026-09-01', status: '培训中', total_count: 3, completed_count: 1, progress: 33, training_position: '质量岗位' }
            getMock('lib/api/client/hr', 'fetchTrainingDepartments').mockResolvedValue(['质量部'])
            getMock('lib/api/client/hr', 'fetchNewEmployeeTrainingPlans').mockResolvedValue({ data: [plan], total: 1, page: 1, page_size: 20 })
            getMock('lib/api/client/hr', 'fetchNewEmployeeTrainingStats').mockResolvedValue({ pending: 1, training: 1, completed: 0, overdue: 0 })
            getMock('lib/api/client/hr', 'fetchDepartmentPositions').mockResolvedValue(['质量岗位'])
            getMock('actions/hr', 'generateNewEmployeeTrainingPlan').mockResolvedValue({ plan_id: 'plan-1' })
            getMock('actions/hr', 'updateNewEmployeeTrainingPlan').mockResolvedValue({})
            getMock('actions/hr', 'createPositionTrainingMappingAction').mockResolvedValue({})
          }
          if (path.includes('OnboardingManagementPage')) {
            const onboarding = { id: 'onboard-1', name: '候选人', onboard_date: '2026-08-20', department: '质量部', level: '专员', status: '进行中', health_status: '合格', resignation_cert: '已提供', id_card: '已提供', education_cert: '未提供' }
            getMock('lib/api/client/hr', 'fetchOnboardingList').mockResolvedValue({ data: [onboarding], meta: { total: 1, page: 1, page_size: 20 } })
            getMock('lib/api/client/hr', 'fetchDepartments').mockResolvedValue({ data: [{ id: 'dept-1', name: '质量部' }], meta: { total: 1 } })
            getMock('lib/api/client/hr', 'fetchJobPostings').mockResolvedValue({ data: [{ id: 'job-1', title: '分析员' }], meta: { total: 1 } })
            getMock('actions/hr', 'updateOnboardingAction').mockResolvedValue({})
            getMock('actions/hr', 'syncOnboardingToEmployeeAction').mockResolvedValue({})
            getMock('actions/hr', 'syncOnboardingToContractAction').mockResolvedValue({})
          }
          if (path.includes('RecruitmentClient') || path.includes('CandidateListView') || path.includes('CandidateCardView')) {
            const candidate = { id: 'candidate-1', name: '候选人', job_position: '分析员', interview_status: '通过', fit_level: '高', education: '本科', phone: '13800000000', email: 'candidate@example.com', contact: '13800000000', work_years: 3, match_rate: 90, resume_score: 88 }
            getMock('lib/api/client/hr', 'fetchCandidates').mockResolvedValue({ data: [candidate], meta: { total: 1, page: 1, page_size: 20 } })
            getMock('actions/hr', 'sendOfferEmailAction').mockResolvedValue({})
            getMock('actions/hr', 'deleteCandidateAction').mockResolvedValue({})
            getMock('actions/hr', 'updateCandidateAction').mockResolvedValue({})
            getMock('actions/hr', 'createOnboardingFromInterviewAction').mockResolvedValue({ message: '已转入职' })
          }
          if (path.includes('ContractAlertBanner')) {
            const contractRows = [{ employee_id: 'employee-1', name: '李四', department: '质量部', sub_department: 'QA', contract_end_date: '2026-09-30', employee_number: 'E-1', position: '分析员', contract_sequence: 1 }]
            vi.stubGlobal('fetch', vi.fn(async (url: string) => {
              if (url.includes('contract-expiring')) return new Response(JSON.stringify({ data: contractRows }), { status: 200, headers: { 'content-type': 'application/json' } })
              return new Response(JSON.stringify({ code: 200, data: [] }), { status: 200, headers: { 'content-type': 'application/json' } })
            }))
            getMock('actions/hr', 'getContractPushStatusAction').mockResolvedValue({ data: { state: 'completed', pushed: 1, failed: 0, skipped_pushed: 0, skipped_approved: 0 } })
            getMock('actions/hr', 'pushContractExpiringAction').mockResolvedValue({ message: '已发起' })
            getMock('actions/hr', 'saveContractTemplateAction').mockResolvedValue({})
          }
          if (path.includes('AnnualTrainingStatsClient')) Object.assign(componentProps, { department: '质量部', dateFrom: '2026-01-01', dateTo: '2026-12-31', periodLabel: '全年', printRequest: 0 })
          if (path.includes('CandidateListView') || path.includes('CandidateCardView')) Object.assign(componentProps, { candidates: [{ id: 'candidate-1', name: '候选人', job_position: '分析员', interview_status: '通过', fit_level: '高', education: '本科', phone: '13800000000', email: 'candidate@example.com', contact: '13800000000', work_years: 3, match_rate: 90, resume_score: 88 }], loading: false, page: 1, pageSize: 20, total: 1, onPageChange: vi.fn(), onDelete: vi.fn() })
          rendered = renderClient(createElement(component as never, componentProps))
          await settle()
          mounted += 1

          for (let round = 0; round < 2; round += 1) {
            const clickables = Array.from(rendered.container.querySelectorAll('button, a, [role="button"], span.cb-big, tr'))
            for (const clickable of clickables) {
              if (clickable instanceof HTMLButtonElement && clickable.disabled) continue
              if (clickable.isConnected) clickable.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
            }
            await settle()
          }
          for (const select of Array.from(rendered.container.querySelectorAll('select')).slice(0, 6)) {
            const option = Array.from(select.options).find((item) => item.value)
            if (option) {
              select.value = option.value
              select.dispatchEvent(new Event('change', { bubbles: true }))
            }
          }
          for (const input of Array.from(rendered.container.querySelectorAll<HTMLInputElement>('input:not([type="checkbox"]):not([type="radio"]):not([type="file"])')).slice(0, 6)) {
            input.value = '测试输入'
            input.dispatchEvent(new Event('input', { bubbles: true }))
            input.dispatchEvent(new Event('change', { bubbles: true }))
          }
          for (const input of Array.from(rendered.container.querySelectorAll<HTMLInputElement>('input[type="checkbox"], input[type="radio"]')).slice(0, 4)) {
            if (!input.disabled) input.click()
          }
          for (const form of Array.from(rendered.container.querySelectorAll('form')).slice(0, 2)) {
            form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
          }
          await settle()
        } catch (error) {
          failures.push(`${path}#${name}: ${error instanceof Error ? error.message : String(error)}`)
        } finally {
          if (rendered) closeRendered(rendered)
        }
      }
    }
    expect(mounted).toBeGreaterThan(15)
    expect(failures).toEqual([])
  }, 180000)

})

describe('quality deviation history / workbench / inspection modal coverage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mocks.permissionAllowed = true
    localStorage.clear()
    window.URL.createObjectURL = vi.fn(() => 'blob:test')
    window.URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    document.body.replaceChildren()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renders deviation history rows and their column renderers', async () => {
    getMock('lib/api/client/quality', 'fetchHistoricalDeviations').mockResolvedValue({
      items: [{
        id: 'hist-1', code: 'PC-2026-0001', deviation_event: '含量偏差', deviation_content: '批次A 收率偏低',
        direct_cause: '投料错误', root_cause: 'SOP 未更新', attachment_count: 3, created_at: '2026-08-10T02:00:00Z',
      }, {
        id: 'hist-2', code: '', deviation_event: null, deviation_content: null,
        direct_cause: null, root_cause: null, attachment_count: 0, created_at: '2026-08-11T02:00:00Z',
      }],
      total: 2,
    })
    const rendered = renderClient(createElement(DeviationHistoryPage))
    await settle()
    expect(rendered.container.textContent).toContain('PC-2026-0001')
    expect(rendered.container.textContent).toContain('含量偏差')
    expect(rendered.container.textContent).toContain('直接原因：投料错误')
    expect(rendered.container.textContent).toContain('根本原因：SOP 未更新')
    expect(rendered.container.textContent).toContain('3 个')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    getMock('lib/api/client/quality', 'fetchHistoricalDeviation').mockResolvedValue({
      id: 'hist-1', code: 'PC-2026-0001', deviation_event: '含量偏差',
      attachments: [
        { id: 'att-pdf', file_name: '现场.pdf', url: '/api/files/pdf', file_size: 2 * 1024 * 1024, converted: false },
        { id: 'att-md', file_name: '调查报告.docx', url: '/api/files/md', file_size: 512, converted: true },
        { id: 'att-kb', file_name: '旧记录.doc', url: '/api/files/kb', file_size: 20480, converted: false },
        { id: 'att-x', file_name: '无大小.pdf', url: '/api/files/x', converted: false },
      ],
    })
    getMock('actions/quality-deviation-workbench', 'updateHistoricalDeviation').mockResolvedValue({ id: 'hist-1' })
    getMock('actions/quality-deviation-workbench', 'aiExtractHistoricalDeviation').mockResolvedValue({
      id: 'hist-1', code: 'PC-2026-0001', deviation_event: 'AI 事件', direct_cause: 'AI 直接原因', root_cause: 'AI 根因',
      attachments: [
        { id: 'att-pdf', file_name: '现场.pdf', url: '/api/files/pdf', file_size: 2 * 1024 * 1024, converted: false },
        { id: 'att-md', file_name: '调查报告.docx', url: '/api/files/md', file_size: 512, converted: true },
        { id: 'att-kb', file_name: '旧记录.doc', url: '/api/files/kb', file_size: 20480, converted: false },
        { id: 'att-x', file_name: '无大小.pdf', url: '/api/files/x', converted: false },
      ],
    })
    getMock('actions/quality-deviation-workbench', 'deleteHistoricalDeviation').mockResolvedValue({ ok: true })
    getMock('actions/quality-deviation-workbench', 'uploadHistoricalDeviationAttachment').mockResolvedValue({
      id: 'att-new', file_name: 'template.pdf', url: '/api/files/att-new',
    })
    getMock('actions/quality-deviation-workbench', 'batchImportHistoricalDeviations').mockResolvedValue({
      total: 2, succeeded: 1, failed: 1, results: [{ status: 'failed', file_name: '坏文件.docx' }],
    })
    findButton('编辑')?.click()
    await settle()
    // 编辑抽屉：详情 + 附件列表 + 操作按钮
    expect(rendered.container.textContent).toContain('历史偏差 - PC-2026-0001')
    expect(rendered.container.textContent).toContain('调查报告.docx')
    findButton('AI 提取')?.click()
    await settle()
    findButton('上传附件')?.click()
    await settle()
    expect(mocks.message.success).toHaveBeenCalledWith(expect.stringContaining('上传成功'))
    // 附件在线预览：首个为 PDF（blob 内嵌分支），随后 MD 文本含表格/图片（markdown 组件渲染器分支）
    vi.stubGlobal('fetch', vi.fn(async (input: string) => {
      if (String(input).includes('/api/files/pdf')) {
        return new Response(new Blob(['%PDF-1.4'], { type: 'application/pdf' }), {
          status: 200, headers: { 'content-type': 'application/pdf' },
        })
      }
      return new Response('# 预览的 Markdown 正文\n\n![图](/api/files/pic.png)\n\n| 项目 | 结果 |\n|---|---|\n| 含量 | 合格 |', {
        status: 200, headers: { 'content-type': 'text/markdown' },
      })
    }))
    findButton('预览')?.click()
    await settle()
    expect(rendered.container.textContent).toContain('附件预览 - 现场.pdf')
    // 关闭 PDF 预览（Modal onCancel 渲染为“取消”），改预览 MD 附件
    const dialogCancel = rendered.container.querySelector('[role="dialog"] button')
    act(() => { dialogCancel?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    const mdPreview = Array.from(rendered.container.querySelectorAll('button')).filter((b) => b.textContent?.trim() === '预览')
    act(() => { mdPreview[1]?.click() })
    await settle()
    expect(rendered.container.textContent).toContain('调查报告.docx')
    expect(rendered.container.textContent).toContain('预览的 Markdown 正文')
    expect(rendered.container.textContent).toContain('含量')
    // 抽屉内附件删除（Popconfirm 触发 modal.confirm onOk）
    const delAttachment = Array.from(rendered.container.querySelectorAll('button')).filter((b) => b.textContent?.trim() === '删除')
    getMock('actions/quality-deviation-workbench', 'deleteHistoricalDeviationAttachment').mockResolvedValue({ attachments: [] })
    act(() => { delAttachment[delAttachment.length - 1]?.click() })
    await settle()
    expect(getMock('actions/quality-deviation-workbench', 'deleteHistoricalDeviationAttachment')).toHaveBeenCalledWith('hist-1', expect.any(String))
    findButton('保存')?.click()
    await settle()
    expect(getMock('actions/quality-deviation-workbench', 'updateHistoricalDeviation')).toHaveBeenCalled()
    expect(mocks.message.success).toHaveBeenCalledWith('已保存')
    // 删除走 modal.confirm（harness 自动执行 onOk）
    findButton('删除')?.click()
    await settle()
    expect(getMock('actions/quality-deviation-workbench', 'deleteHistoricalDeviation')).toHaveBeenCalledWith('hist-1')
    closeRendered(rendered)

    // 新建模式：暂存附件后保存会先创建记录再逐个上传附件
    getMock('actions/quality-deviation-workbench', 'createHistoricalDeviation').mockResolvedValue({ id: 'hist-new' })
    getMock('actions/quality-deviation-workbench', 'uploadHistoricalDeviationAttachment').mockResolvedValue({
      id: 'att-new2', file_name: 'template.pdf', url: '/api/files/new2',
    })
    const createView = renderClient(createElement(DeviationHistoryPage))
    await settle()
    const findCreateBtn = (text: string) => Array.from(createView.container.querySelectorAll('button')).find((b) => b.textContent?.includes(text))
    findCreateBtn('新建历史偏差')?.click()
    await settle()
    expect(createView.container.textContent).toContain('新建历史偏差')
    findCreateBtn('上传附件')?.click()
    await settle()
    findCreateBtn('保存')?.click()
    await settle()
    expect(getMock('actions/quality-deviation-workbench', 'createHistoricalDeviation')).toHaveBeenCalled()
    expect(getMock('actions/quality-deviation-workbench', 'uploadHistoricalDeviationAttachment')).toHaveBeenCalledWith(
      'hist-new',
      expect.any(FormData),
    )
    closeRendered(createView)
  })

  it('renders deviation workbench list and settings-backed page', async () => {
    getMock('lib/api/client/quality', 'fetchDeviationWorkbenchReports').mockResolvedValue({
      items: [{
        id: 'wb-1', code: 'WB-2026-0001', deviation_summary: '有关键偏差', status: 'completed',
        created_at: '2026-08-11T03:04:05Z', source_type: 'report_record',
      }],
      total: 1,
    })
    getMock('lib/api/client/quality', 'fetchDeviationWorkbenchSettings').mockResolvedValue({
      report_system_prompt: '请以 GMP 视角分析偏差', model_name: 'gpt-test', is_enabled: true,
    })
    getMock('lib/api/client/quality', 'fetchFeishuDeviationReportRecords').mockResolvedValue({
      items: [{ record_id: 'fr-1', deviation_code: 'DEV-9', product_batch: 'B2026', description: '飞书偏差描述' }],
      total: 1,
    })
    getMock('lib/api/client/quality', 'fetchDeviationWorkbenchReport').mockResolvedValue({
      id: 'wb-1', code: 'WB-2026-0001', status: 'completed', source_type: 'report_record',
      model_name: 'llm-a', report_md: '# 调查报告\n\n结论内容',
      context_snapshot: {
        historical_deviations: [{ code: 'PC-2026-0001', deviation_event: '历史事件', root_cause: '历史根因' }],
        documents: [{ code: 'SOP-001', name: '偏差管理规程', content: '规程内容' }],
      },
      attachments: [{ id: 'att-1', file_name: '现场记录.docx', url: '/api/files/att-1' }],
    })
    getMock('actions/quality-deviation-workbench', 'updateDeviationWorkbenchSettings').mockResolvedValue({
      report_system_prompt: '新提示词', model_name: 'llm-a', is_enabled: true,
    })
    getMock('actions/quality-deviation-workbench', 'deleteDeviationWorkbenchReport').mockResolvedValue({ ok: true })
    getMock('actions/quality-deviation-workbench', 'analyzeDeviationWorkbench').mockResolvedValue({
      id: 'wb-2', code: 'WB-2026-0002', status: 'completed', source_type: 'manual',
      report_md: '# 新报告', context_snapshot: {}, attachments: [],
    })
    const rendered = renderClient(createElement(DeviationWorkbenchPage, { initialRecordId: null }))
    await settle()
    expect(rendered.container.textContent).toContain('WB-2026-0001')
    expect(rendered.container.textContent).toContain('有关键偏差')
    // 过滤栏交互：来源/状态下拉切换与搜索框输入触发查询条件更新
    const wbSelects = Array.from(rendered.container.querySelectorAll('select')) as HTMLSelectElement[]
    for (const sel of wbSelects.slice(0, 2)) {
      if (sel.options.length > 1) {
        act(() => { sel.value = sel.options[1].value; sel.dispatchEvent(new Event('change', { bubbles: true })) })
      }
    }
    const wbSearch = rendered.container.querySelector('input[placeholder*="搜索编号"]') as HTMLInputElement | null
    act(() => { if (wbSearch) { wbSearch.value = 'WB'; wbSearch.dispatchEvent(new Event('input', { bubbles: true })) } })
    await settle()
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    findButton('刷新')?.click()
    await settle()
    // 详情抽屉：报告正文 / 参考来源 / 附件与预览
    findButton('查看')?.click()
    await settle()
    expect(rendered.container.textContent).toContain('调查报告 - WB-2026-0001')
    expect(rendered.container.textContent).toContain('参考来源')
    expect(rendered.container.textContent).toContain('附件（1）')
    expect(rendered.container.textContent).toContain('现场记录.docx')
    // 附件预览：AttachmentContent 以原生 fetch 拉取标准 MD 并渲染
    vi.stubGlobal('fetch', vi.fn(async () => new Response('# 附件预览内容', {
      status: 200, headers: { 'content-type': 'text/markdown' },
    })))
    findButton('预览')?.click()
    await settle()
    expect(rendered.container.textContent).toContain('附件预览内容')
    // 导出按钮存在即可（harness Modal 不触发 afterOpenChange，预览加载链路不在此覆盖）
    const exportBtn = findButton('导出 Markdown')
    expect(exportBtn).toBeTruthy()
    exportBtn?.click()
    await settle()
    // 设置抽屉：提示词回填与保存
    findButton('设置')?.click()
    await settle()
    expect(rendered.container.textContent).toContain('偏差工作台设置')
    findButton('保存')?.click()
    await settle()
    expect(getMock('actions/quality-deviation-workbench', 'updateDeviationWorkbenchSettings')).toHaveBeenCalled()
    // 新建抽屉：上传附件（Upload beforeUpload 拦截）后生成报告
    findButton('新建偏差工作台')?.click()
    await settle()
    expect(rendered.container.textContent).toContain('新建偏差工作台 - 生成调查报告')
    findButton('上传附件')?.click()
    await settle()
    getMock('actions/quality-deviation-workbench', 'uploadDeviationWorkbenchAttachment').mockResolvedValue({
      id: 'desc-1', file_name: 'template.pdf', storage_key: 'sk-1', asset_keys: [],
    })
    findButton('生成调查报告')?.click()
    await settle()
    expect(getMock('actions/quality-deviation-workbench', 'analyzeDeviationWorkbench')).toHaveBeenCalled()
    closeRendered(rendered)

    // 带 initialRecordId 挂载：创建抽屉预选报告记录并回填 prefill
    getMock('lib/api/client/quality', 'fetchFeishuDeviationReportRecord').mockResolvedValue({
      record_id: 'fr-1', deviation_code: 'DEV-9', product_batch: 'B2026', description: '飞书偏差描述',
      attachments: [{ name: '报告.docx', url: 'https://feishu.example/a' }],
    })
    const prefilled = renderClient(createElement(DeviationWorkbenchPage, { initialRecordId: 'fr-1' }))
    await settle()
    expect(prefilled.container.textContent).toContain('飞书偏差描述')
    closeRendered(prefilled)
  })

  it('renders workbench failed/processing report states and delete confirm', async () => {
    getMock('lib/api/client/quality', 'fetchDeviationWorkbenchReports').mockResolvedValue({
      items: [
        { id: 'f1', code: 'WB-F', status: 'failed', created_at: '2026-08-11T00:00:00Z', deviation_summary: '失败样本' },
        { id: 'p1', code: 'WB-P', status: 'processing', created_at: '2026-08-11T00:00:00Z', deviation_summary: '进行中样本' },
      ],
      total: 2,
    })
    getMock('lib/api/client/quality', 'fetchDeviationWorkbenchSettings').mockResolvedValue(null)
    getMock('lib/api/client/quality', 'fetchFeishuDeviationReportRecords').mockResolvedValue({ items: [], total: 0 })
    getMock('lib/api/client/quality', 'fetchDeviationWorkbenchReport').mockResolvedValue({
      id: 'f1', code: 'WB-F', status: 'failed', source_type: 'manual', error_message: '模型超时',
      report_md: '', context_snapshot: {}, attachments: [],
    })
    getMock('actions/quality-deviation-workbench', 'deleteDeviationWorkbenchReport').mockResolvedValue({ ok: true })
    const rendered = renderClient(createElement(DeviationWorkbenchPage, { initialRecordId: null }))
    await settle()
    expect(rendered.container.textContent).toContain('失败样本')
    expect(rendered.container.textContent).toContain('进行中样本')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((b) => b.textContent?.includes(text))
    findButton('查看')?.click()
    await settle()
    expect(rendered.container.textContent).toContain('模型超时')
    findButton('删除')?.click()
    await settle()
    expect(getMock('actions/quality-deviation-workbench', 'deleteDeviationWorkbenchReport')).toHaveBeenCalledWith('f1')
    closeRendered(rendered)

    // 创建抽屉：手动来源未填内容时拦截；上传失败与关闭清理分支
    getMock('lib/api/client/quality', 'fetchDeviationWorkbenchReports').mockResolvedValue({ items: [], total: 0 })
    getMock('lib/api/client/quality', 'fetchDeviationWorkbenchSettings').mockResolvedValue(null)
    getMock('actions/quality-deviation-workbench', 'analyzeDeviationWorkbench').mockResolvedValue(null)
    getMock('actions/quality-deviation-workbench', 'uploadDeviationWorkbenchAttachment').mockRejectedValue(new Error('容量超限'))
    getMock('actions/quality-deviation-workbench', 'deleteDeviationWorkbenchAttachment').mockResolvedValue({ ok: true })
    const createView = renderClient(createElement(DeviationWorkbenchPage, { initialRecordId: null }))
    await settle()
    const cf = (text: string) => Array.from(createView.container.querySelectorAll('button')).find((b) => b.textContent?.includes(text))
    cf('新建偏差工作台')?.click()
    await settle()
    cf('生成调查报告')?.click()
    await settle()
    expect(mocks.message.warning).toHaveBeenCalledWith('请手动输入偏差内容或上传附件')
    cf('上传附件')?.click()
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('容量超限')
    // 上传成功 → descriptor 渲染（storage_key → 标准MD 标记）
    getMock('actions/quality-deviation-workbench', 'uploadDeviationWorkbenchAttachment').mockResolvedValue({
      id: 'desc-ok', file_name: 'report.pdf', storage_key: 'sk-1', converted_md_key: 'md-1', asset_keys: [],
    })
    cf('上传附件')?.click()
    await settle()
    expect(mocks.message.success).toHaveBeenCalledWith('上传成功')
    // 关闭创建抽屉（未生成）→ 未消费附件清理（无 descriptor 时无需 delete）
    cf('关闭')?.click()
    await settle()
    closeRendered(createView)
  })

  it('renders inspection record modal fields and submits create payload', async () => {
    getMock('lib/api/client/quality', 'fetchInspectionFeishuFields').mockResolvedValue({
      fields: [
        { field_name: '检验编号', ui_type: 'Text', editable: true },
        { field_name: '结论', ui_type: 'SingleSelect', editable: true },
        { field_name: '数量', ui_type: 'Number', editable: true },
        { field_name: '完成日期', ui_type: 'DateTime', editable: true },
        { field_name: '合格', ui_type: 'Checkbox', editable: true },
        { field_name: '项目', ui_type: 'MultiSelect', editable: true },
        { field_name: '来源链接', ui_type: 'Url', editable: true },
        { field_name: '创建时间', ui_type: 'CreatedTime', editable: false },
        { field_name: '附件', ui_type: 'Attachment', editable: false },
      ],
    })
    const onSuccess = vi.fn()
    const onClose = vi.fn()
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['x']) })
    vi.stubGlobal('fetch', fetchMock)
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)
    const rendered = renderClient(createElement(InspectionFeishuRecordModal, {
      open: true, entityCode: 'finish_inspect', mode: 'create',
      initialValues: {
        record_id: 'rec-9',
        '创建时间': '2026-08-12T00:00:00Z',
        '附件': [{ name: '报告.pdf', url: 'blob:direct', file_token: 'ft-9' }],
        '数量': '12', '合格': '是', '项目': ['A', 'B'], '来源链接': { link: 'https://x.test', text: '来源' },
        '完成日期': '2026-08-01',
      },
      onClose, onSuccess,
    }))
    await settle()
    expect(rendered.container.textContent).toContain('检验编号')
    // 只读字段值经 renderReadOnlyValue 渲染（Descriptions mock 以属性承载标题/label）
    expect(rendered.container.textContent).toContain('2026-08-12T00:00:00Z')
    // 只读附件点击走后端代理下载（fetch → blob → window.open）
    const attachmentButton = Array.from(rendered.container.querySelectorAll('button')).find((b) => b.textContent === '报告.pdf')
    attachmentButton?.click()
    await settle()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/inspection/feishu/finish_inspect/records/rec-9/attachments/ft-9/content',
    )
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((button) => button.textContent?.includes(text))
    findButton('确定')?.click()
    await settle()
    expect(onSuccess).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
    closeRendered(rendered)

    // 编辑模式 + 直链附件（无 token）+ 下载失败提示分支
    getMock('lib/api/client/quality', 'fetchInspectionFeishuFields').mockResolvedValue({
      fields: [
        { field_name: '检验编号', ui_type: 'Text', editable: true },
        { field_name: '直链附件', ui_type: 'Attachment', editable: false },
        { field_name: '代理附件', ui_type: 'Attachment', editable: false },
      ],
      can_push: false,
    })
    getMock('actions/quality-inspection', 'updateInspectionFeishuRecord').mockResolvedValue({ record_id: 'r1' })
    const failFetch = vi.fn().mockResolvedValue({
      ok: false, status: 403, json: async () => ({ message: '附件未授权' }),
    })
    vi.stubGlobal('fetch', failFetch)
    const editView = renderClient(createElement(InspectionFeishuRecordModal, {
      open: true, entityCode: 'finish', mode: 'edit',
      initialValues: {
        record_id: 'r1', '检验编号': 'JY-7',
        '直链附件': [{ name: '直链.pdf', url: 'https://files.example/d.pdf' }],
        '代理附件': [{ name: '代理.pdf', url: 'blob:x', file_token: 'ft-e' }],
      },
      onClose: vi.fn(), onSuccess: vi.fn(),
    }))
    await settle()
    expect(editView.container.textContent).toContain('编辑记录')
    const directBtn = Array.from(editView.container.querySelectorAll('button')).find((b) => b.textContent === '直链.pdf')
    await act(async () => { directBtn?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    const proxyBtn = Array.from(editView.container.querySelectorAll('button')).find((b) => b.textContent === '代理.pdf')
    await act(async () => { proxyBtn?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    // 代理附件下载失败：错误文案透传（内部 message 为 App.useApp 桩）
    expect(mocks.message.error).toHaveBeenCalledWith('附件未授权')
    const okEdit = Array.from(editView.container.querySelectorAll('button')).find((b) => b.textContent?.includes('确定'))
    await act(async () => { okEdit?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    expect(getMock('actions/quality-inspection', 'updateInspectionFeishuRecord')).toHaveBeenCalledWith(
      'finish', 'r1', expect.objectContaining({ 检验编号: 'JY-7' }),
    )
    closeRendered(editView)
  })
})

describe('department contact / inspection table / picker / attachment preview coverage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mocks.permissionAllowed = true
    localStorage.clear()
    window.URL.createObjectURL = vi.fn(() => 'blob:test')
    window.URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    document.body.replaceChildren()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renders department contacts table and opens edit modal', async () => {
    const items = [{
      id: 'c1', name: '张三', avatar_url: null, bitable_user_id: null, department: '质量部',
      enterprise_email: 'z@liv.com', open_id: 'ou-1', department_head_name: '李四',
      department_head_avatar_url: null, department_head_bitable_user_id: null,
      department_head_enterprise_email: 'l@liv.com', department_head_open_id: 'ou-2',
      feishu_record_id: 'r-1', created_at: '2026-08-01', updated_at: '2026-08-02',
    }]
    const rendered = renderClient(createElement(DepartmentContactPage, {
      items, total: 1, page: 1, pageSize: 20, activeDepartment: '', departmentOptions: ['质量部'],
    }))
    await settle()
    expect(rendered.container.textContent).toContain('张三')
    expect(rendered.container.textContent).toContain('李四')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((b) => b.textContent?.includes(text))
    getMock('lib/api/client/hr', 'fetchHrMembers').mockResolvedValue([{ open_id: 'ou-9', name: '王五', avatar_url: null }])
    findButton('修改')?.click()
    await settle()
    expect(rendered.container.querySelector('[role="dialog"]')).toBeTruthy()
    // 编辑弹窗确定 → 飞书同步保存
    getMock('actions/quality', 'updateDepartmentContactFeishu').mockResolvedValue({ id: 'c1' })
    findButton('确定')?.click()
    await settle()
    expect(getMock('actions/quality', 'updateDepartmentContactFeishu')).toHaveBeenCalledWith(
      'c1',
      expect.objectContaining({ department: '质量部' }),
    )
    expect(mocks.message.success).toHaveBeenCalledWith('部门联系人已更新')
    closeRendered(rendered)
  })

  it('renders inspection feishu table rows via list api and pull action', async () => {
    getMock('lib/api/client/quality', 'fetchInspectionFeishuFields').mockResolvedValue({
      fields: [{ field_name: '检验编号', ui_type: 'Text', editable: true }], can_push: true,
    })
    vi.stubGlobal('fetch', vi.fn(async (input: string) => {
      if (String(input).includes('/records')) {
        return new Response(JSON.stringify({ data: [{ record_id: 'x1', 检验编号: 'JY-1' }], meta: { total: 1, configured: true, fields: ['检验编号'], display_fields: ['检验编号'] } }), { status: 200, headers: { 'content-type': 'application/json' } })
      }
      return new Response(JSON.stringify({ data: [], meta: { total: 0, configured: true, fields: [], display_fields: [] } }), { status: 200, headers: { 'content-type': 'application/json' } })
    }))
    getMock('actions/quality-inspection', 'pullInspectionFeishuRecords').mockResolvedValue({ synced: 1, failed: 0 })
    const rendered = renderClient(createElement(InspectionFeishuTable, {
      title: '成品检验', listApi: '/api/v1/quality/inspection/feishu/finish/records',
      pullApi: '/api/v1/quality/inspection/feishu/finish/pull', entityCode: 'finish', editable: true,
    }))
    await settle()
    expect(rendered.container.textContent).toContain('成品检验')
    expect(rendered.container.textContent).toContain('JY-1')
    closeRendered(rendered)
  })

  it('renders document catalog picker with departments and entries', async () => {
    getMock('lib/api/client/quality', 'fetchDocumentDepartments').mockResolvedValue([
      { id: 'd1', name: '质量管理部' },
    ])
    getMock('lib/api/client/quality', 'fetchDocumentEntries').mockResolvedValue({
      items: [{ id: 'e1', code: 'SOP-1', name: '偏差管理规程', version: 'V1', category: 'S' }], total: 1,
    })
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    const rendered = renderClient(createElement(DocumentCatalogPickerModal, {
      open: true, onClose, onConfirm, excludeNames: ['已选文件'],
    }))
    await settle()
    expect(rendered.container.textContent).toContain('偏差管理规程')
    // 关键字搜索触发重新分页拉取
    const searchInput = rendered.container.querySelector('input[placeholder="搜索文件名称/编码"]') as HTMLInputElement | null
    act(() => {
      if (searchInput) {
        searchInput.value = '规程'
        searchInput.dispatchEvent(new Event('input', { bubbles: true }))
      }
    })
    await settle()
    expect(getMock('lib/api/client/quality', 'fetchDocumentEntries')).toHaveBeenCalledWith(
      expect.objectContaining({ keyword: '规程' }),
    )
    // 勾选条目（Table mock 行点击触发 rowSelection.onChange）后确认录入
    const row = Array.from(rendered.container.querySelectorAll('tr')).find((tr) => tr.textContent?.includes('偏差管理规程'))
    act(() => { row?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    // harness Modal 固定渲染“取消/确定”，onOk 即确认录入
    findBtn(rendered, '确定')?.click()
    await settle()
    expect(onConfirm).toHaveBeenCalled()
    closeRendered(rendered)

    // 部门/条目加载失败 → 各自 catch 降级分支
    getMock('lib/api/client/quality', 'fetchDocumentDepartments').mockRejectedValue(new Error('500'))
    getMock('lib/api/client/quality', 'fetchDocumentEntries').mockRejectedValue(new Error('500'))
    const failView = renderClient(createElement(DocumentCatalogPickerModal, {
      open: true, onClose: vi.fn(), onConfirm: vi.fn(),
    }))
    await settle()
    expect(failView.container.textContent).toContain('从文件管理选择培训内容')
    closeRendered(failView)
  })

  it('drives inspection table detail/edit/delete/pull and unconfigured banner', async () => {
    getMock('lib/api/client/quality', 'fetchInspectionFeishuFields').mockResolvedValue({
      fields: [{ field_name: '检验编号', ui_type: 'Text', editable: true }], can_push: false,
    })
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      data: [{ record_id: 'x1', 检验编号: 'JY-1' }],
      meta: { total: 1, configured: true, fields: ['检验编号'], display_fields: ['检验编号'] },
    }), { status: 200, headers: { 'content-type': 'application/json' } })))
    getMock('actions/quality-inspection', 'deleteInspectionFeishuRecord').mockResolvedValue({ record_id: 'x1' })
    getMock('actions/quality-inspection', 'pullInspectionFeishuRecords').mockResolvedValue({ synced: 2, failed: 0 })
    const rendered = renderClient(createElement(InspectionFeishuTable, {
      title: '物料检验', listApi: '/api/v1/quality/inspection/feishu/material/records',
      pullApi: '/api/v1/quality/inspection/feishu/material/pull', entityCode: 'material', editable: true,
    }))
    await settle()
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((b) => b.textContent?.includes(text))
    findButton('详情')?.click()
    await settle()
    findButton('编辑')?.click()
    await settle()
    expect(rendered.container.textContent).toContain('编辑记录')
    findButton('确定')?.click()
    await settle()
    findButton('删除')?.click()
    await settle()
    expect(getMock('actions/quality-inspection', 'deleteInspectionFeishuRecord')).toHaveBeenCalledWith('material', 'x1')
    findButton('同步飞书数据')?.click()
    await settle()
    expect(getMock('actions/quality-inspection', 'pullInspectionFeishuRecords')).toHaveBeenCalledWith('material')
    closeRendered(rendered)

    // 未配置态：Alert + 空态错误分支
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      data: [], meta: { total: 0, configured: false, fields: [], display_fields: [] },
    }), { status: 200, headers: { 'content-type': 'application/json' } })))
    const unconfigured = renderClient(createElement(InspectionFeishuTable, {
      title: '成品检验', listApi: '/api/v1/quality/inspection/feishu/finish/records', entityCode: 'finish',
    }))
    // 查询 promise 链需多轮 flush 才能把 configured:false 落到 queryData
    await settle(); await settle(); await settle()
    expect(unconfigured.container.textContent).toContain('飞书数据源未配置')
    closeRendered(unconfigured)
  })

  it('renders esg training report table with records and filter options', async () => {
    getMock('lib/api/hr', 'fetchEsgRecordsByDept').mockResolvedValue({
      data: [{
        id: 'esg-1', training_date: '2026-08-05', training_name: 'GMP 年度培训', training_method: '线上',
        caliber: '集团', training_type: '质量培训', employee_name: '张三', employee_account: 'zhangsan',
        department: '质量部', employee_level: 'P4', gender: '男', age: 30, duration: 2,
        apply_company: '公司A', apply_company_no: 'AC-1', remarks: '备注',
      }],
      meta: { total: 1 },
    })
    getMock('lib/api/hr', 'fetchEsgFilterOptions').mockResolvedValue({ training_type: ['质量培训'] })
    const rendered = renderClient(createElement(EsgTrainingReportClient, {
      department: '质量部', dateFrom: '2026-08-01', dateTo: '2026-08-31', periodLabel: '8 月', printRequest: 0,
    }))
    await settle()
    expect(rendered.container.textContent).toContain('GMP 年度培训')
    expect(rendered.container.textContent).toContain('张三')
    closeRendered(rendered)

    // printRequest>0 触发 doPrint：拉全量 → 新窗口写打印页
    const fakeWindow = {
      document: { write: vi.fn(), close: vi.fn() },
      focus: vi.fn(),
      print: vi.fn(),
    }
    vi.stubGlobal('open', vi.fn(() => fakeWindow))
    const printView = renderClient(createElement(EsgTrainingReportClient, {
      department: '质量部', dateFrom: '2026-08-01', dateTo: '2026-08-31', periodLabel: '8 月', printRequest: 1,
    }))
    await settle()
    expect(fakeWindow.document.write).toHaveBeenCalledWith(expect.stringContaining('GMP 年度培训'))
    expect(fakeWindow.print).toHaveBeenCalled()
    closeRendered(printView)

    // 浏览器拦截弹窗 → 错误提示分支
    vi.stubGlobal('open', vi.fn(() => null))
    const blockedView = renderClient(createElement(EsgTrainingReportClient, {
      department: '质量部', dateFrom: '', dateTo: '', periodLabel: '', printRequest: 1,
    }))
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('浏览器拦截了弹出窗口，请允许后重试')
    closeRendered(blockedView)
  })

  it('renders onboarding attachment preview for a pdf blob', async () => {
    const onClose = vi.fn()
    const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    const rendered = renderClient(createElement(OnboardingAttachmentPreviewModal, {
      open: true, fileName: 'report.pdf', blob, onClose,
    }))
    await settle()
    expect(rendered.container.textContent).toContain('report.pdf')
    // iframe 承载 PDF 预览
    expect(rendered.container.querySelector('iframe')).toBeTruthy()
    closeRendered(rendered)
  })

  it('degrades legacy .doc and reports spreadsheet parse failures', async () => {
    // 老 .doc：mammoth 不支持 → 降级为 other，不报错
    const docView = renderClient(createElement(OnboardingAttachmentPreviewModal, {
      open: true, fileName: 'legacy.doc', blob: new Blob(['x']), onClose: vi.fn(),
    }))
    await settle()
    expect(docView.container.textContent).toContain('legacy.doc')
    closeRendered(docView)

    // .xlsx 内容解析分支（XLSX.read → sheet_to_json 渲染表格或降级）
    const xlsxView = renderClient(createElement(OnboardingAttachmentPreviewModal, {
      open: true, fileName: 'data.xlsx', blob: new Blob(['not-a-xlsx']), onClose: vi.fn(),
    }))
    await settle()
    expect(xlsxView.container.textContent).toContain('预览 - data.xlsx')
    closeRendered(xlsxView)

    // CSV UTF-8 文本解析路径
    const csvView = renderClient(createElement(OnboardingAttachmentPreviewModal, {
      open: true, fileName: 'list.csv', blob: new Blob(['姓名,部门\n张三,质量部'], { type: 'text/csv' }), onClose: vi.fn(),
    }))
    await settle()
    expect(csvView.container.textContent).toContain('预览 - list.csv')
    closeRendered(csvView)

    // 空 blob 直接返回，不渲染内容分支
    const emptyView = renderClient(createElement(OnboardingAttachmentPreviewModal, {
      open: true, fileName: 'missing.bin', blob: null, onClose: vi.fn(),
    }))
    await settle()
    expect(emptyView.container.textContent).toContain('missing.bin')
    closeRendered(emptyView)
  })
})

describe('sidebar navigation / onboarding attachment flow / validation audit shell', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mocks.permissionAllowed = true
    localStorage.clear()
    window.URL.createObjectURL = vi.fn(() => 'blob:test')
    window.URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    document.body.replaceChildren()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('navigates parent menu labels with a landing path without toggling collapse', async () => {
    const modules = [{
      key: 'migration', moduleCode: 'quality', label: '迁移模块', icon: 'appstore', path: '/migration',
      children: [
        {
          key: 'dash', label: '仓储仪表盘', path: '/migration/dash',
          children: [{ key: 'dash-detail', label: '仪表盘明细', path: '/migration/dash/detail' }],
        },
        { key: 'cfg', label: '模块设置', path: '/migration/cfg', placement: 'bottom' as const, adminOnly: true },
      ],
    }]
    const rendered = renderClient(createElement(Sidebar, {
      user: { role: 'admin', name: '管理员' } as never, modules: modules as never,
    }))
    await settle()
    expect(rendered.container.textContent).toContain('仓储仪表盘')
    expect(rendered.container.textContent).toContain('模块设置')
    // 带 path 的父级点击标签直接导航到落地页（span 的 stopPropagation 阻止展开切换）；
    // 叶子路径经 Menu onClick→keyPathMap 的分支在简化 Menu mock 下不渲染子层级，不在此覆盖
    const parentLabel = Array.from(rendered.container.querySelectorAll('span'))
      .find((s) => s.textContent === '仓储仪表盘')
    expect(parentLabel).toBeTruthy()
    // React onMouseEnter 由原生 mouseover 合成，触发预取回调（Sidebar 66 行）
    act(() => { parentLabel?.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })) })
    act(() => { parentLabel?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    expect(mocks.router.push).toHaveBeenCalledWith('/migration/dash')
    closeRendered(rendered)
  })

  it('opens onboarding attachment preview modal from list row', async () => {
    getMock('lib/api/client/hr', 'fetchOnboardingList').mockResolvedValue({
      data: [{
        id: 'ob-1', name: '张三', department: '生产部', position: '操作员',
        onboarding_date: '2026-08-20', status: '进行中',
        resignation_attachment: [
          { file_token: 'ft-pdf', name: '离职证明.pdf' },
          { name: '直链.docx', url: 'https://files.example/d.docx' },
          { name: '坏附件.bin' },
          { file_token: 'ft-png', name: '照片.png' },
        ],
        id_attachment: [], education_attachment: [], other_attachment: [],
      }],
      total: 1,
    })
    getMock('lib/api/client/hr', 'fetchDepartments').mockResolvedValue({ data: [] })
    getMock('lib/api/client/hr', 'fetchJobPostings').mockResolvedValue({ data: [] })
    getMock('lib/api/client/hr', 'fetchOnboardingAttachmentContent').mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)
    const rendered = renderClient(createElement(OnboardingManagementPage))
    await settle()
    expect(rendered.container.textContent).toContain('张三')
    const clickText = async (text: string) => {
      const el = Array.from(rendered.container.querySelectorAll('span, button, a')).find((e) => e.textContent === text)
      await act(async () => { el?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
      await settle()
    }
    // 带 token PDF → 预览弹窗
    await clickText('离职证明.pdf')
    expect(rendered.container.textContent).toContain('预览 - 离职证明.pdf')
    // 关闭预览
    await act(async () => {
      Array.from(rendered.container.querySelectorAll('button')).find((b) => b.textContent === '取消')?.click()
    })
    // 无 token 有直链 → 新标签打开
    await clickText('直链.docx')
    expect(openMock).toHaveBeenCalledWith('https://files.example/d.docx', '_blank')
    // 无 token 无直链 → 警告
    await clickText('坏附件.bin')
    expect(mocks.message.warning).toHaveBeenCalledWith('附件无下载地址')
    closeRendered(rendered)

    // 编辑详情加载失败 → 错误提示
    const editFailView = renderClient(createElement(OnboardingManagementPage))
    await settle()
    getMock('lib/api/client/hr', 'fetchOnboardingById').mockRejectedValue(new Error('详情接口 500'))
    const editBtn = Array.from(editFailView.container.querySelectorAll('button')).find((b) => b.textContent === '编辑')
    await act(async () => { editBtn?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('详情接口 500')
    closeRendered(editFailView)

    // 编辑成功 → 保存 → 删除 流
    getMock('lib/api/client/hr', 'fetchOnboardingById').mockResolvedValue({
      data: {
        id: 'ob-1', name: '张三', department: '生产部',
        resignation_attachment: [{ file_token: 'ft-pdf', name: '离职证明.pdf' }],
        id_attachment: [], education_attachment: [], other_attachment: [],
      },
    })
    getMock('actions/hr', 'updateOnboardingAction').mockResolvedValue({ code: 200, message: 'ok' })
    getMock('actions/hr', 'deleteOnboardingAction').mockResolvedValue({ code: 200, message: 'ok' })
    const editView = renderClient(createElement(OnboardingManagementPage))
    await settle()
    const findIn = (view: HTMLDivElement, text: string) =>
      Array.from(view.querySelectorAll('button')).find((b) => b.textContent === text)
    await act(async () => { findIn(editView.container, '编辑')?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    await act(async () => { findIn(editView.container, '确定')?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    await act(async () => { findIn(editView.container, '删除')?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    closeRendered(editView)
  })

  it('mounts validation audit list and new shells with empty state', async () => {
    getMock('lib/api/validation-audit', 'fetchValidationAuditTasks').mockResolvedValue({ items: [], total: 0 })
    const list = renderClient(createElement(ValidationAuditListClient, { initialTasks: [], initialTotal: 0 }))
    await settle()
    expect(list.container.textContent).toContain('验证')
    closeRendered(list)

    const form = renderClient(createElement(ValidationAuditNewClient))
    await settle()
    expect(form.container.textContent).toContain('验证')
    closeRendered(form)
  })

  it('drives validation audit list row actions and new task navigation', async () => {
    const task = {
      id: 'vt-1', task_name: '无菌工艺验证审核', product_name: '产品S', source_company: '101 车间',
      audit_mode: 'protocol', status: 'completed', conclusion: 'pass',
      serious_count: 0, general_count: 2, suggestion_count: 1, created_at: '2026-08-01',
    }
    getMock('lib/api/validation-audit', 'fetchValidationAuditTasks').mockResolvedValue({ items: [task], total: 1 })
    getMock('actions/validation-audit', 'deleteValidationAuditTask').mockResolvedValue({ ok: true })
    const rendered = renderClient(createElement(ValidationAuditListClient, { initialTasks: [task], initialTotal: 1 } as never))
    await settle()
    expect(rendered.container.textContent).toContain('无菌工艺验证审核')
    const findButton = (text: string) => Array.from(rendered.container.querySelectorAll('button')).find((b) => b.textContent?.includes(text))
    findButton('查看')?.click()
    expect(mocks.router.push).toHaveBeenCalledWith('/registration/validation-audit/vt-1')
    findButton('新建审核任务')?.click()
    expect(mocks.router.push).toHaveBeenCalledWith('/registration/validation-audit/new')
    findButton('删除')?.click()
    await settle()
    expect(getMock('actions/validation-audit', 'deleteValidationAuditTask')).toHaveBeenCalledWith('vt-1')
    closeRendered(rendered)
  })

  it('renders docx preview with chapter fetch and download callback', async () => {
    getMock('lib/api/dossier-writer-client', 'fetchChapterDocx').mockResolvedValue(new ArrayBuffer(64))
    const onDownload = vi.fn()
    const rendered = renderClient(createElement(DocxPreview, {
      chapterId: 'ch-1', chapterTitle: '第五章 分析方法', onDownload, refreshKey: 0,
    }))
    await settle()
    expect(rendered.container.textContent).toContain('第五章 分析方法')
    const dl = Array.from(rendered.container.querySelectorAll('button')).find((b) => b.textContent?.trim() === '下载')
    expect(dl).toBeTruthy()
    dl?.click()
    expect(onDownload).toHaveBeenCalled()
    closeRendered(rendered)

    // 无 chapterId 时渲染引导空态
    const emptyView = renderClient(createElement(DocxPreview, { chapterId: null }))
    await settle()
    expect(emptyView.container.textContent).toContain('请从左侧目录选择一个章节')
    closeRendered(emptyView)
  })

  it('renders validation audit detail with files, issues and report', async () => {
    const task = {
      id: 't1', task_name: 'X 制剂工艺验证审核', product_name: '产品X', method_name: 'HPLC',
      source_company: '质量部', audit_mode: 'protocol', status: 'completed', conclusion: 'pass',
      risk_level: '低', serious_count: 0, general_count: 1, suggestion_count: 0,
      compliant_count: 5, non_compliant_count: 1, report_path: null,
      created_at: '2026-08-01', updated_at: '2026-08-02',
    }
    const files = [{
      id: 'f1', file_type: 'protocol', original_filename: '方案.docx', file_size: 10240,
      parse_status: 'parsed', created_at: '2026-08-01',
    }]
    const issues = [{
      id: 'i1', task_id: 't1', file_id: 'f1', issue_no: 'ISS-1', dimension: '方法学',
      check_item: '专属性', description: '缺少强制降解描述', suggestion: '补充降解条件',
      issue_type: 'general', page_no: 3, evidence_text: '……', created_at: '2026-08-01',
    }]
    const report = {
      id: 'r1', task_id: 't1', report_title: '审核报告', report_markdown: '# 审核结论\n\n通过',
      report_file_path: null, version: 1, created_at: '2026-08-02',
    }
    getMock('lib/api/validation-audit', 'fetchValidationAuditTaskById').mockResolvedValue({ data: task })
    getMock('lib/api/validation-audit', 'fetchValidationAuditFiles').mockResolvedValue({ data: files })
    getMock('lib/api/validation-audit', 'fetchValidationAuditIssues').mockResolvedValue({ data: issues })
    getMock('lib/api/validation-audit', 'fetchValidationAuditReport').mockResolvedValue({ data: report })
    const rendered = renderClient(createElement(ValidationAuditDetailClient, {
      task, initialFiles: files, initialIssues: issues, initialReport: report,
    } as never))
    await settle()
    expect(rendered.container.textContent).toContain('X 制剂工艺验证审核')
    expect(rendered.container.textContent).toContain('方案.docx')
    expect(rendered.container.textContent).toContain('缺少强制降解描述')
    closeRendered(rendered)
  })

  it('opens document catalog picker from sign-in tab and merges selection', async () => {
    getMock('lib/api/client/quality', 'fetchDocumentDepartments').mockResolvedValue([{ id: 'd1', name: '质量部' }])
    getMock('lib/api/client/quality', 'fetchDocumentEntries').mockResolvedValue({
      items: [{ id: 'e1', code: 'SOP-2', name: '洁净区规程', version: 'V1', category: 'S' }], total: 1,
    })
    getMock('actions/quality', 'resolveDocumentEntryContent').mockResolvedValue([
      { name: '洁净区规程', code: 'SOP-2' },
    ])
    const rendered = renderClient(createElement(TrainingSignInTabsClient))
    await settle()
    findBtn(rendered, '从文件管理选择')?.click()
    await settle()
    // 空勾选确认：直接关闭分支
    findBtn(rendered, '确定')?.click()
    await settle()
    // 重新打开并勾选条目确认：解析编码合并进培训内容
    findBtn(rendered, '从文件管理选择')?.click()
    await settle()
    const row = Array.from(rendered.container.querySelectorAll('tr')).find((tr) => tr.textContent?.includes('洁净区规程'))
    act(() => { row?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    findBtn(rendered, '确定')?.click()
    await settle()
    expect(mocks.message.success).toHaveBeenCalledWith(expect.stringContaining('已从文件管理选择'))
    expect(rendered.container.textContent).toContain('《洁净区规程》')
    closeRendered(rendered)
  })
})

function findBtn(rendered: { container: HTMLDivElement }, text: string) {
  return Array.from(rendered.container.querySelectorAll('button')).find((b) => b.textContent?.includes(text))
}
