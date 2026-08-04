import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const lifecycle = vi.hoisted(() => ({
  effects: [] as Array<() => void | (() => void)>,
  setters: [] as Array<ReturnType<typeof vi.fn>>,
  stateIndex: 0,
  stateOverrides: new Map<number, unknown>(),
}))

const ui = vi.hoisted(() => ({
  form: {
    resetFields: vi.fn(),
    setFieldValue: vi.fn(),
    setFieldsValue: vi.fn(),
    validateFields: vi.fn(),
  },
  message: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
  modal: { confirm: vi.fn() },
}))

const actions = vi.hoisted(() => ({
  createExternalIdentityBinding: vi.fn(),
  exportAgentTrace: vi.fn(),
  getAgentCapabilityImpacts: vi.fn(),
  getAgentConfirmations: vi.fn(),
  getAgentDeliveries: vi.fn(),
  getAgentRuntimeOverview: vi.fn(),
  getAgentToolCatalog: vi.fn(),
  getAgentToolCatalogPage: vi.fn(),
  getAgentTrace: vi.fn(),
  getExternalIdentityBindings: vi.fn(),
  getExternalIdentityConflicts: vi.fn(),
  getFeishuAuthorizations: vi.fn(),
  getLivzonFeishuConfig: vi.fn(),
  getLivzonFeishuGatewayStatus: vi.fn(),
  revokeFeishuAuthorization: vi.fn(),
  saveLivzonFeishuConfig: vi.fn(),
  setAgentToolEnabled: vi.fn(),
  syncLivzonFeishuDirectory: vi.fn(),
  testLivzonFeishuConfig: vi.fn(),
  updateExternalIdentityBindingStatus: vi.fn(),
}))

const users = vi.hoisted(() => ({ getUsers: vi.fn() }))

vi.mock('react', async (importOriginal) => {
  const original = await importOriginal<typeof import('react')>()
  return {
    ...original,
    useCallback: vi.fn((callback) => callback),
    useEffect: vi.fn((effect: () => void | (() => void)) => {
      lifecycle.effects.push(effect)
    }),
    useState: vi.fn((initial: unknown) => {
      const index = lifecycle.stateIndex++
      const setter = vi.fn()
      lifecycle.setters.push(setter)
      return [
        lifecycle.stateOverrides.has(index)
          ? lifecycle.stateOverrides.get(index)
          : initial,
        setter,
      ]
    }),
  }
})

vi.mock('antd', () => {
  const Component = () => null
  const Descriptions = Object.assign(Component, { Item: Component })
  const Form = Object.assign(Component, {
    Item: Component,
    useForm: () => [ui.form],
  })
  const Input = Object.assign(Component, {
    Password: Component,
    Search: Component,
  })
  const ListItem = Object.assign(Component, { Meta: Component })
  const List = Object.assign(Component, { Item: ListItem })
  const Space = Object.assign(Component, { Compact: Component })
  return {
    Alert: Component,
    App: { useApp: () => ({ message: ui.message, modal: ui.modal }) },
    Button: Component,
    Card: Component,
    Col: Component,
    Descriptions,
    Drawer: Component,
    Empty: Component,
    Form,
    Input,
    List,
    Pagination: Component,
    Row: Component,
    Select: Component,
    Space,
    Statistic: Component,
    Switch: Component,
    Table: Component,
    Tabs: Component,
    Tag: Component,
    Typography: { Text: Component, Title: Component },
  }
})

vi.mock('@/actions/settings', () => actions)
vi.mock('@/actions/users', () => users)

import FeishuSettingsClient, {
  AuthorizationConfirmation,
  FeishuAccess,
  IdentityAdmission,
  Overview,
  ToolGovernance,
  TraceDelivery,
} from './FeishuSettingsClient'

interface ElementLike {
  props?: Record<string, unknown>
}

function walk(node: ReactNode | unknown): ElementLike[] {
  if (Array.isArray(node)) return node.flatMap(walk)
  if (typeof node !== 'object' || node === null) return []
  const element = node as ElementLike
  return [
    element,
    ...Object.values(element.props ?? {}).flatMap(walk),
  ]
}

function textOf(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (typeof node === 'object' && node !== null) {
    return textOf((node as ElementLike).props?.children)
  }
  return ''
}

function findButton(tree: unknown, text: string): ElementLike {
  const result = walk(tree).find(
    (element) =>
      typeof element.props?.onClick === 'function' && textOf(element).includes(text),
  )
  expect(result, `button ${text}`).toBeDefined()
  return result as ElementLike
}

function resetHooks(overrides: Record<number, unknown> = {}) {
  lifecycle.effects.length = 0
  lifecycle.setters.length = 0
  lifecycle.stateIndex = 0
  lifecycle.stateOverrides = new Map(
    Object.entries(overrides).map(([key, value]) => [Number(key), value]),
  )
}

function invokeEffects() {
  return lifecycle.effects.map((effect) => effect())
}

const config = {
  id: null,
  config_name: 'Livzon',
  app_id: 'cli_app',
  app_secret_configured: true,
  app_secret_masked: '***',
  tenant_id: 'tenant-a',
  gateway_enabled: true,
  allowed_group_chat_ids: ['oc_group'],
  require_group_mention: true,
  config_version: 3,
  is_active: true,
  updated_at: '2026-08-04T00:00:00Z',
  updated_by: 'admin',
}

const binding = {
  id: 'binding-1',
  tenant_id: 'tenant-a',
  platform: 'feishu' as const,
  app_fingerprint: 'cli_app',
  external_open_id: 'ou_user',
  local_user_id: '00000000-0000-0000-0000-000000000001',
  local_user_name: '张三',
  local_user_department: '质量部',
  source: 'admin' as const,
  status: 'active' as const,
  created_at: '2026-08-04T00:00:00Z',
  updated_at: '2026-08-04T00:00:00Z',
}

const tool = {
  operation: 'quality.create_deviation',
  module: 'quality',
  version: 'v1',
  summary: '创建偏差',
  status: 'active' as const,
  risk_level: 'high',
  write: true,
  confirmation_required: true,
  permission_key: 'quality:write',
  input_schema: { type: 'object' },
  output_schema: { type: 'object', 'x-dazah-schema-source': 'return_annotation' },
  timeout_seconds: 30,
  idempotent: false,
}

describe('FeishuSettingsClient governance lifecycle', () => {
  beforeEach(() => {
    resetHooks()
    vi.clearAllMocks()
    ui.form.validateFields.mockResolvedValue({
      app_id: ' cli_app ',
      app_secret: ' secret ',
      tenant_id: ' tenant-a ',
      gateway_enabled: true,
      allowed_group_chat_ids: ['oc_group'],
      require_group_mention: true,
    })
    actions.getLivzonFeishuConfig.mockResolvedValue(config)
    actions.getLivzonFeishuGatewayStatus.mockResolvedValue({
      gateway: 'connected',
      config_version: 3,
      gateway_reconnects: 1,
    })
    actions.getAgentRuntimeOverview.mockResolvedValue({
      pending_confirmations: 1,
      failed_deliveries: 0,
      latest_error_trace_id: 'trace-1',
      latest_error_at: '2026-08-04T00:00:00Z',
    })
    actions.getExternalIdentityBindings.mockResolvedValue({
      items: [binding], page: 1, page_size: 20, total: 1,
    })
    actions.getExternalIdentityConflicts.mockResolvedValue([])
    actions.getAgentToolCatalog.mockResolvedValue([tool])
    actions.getAgentToolCatalogPage.mockResolvedValue({
      items: [tool], page: 1, page_size: 20, total: 1,
    })
    actions.getAgentCapabilityImpacts.mockResolvedValue([
      { operation: tool.operation, automation_id: 'automation-1' },
    ])
    actions.getAgentConfirmations.mockResolvedValue({
      items: [], page: 1, page_size: 50, total: 0,
    })
    actions.getAgentDeliveries.mockResolvedValue({ items: [] })
    actions.getAgentTrace.mockResolvedValue({
      trace_id: 'trace-1',
      counts: { messages: 0, tool_calls: 1, confirmations: 0, domain_events: 0, deliveries: 0 },
      timeline: [],
    })
    actions.getFeishuAuthorizations.mockResolvedValue([])
    actions.saveLivzonFeishuConfig.mockResolvedValue(config)
    actions.testLivzonFeishuConfig.mockResolvedValue({
      status: 'ok', message: '诊断通过', steps: [{ name: 'token', status: 'ok' }],
    })
    actions.syncLivzonFeishuDirectory.mockResolvedValue({
      status: 'ok', message: '同步完成', bindings: { created: 1, existing: 0, conflicts: [] },
    })
    users.getUsers.mockResolvedValue({ items: [{ id: binding.local_user_id, name: '张三' }] })
    vi.stubGlobal('window', {
      setTimeout: (callback: () => void) => { callback(); return 1 },
      clearTimeout: vi.fn(),
    })
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:test'),
      revokeObjectURL: vi.fn(),
    })
    vi.stubGlobal('document', {
      body: { appendChild: vi.fn() },
      createElement: vi.fn(() => ({
        click: vi.fn(),
        remove: vi.fn(),
        href: '',
        download: '',
      })),
    })
  })

  afterEach(() => vi.unstubAllGlobals())

  it('loads and renders the complete management overview', async () => {
    const tree = FeishuSettingsClient()
    invokeEffects()

    await vi.waitFor(() => {
      expect(actions.getLivzonFeishuConfig).toHaveBeenCalledOnce()
      expect(actions.getLivzonFeishuGatewayStatus).toHaveBeenCalledOnce()
      expect(actions.getAgentRuntimeOverview).toHaveBeenCalledOnce()
      expect(lifecycle.setters[5]).toHaveBeenLastCalledWith(false)
    })

    await (findButton(tree, '刷新运行状态').props?.onClick as () => Promise<void>)()
    expect(actions.getAgentRuntimeOverview).toHaveBeenCalledTimes(2)

    const tabs = walk(tree).find((element) => Array.isArray(element.props?.items))
    const overviewTab = (tabs?.props?.items as Array<{ children: ElementLike }>)[0].children
    ;(overviewTab.props?.onNavigate as (key: string, traceId: string) => void)(
      'trace',
      'trace-1',
    )
    await vi.waitFor(() => expect(actions.getAgentTrace).toHaveBeenCalledWith('trace-1'))

    const onNavigate = vi.fn()
    const overview = Overview({
      config,
      status: {
        configured: true,
        gateway: 'failed',
        config_version: 3,
        credential_version: 2,
        gateway_reconnects: 1,
        tenant_id: 'tenant-a',
        gateway_enabled: true,
        outbox_depth: 2,
        pending_confirmations: 1,
        pending_deliveries: 3,
        event_consumer: 'hermes',
        event_consumer_count: 1,
        gateway_upstream: { release_tag: 'v1', commit_sha: '1234567890abcdef' },
      },
      health: {
        pending_confirmations: 1,
        failed_deliveries: 2,
        latest_error_trace_id: 'trace-1',
        latest_error_at: 'invalid-date',
      },
      onNavigate,
    })
    expect(walk(overview).some(
      (element) => element.props?.title === '外部验收状态',
    )).toBe(false)
    expect(walk(overview).some(
      (element) => String(element.props?.description).includes('不代表当前仍异常'),
    )).toBe(true)
    await (findButton(overview, '查看调用链路').props?.onClick as () => void)()
    expect(onNavigate).toHaveBeenCalledWith('trace', 'trace-1')
  })

  it('saves and diagnoses Feishu access configuration', async () => {
    resetHooks()
    const onSaved = vi.fn()
    const tree = FeishuAccess({
      config,
      status: { gateway: 'connected', config_version: 3, gateway_reconnects: 1 } as never,
      onSaved,
    })
    invokeEffects()
    expect(ui.form.setFieldsValue).toHaveBeenCalled()

    ;(findButton(tree, '保存配置').props?.onClick as () => void)()
    await vi.waitFor(() => expect(ui.modal.confirm).toHaveBeenCalled())
    await ui.modal.confirm.mock.calls.at(-1)?.[0].onOk()
    expect(actions.saveLivzonFeishuConfig).toHaveBeenCalled()
    expect(onSaved).toHaveBeenCalledWith(config)

    ;(findButton(tree, '运行诊断').props?.onClick as () => void)()
    await vi.waitFor(() => expect(actions.testLivzonFeishuConfig).toHaveBeenCalled())
    expect(ui.message.success).toHaveBeenCalled()
  })

  it('loads identities, creates bindings, syncs directory and changes status', async () => {
    resetHooks({ 0: [binding], 1: [{ id: binding.local_user_id, name: '张三' }], 7: 7, 8: [{
      local_user_id: binding.local_user_id,
      local_user_name: '张三',
      external_identifier: 'ou_conflict',
      conflict_type: 'external_owned_by_other',
      conflicting_binding_id: 'binding-2',
    }] })
    const tree = IdentityAdmission({ tenantId: 'tenant-a', appId: 'cli_app' })
    invokeEffects()
    await vi.waitFor(() => expect(actions.getExternalIdentityBindings).toHaveBeenCalled())
    expect(ui.form.setFieldsValue).toHaveBeenCalled()

    const form = walk(tree).find((element) => typeof element.props?.onFinish === 'function')
    await (form?.props?.onFinish as (value: typeof binding) => Promise<void>)(binding)
    expect(actions.createExternalIdentityBinding).toHaveBeenCalledWith(binding)

    ;(findButton(tree, '同步飞书目录').props?.onClick as () => void)()
    await ui.modal.confirm.mock.calls.at(-1)?.[0].onOk()
    expect(actions.syncLivzonFeishuDirectory).toHaveBeenCalled()

    const tables = walk(tree).filter((element) => Array.isArray(element.props?.columns))
    const identityColumns = tables[0].props?.columns as Array<Record<string, unknown>>
    for (const column of identityColumns) {
      if (typeof column.render === 'function') {
        ;(column.render as (value: unknown, item: typeof binding) => unknown)(undefined, binding)
      }
    }
    const operation = identityColumns.at(-1)?.render as (value: unknown, item: typeof binding) => unknown
    const operationTree = operation(undefined, binding)
    ;(findButton(operationTree, '暂停').props?.onClick as () => void)()
    await ui.modal.confirm.mock.calls.at(-1)?.[0].onOk()
    expect(actions.updateExternalIdentityBindingStatus).toHaveBeenCalledWith('binding-1', 'suspended')
  })

  it('loads tool governance and applies emergency policy changes', async () => {
    resetHooks({
      0: [tool],
      1: ['quality'],
      2: tool,
      3: [{ operation: tool.operation }],
      5: 1,
    })
    const tree = ToolGovernance()
    invokeEffects()
    await vi.waitFor(() => {
      expect(actions.getAgentToolCatalogPage).toHaveBeenCalled()
      expect(actions.getAgentToolCatalog).toHaveBeenCalled()
    })

    const table = walk(tree).find((element) => Array.isArray(element.props?.columns))
    const columns = table?.props?.columns as Array<Record<string, unknown>>
    for (const column of columns) {
      if (typeof column.render === 'function') {
        ;(column.render as (value: unknown, item: typeof tool) => unknown)(
          column.dataIndex === 'write' ? true : column.dataIndex === 'risk_level' ? 'high' : 'active',
          tool,
        )
      }
    }
    const operationTree = (columns.at(-1)?.render as (value: unknown, item: typeof tool) => unknown)(undefined, tool)
    const toggle = walk(operationTree).find((element) => typeof element.props?.onChange === 'function')
    ;(toggle?.props?.onChange as (enabled: boolean) => void)(false)
    await ui.modal.confirm.mock.calls.at(-1)?.[0].onOk()
    expect(actions.setAgentToolEnabled).toHaveBeenCalledWith(tool.operation, false)
  })

  it('loads confirmations, queries grants and revokes remembered access', async () => {
    const grant = {
      id: 'grant-1', user_id: 'user-1', resource: 'doc-1', action: 'write', risk: 'low', created_at: 1,
    }
    resetHooks({ 0: 'user-1', 1: [grant], 2: [{
      id: 'confirmation-1', operation: 'quality.create_deviation', summary: '创建偏差',
      risk_level: 'medium', status: 'pending', expires_at: config.updated_at, created_at: config.updated_at,
    }] })
    actions.getFeishuAuthorizations.mockResolvedValue([grant])
    const tree = AuthorizationConfirmation()
    invokeEffects()
    await vi.waitFor(() => expect(actions.getAgentConfirmations).toHaveBeenCalled())

    const userIdInput = walk(tree).find(
      (element) => element.props?.placeholder === '本地用户编号（UUID）',
    )
    ;(userIdInput?.props?.onChange as (event: { target: { value: string } }) => void)(
      { target: { value: 'user-2' } },
    )
    expect(lifecycle.setters[0]).toHaveBeenCalledWith('user-2')

    await (findButton(tree, '查询授权').props?.onClick as () => Promise<void>)()
    expect(actions.getFeishuAuthorizations).toHaveBeenCalledWith('user-1')

    const tables = walk(tree).filter((element) => Array.isArray(element.props?.columns))
    const grantColumns = tables[0].props?.columns as Array<Record<string, unknown>>
    const actionTree = (grantColumns.at(-1)?.render as (value: unknown, item: typeof grant) => unknown)(undefined, grant)
    ;(findButton(actionTree, '撤销').props?.onClick as () => void)()
    await ui.modal.confirm.mock.calls.at(-1)?.[0].onOk()
    expect(actions.revokeFeishuAuthorization).toHaveBeenCalledWith('grant-1', 'user-1')
  })

  it('loads deliveries, queries trace data and exports safe diagnostics', async () => {
    const trace = {
      trace_id: 'trace-1',
      counts: { messages: 1, tool_calls: 1, confirmations: 1, domain_events: 1, deliveries: 1 },
      timeline: [{
        type: 'tool', id: 'event-1', occurred_at: config.updated_at, status: 'executed',
        summary: '工具执行', error_code: null,
      }],
    }
    resetHooks({ 0: 'failed', 1: [{ id: 'delivery-1', status: 'failed' }], 2: false })
    actions.exportAgentTrace.mockResolvedValue({ filename: 'trace.json', content: '{}' })
    const onQuery = vi.fn().mockResolvedValue(undefined)
    const onTraceIdChange = vi.fn()
    const tree = TraceDelivery({
      traceId: 'trace-1',
      trace,
      onTraceIdChange,
      onQuery,
    })
    invokeEffects()
    await vi.waitFor(() => expect(actions.getAgentDeliveries).toHaveBeenCalledWith('failed'))

    await (findButton(tree, '查询').props?.onClick as () => Promise<void>)()
    await (findButton(tree, '导出安全诊断').props?.onClick as () => Promise<void>)()
    expect(onQuery).toHaveBeenCalledWith('trace-1')
    expect(actions.exportAgentTrace).toHaveBeenCalledWith('trace-1')
    expect(walk(tree).some(
      (element) => element.props?.title === '调用链路（Trace）用于定位故障',
    )).toBe(true)

    const traceInput = walk(tree).find(
      (element) => element.props?.placeholder === '输入调用链路编号或运行编号',
    )
    ;(traceInput?.props?.onChange as (event: { target: { value: string } }) => void)(
      { target: { value: 'trace-2' } },
    )
    expect(onTraceIdChange).toHaveBeenCalledWith('trace-2')

    const list = walk(tree).find((element) => typeof element.props?.renderItem === 'function')
    ;(list?.props?.renderItem as (item: typeof trace.timeline[number]) => unknown)(trace.timeline[0])
    const table = walk(tree).find((element) => Array.isArray(element.props?.columns))
    const columns = table?.props?.columns as Array<Record<string, unknown>>
    const channelColumn = columns.find((column) => column.dataIndex === 'channel')
    expect((channelColumn?.render as (value: string) => unknown)('feishu')).toBeDefined()
    expect((channelColumn?.render as (value: string) => unknown)('custom')).toBeDefined()
    const statusColumn = columns.find(
      (column) => column.dataIndex === 'status',
    )
    ;(statusColumn?.render as (value: string) => unknown)('failed')
    expect((table?.props?.rowKey as (item: { id: number }) => string)({ id: 7 })).toBe('7')
  })
})
