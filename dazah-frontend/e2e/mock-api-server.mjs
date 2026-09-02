import { createServer } from 'node:http'

const port = Number(process.env.E2E_MOCK_API_PORT || 4100)

const currentUser = {
  id: '00000000-0000-0000-0000-000000000001',
  name: 'CI 测试管理员',
  username: 'ci-admin',
  role: 'admin',
  status: 'active',
  auth_source: 'local',
  email: null,
  mobile: null,
  avatar_url: null,
  employee_no: 'CI-001',
  department: '质量保证',
  position: '测试账号',
  module_codes: [
    'procurement',
    'quality',
    'registration',
    'hr',
    'warehouse',
    'identity',
    'platform',
    'energy',
  ],
}

const pendingPurchaseRequest = {
  id: '22222222-2222-2222-2222-222222222222',
  category: 'hardware',
  request_department: '工程设备部',
  request_date: '2026-07-29',
  total_amount: '1280.00',
  status: 'pending_hardware_warehouse',
  items: [],
  approvals: [],
}

const feishuConfig = {
  id: '10000000-0000-0000-0000-000000000001',
  config_name: 'Livzon 助手飞书设置',
  app_id: 'cli_e2e',
  tenant_id: 'default',
  gateway_enabled: true,
  allowed_group_chat_ids: [],
  require_group_mention: true,
  config_version: 2,
  app_secret_configured: true,
  app_secret_masked: '******',
  is_active: true,
  updated_at: '2026-07-31T09:00:00Z',
  updated_by: '00000000-0000-0000-0000-000000000001',
}

let llmConfigs = [
  {
    id: '30000000-0000-0000-0000-000000000001',
    config_name: '现有测试配置',
    config_type: 'text',
    capabilities: ['text', 'document'],
    api_base_url: 'https://existing.example/v1',
    api_key_masked: '******',
    model_name: 'existing-model',
    temperature: 0,
    timeout_seconds: 120,
    is_active: false,
    notes: '用于端到端测试',
    created_at: '2026-08-19T00:00:00Z',
    updated_at: '2026-08-19T00:00:00Z',
  },
]

function llmDetection(detail = '模型连通正常；已检测到文本和文档能力，模型不接受图片输入') {
  return {
    status: 'ok',
    config_type: 'text',
    capabilities: ['text', 'document'],
    detail,
  }
}

function readJsonBody(request) {
  return new Promise((resolve) => {
    const chunks = []
    request.on('data', (chunk) => chunks.push(chunk))
    request.on('end', () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'))
      } catch {
        resolve({})
      }
    })
  })
}

function v2Event(type, sequence, data, runKey = 'e2e') {
  return [
    `event: ${type}`,
    `data: ${JSON.stringify({
      protocol_version: '2.0',
      event_id: `${runKey}-event-${sequence}`,
      trace_id: `${runKey}-trace`,
      run_id: `${runKey}-run`,
      sequence,
      occurred_at: new Date().toISOString(),
      type,
      data,
    })}`,
    '',
    '',
  ].join('\n')
}

function confirmation(id, summary, expiresInMs = 60_000) {
  return {
    id,
    operation: 'quality.create_deviation',
    summary,
    risk_level: 'medium',
    status: 'pending',
    expires_at: new Date(Date.now() + expiresInMs).toISOString(),
    request_payload: { body: { title: summary } },
  }
}

async function streamAgentReply(request, response) {
  const body = await readJsonBody(request)
  const message = typeof body.message === 'string' ? body.message : ''
  const runKey = `e2e-${Date.now()}`
  const sessionId = typeof body.session_id === 'string' ? body.session_id : 'session-e2e'
  response.statusCode = 200
  response.setHeader('Content-Type', 'text/event-stream; charset=utf-8')
  response.setHeader('Cache-Control', 'no-cache')
  response.write(v2Event('accepted', 1, { session_id: sessionId }, runKey))

  if (message.includes('停止生成测试')) {
    response.write(v2Event('thinking', 2, { status: 'started' }, runKey))
    const heartbeat = setInterval(() => {
      if (!response.destroyed) response.write(': keep-alive\n\n')
    }, 100)
    request.on('close', () => clearInterval(heartbeat))
    return
  }

  if (message.includes('断线恢复测试')) {
    response.write(v2Event('text_delta', 2, { text: '处理中' }, runKey))
    response.end()
    return
  }

  let pendingConfirmations = []
  let answer = '助手关键流程测试完成'
  if (message.includes('多个确认测试')) {
    pendingConfirmations = [
      confirmation('confirmation-first', '创建第一项偏差'),
      confirmation('confirmation-second', '创建第二项偏差'),
    ]
    answer = '已生成两个待确认操作'
  } else if (message.includes('过期确认测试')) {
    pendingConfirmations = [confirmation('confirmation-expiring', '即将过期的操作', 1_500)]
    answer = '确认项将在到期后自动移除'
  } else if (Array.isArray(body.attachments) && body.attachments.length > 0) {
    answer = `已分析 ${body.attachments.length} 个附件`
  }

  response.write(v2Event('capability_search', 2, { status: 'started' }, runKey))
  response.write(v2Event('text_delta', 3, { text: answer }, runKey))
  response.end(v2Event('finished', 4, {
    session_id: sessionId,
    message: { id: `${runKey}-message`, role: 'assistant', content: answer },
    pending_confirmations: pendingConfirmations,
    tool_trace: [],
  }, runKey))
}

const pageBusinessRequests = new Map()
const ledgerLastWrites = new Map()
const ledgerDeleted = new Set()
const server = createServer(async (request, response) => {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  const authorization = request.headers.authorization || ''
  const pageTestToken = authorization.replace('Bearer ', '')
  if (pageTestToken.startsWith('page-') && request.url?.startsWith('/api/v1/procurement/')) {
    pageBusinessRequests.set(pageTestToken, (pageBusinessRequests.get(pageTestToken) || 0) + 1)
  }
  if (pageTestToken.startsWith('ledger-') && request.url?.startsWith('/api/v1/quality/')) {
    pageBusinessRequests.set(pageTestToken, (pageBusinessRequests.get(pageTestToken) || 0) + 1)
  }
  if (request.url?.startsWith('/__test/page-requests?')) {
    const token = new URL(request.url, 'http://localhost').searchParams.get('token')
    response.end(JSON.stringify({ count: pageBusinessRequests.get(token) || 0 }))
    return
  }
  if (request.url?.startsWith('/__test/ledger-write?')) {
    const token = new URL(request.url, 'http://localhost').searchParams.get('token')
    response.end(JSON.stringify(ledgerLastWrites.get(token) || null))
    return
  }

  if (request.url === '/health') {
    response.end(JSON.stringify({ status: 'ok' }))
    return
  }

  if (request.url?.startsWith('/api/v1/identity/me')) {
    if (pageTestToken === 'admin-no-page-grants') {
      response.end(JSON.stringify({ code: 200, data: { ...currentUser,
        module_codes: [], page_permissions: [],
        page_permission_rollouts: { procurement: 'enforced', quality: 'enforced' },
      } }))
      return
    }
    if (pageTestToken.startsWith('ledger-')) {
      const write = ['ledger-create', 'ledger-delete'].includes(pageTestToken)
      const permissions = write ? ['access', 'query', 'operate'] : pageTestToken === 'ledger-query' ? ['access', 'query']
        : pageTestToken === 'ledger-access' ? ['access'] : []
      response.end(JSON.stringify({ code: 200, data: { ...currentUser, role: 'user',
        module_codes: ['quality'], page_permission_rollouts: { quality: 'enforced' },
        page_permissions: [{ page_key: 'quality:deviations:deviation-ledger', module_code: 'quality', permissions,
          sensitive_actions: pageTestToken === 'ledger-delete' ? ['delete'] : [], source: 'user', data_scope: { scope_type: 'all' } }],
      } }))
      return
    }
    if (pageTestToken.startsWith('page-')) {
      const permissions = pageTestToken === 'page-query' ? ['access', 'query']
        : pageTestToken === 'page-access' ? ['access'] : []
      response.end(JSON.stringify({ code: 200, data: { ...currentUser, role: 'user',
        module_codes: ['procurement'], page_permission_rollouts: { procurement: 'enforced' },
        page_permissions: [{ page_key: 'purchasing:supplier', module_code: 'procurement', permissions,
          sensitive_actions: [], source: 'user', data_scope: { scope_type: 'not_applicable' } }],
      } }))
      return
    }
    if (authorization.includes('invalid-session')) {
      response.statusCode = 401
      response.end(JSON.stringify({ code: 401, message: 'authentication required', data: null }))
      return
    }

    const user = authorization.includes('restricted')
      ? { ...currentUser, module_codes: [] }
      : authorization.includes('procurement-only')
        ? { ...currentUser, module_codes: ['procurement'] }
        : currentUser
    response.end(JSON.stringify({ code: 200, message: 'success', data: user }))
    return
  }

  if (pageTestToken.startsWith('ledger-') && request.url?.startsWith('/api/v1/quality/deviations')) {
    if (request.url.includes('/reporter-options')) {
      response.end(JSON.stringify({ code: 200, data: [{ open_id: 'test-reporter', name: '王报告', department: '质量部' }], meta: { total: 1, page: 1, page_size: 50 } }))
      return
    }
    if (request.method === 'POST') {
      const body = await readJsonBody(request)
      ledgerLastWrites.set(pageTestToken, body)
      if (request.url.endsWith('/batch-delete')) {
        ledgerDeleted.add(pageTestToken)
        response.end(JSON.stringify({ code: 200, data: { deleted: body.ids.length, failed: [] } }))
      } else {
        response.end(JSON.stringify({ code: 200, data: { id: '00000000-0000-0000-0000-000000000010', code: 'PC-CREATED' } }))
      }
      return
    }
    if (pageTestToken === 'ledger-delete' && !ledgerDeleted.has(pageTestToken)) {
      response.end(JSON.stringify({ code: 200, data: [{ id: '00000000-0000-0000-0000-000000000011', deviation_code: 'PC-BATCH', title: '测试偏差', status: 'draft' }], meta: { total: 1, page: 1, page_size: 20 } }))
      return
    }
    response.end(JSON.stringify({ code: 200, data: [], meta: { total: 0, page: 1, page_size: 20 } }))
    return
  }

  if (authorization === 'Bearer matrix-admin' && request.url?.startsWith('/api/v1/identity/admin/roles')) {
    if (request.url.endsWith('/page-permissions')) {
      if (request.method === 'PUT') {
        response.statusCode = 409
        response.end(JSON.stringify({ message: '授权版本冲突，请刷新后重试' }))
      } else {
        response.end(JSON.stringify({ code: 200, data: { role_id: 'role-matrix', grant_version: 1, grants: [],
          definitions: [
            ['production', '生产批次'], ['equipment', '设备台账'], ['energy', '能源数据'],
            ['safety', '安全检查'], ['research', '研发项目'], ['registration', '注册项目'],
            ['quality', '偏差记录'], ['administration', '行政管理'], ['hr', '员工管理'],
            ['warehouse', '库存清单'], ['procurement', '采购申请'],
          ].map(([module_code, page_name]) => ({ module_code, page_name, page_key: `${module_code}:test`,
            route_path: `/${module_code}/test`, supported_scope_types: ['not_applicable'], sensitive_actions: module_code === 'production'
              ? [{ key: 'delete', name: '作废生产批次', description: '作废批次记录', category: 'destructive' }] : [] })),
        } }))
      }
    } else {
      response.end(JSON.stringify({ code: 200, data: [{ id: 'role-matrix', name: '页面授权测试角色',
        code: 'matrix_role', is_system: false, permissions: [], grant_version: 1 }] }))
    }
    return
  }

  if (request.url === '/api/v1/llm/configs' && request.method === 'GET') {
    response.end(JSON.stringify(llmConfigs))
    return
  }

  if (request.url === '/api/v1/llm/configs/probe' && request.method === 'POST') {
    const body = await readJsonBody(request)
    if (String(body.api_base_url || '').includes('fail.example')) {
      response.statusCode = 400
      response.end(JSON.stringify({ detail: '模拟连通性失败' }))
      return
    }
    response.end(JSON.stringify({
      ...llmDetection(
        body.probe_type === 'url'
          ? 'API URL 与密钥连通正常'
          : undefined,
      ),
      probe_type: body.probe_type,
    }))
    return
  }

  if (request.url === '/api/v1/llm/configs/test' && request.method === 'POST') {
    if (!llmConfigs.some((config) => config.is_active)) {
      response.statusCode = 404
      response.end(JSON.stringify({ detail: '没有已激活的 LLM 配置' }))
      return
    }
    response.end(JSON.stringify(llmDetection('当前激活模型连接正常')))
    return
  }

  if (request.url === '/api/v1/llm/configs' && request.method === 'POST') {
    const body = await readJsonBody(request)
    if (body.is_active) {
      llmConfigs = llmConfigs.map((config) => ({ ...config, is_active: false }))
    }
    const now = new Date().toISOString()
    const config = {
      ...body,
      id: '30000000-0000-0000-0000-000000000002',
      config_type: 'text',
      capabilities: ['text', 'document'],
      api_key_masked: '******',
      created_at: now,
      updated_at: now,
    }
    delete config.api_key
    llmConfigs.unshift(config)
    response.statusCode = 201
    response.end(JSON.stringify(config))
    return
  }

  const llmConfigMatch = request.url?.match(
    /^\/api\/v1\/llm\/configs\/([^/]+)(\/test)?$/,
  )
  if (llmConfigMatch && request.method === 'POST' && llmConfigMatch[2]) {
    const config = llmConfigs.find((item) => item.id === llmConfigMatch[1])
    if (!config) {
      response.statusCode = 404
      response.end(JSON.stringify({ detail: 'Config not found' }))
      return
    }
    response.end(JSON.stringify(llmDetection('已重新检测模型能力')))
    return
  }

  if (llmConfigMatch && request.method === 'PUT' && !llmConfigMatch[2]) {
    const body = await readJsonBody(request)
    if (body.is_active) {
      llmConfigs = llmConfigs.map((config) => ({ ...config, is_active: false }))
    }
    const index = llmConfigs.findIndex((item) => item.id === llmConfigMatch[1])
    if (index < 0) {
      response.statusCode = 404
      response.end(JSON.stringify({ detail: 'Config not found' }))
      return
    }
    const updated = {
      ...llmConfigs[index],
      ...body,
      updated_at: new Date().toISOString(),
    }
    delete updated.api_key
    llmConfigs[index] = updated
    response.end(JSON.stringify(updated))
    return
  }

  if (llmConfigMatch && request.method === 'DELETE' && !llmConfigMatch[2]) {
    llmConfigs = llmConfigs.filter((item) => item.id !== llmConfigMatch[1])
    response.statusCode = 204
    response.end()
    return
  }

  if (request.url === '/api/v1/agent/chat/stream' && request.method === 'POST') {
    await streamAgentReply(request, response)
    return
  }

  if (request.url?.startsWith('/api/v1/agent/sessions?')) {
    response.end(JSON.stringify({
      code: 200,
      data: {
        items: [{
          id: 'session-history',
          title: '飞书历史会话',
          channel: 'feishu',
          status: 'active',
          message_count: 2,
          pending_confirmation_count: 0,
          last_message_preview: '历史恢复内容',
          created_at: '2026-07-31T08:00:00Z',
          updated_at: '2026-07-31T08:05:00Z',
        }],
        page: 1,
        page_size: 20,
        total: 1,
      },
    }))
    return
  }

  if (request.url === '/api/v1/agent/sessions/session-history') {
    response.end(JSON.stringify({
      code: 200,
      data: {
        session: {
          id: 'session-history',
          title: '飞书历史会话',
          channel: 'feishu',
          status: 'active',
          message_count: 2,
          pending_confirmation_count: 0,
          last_message_preview: '历史恢复内容',
          created_at: '2026-07-31T08:00:00Z',
          updated_at: '2026-07-31T08:05:00Z',
        },
        messages: [
          { id: 'history-user', role: 'user', content: '恢复之前的问题' },
          { id: 'history-assistant', role: 'assistant', content: '历史恢复内容' },
        ],
        confirmations: [],
      },
    }))
    return
  }

  if (
    request.url === '/api/v1/agent/confirmations/confirmation-first/execute'
    && request.method === 'POST'
  ) {
    response.end(JSON.stringify({
      code: 200,
      data: {
        confirmation: {
          ...confirmation('confirmation-first', '创建第一项偏差'),
          status: 'executed',
        },
        result: {
          ok: true,
          operation: 'quality.create_deviation',
          data: {
            pending_confirmation: confirmation(
              'confirmation-followup',
              '确认后续通知',
            ),
          },
          meta: { partial_success: true },
        },
      },
    }))
    return
  }

  if (request.url === '/api/v1/identity/feishu-config/gateway-status') {
    response.end(JSON.stringify({
      code: 200,
      data: {
        configured: true,
        gateway_enabled: true,
        gateway: 'connected',
        config_version: 2,
        credential_version: 2,
        gateway_reconnects: 1,
        event_consumer: 'hermes_native_feishu_gateway',
        event_consumer_count: 1,
        tenant_id: 'default',
      },
    }))
    return
  }

  if (
    request.url === '/api/v1/identity/feishu-config/gateway/restart' &&
    request.method === 'POST'
  ) {
    response.end(JSON.stringify({
      code: 200,
      data: {
        status: 'connected',
        message: 'Hermes 飞书 Gateway 已重新建立连接',
        previous_reconnects: 1,
        gateway_reconnects: 2,
        credential_version: 2,
        config_version: 2,
      },
    }))
    return
  }

  if (
    request.url === '/api/v1/identity/feishu-config' &&
    ['GET', 'PUT'].includes(request.method || '')
  ) {
    response.end(JSON.stringify({ code: 200, data: feishuConfig }))
    return
  }

  if (
    request.url === '/api/v1/identity/feishu-config/test' &&
    request.method === 'POST'
  ) {
    response.end(JSON.stringify({
      code: 200,
      data: {
        status: 'warning',
        message: '飞书接入可用，但同步部门配置需要调整',
        steps: [
          { name: '应用凭证', status: 'ok', message: '凭证有效' },
          {
            name: '诊断目标部门',
            status: 'warning',
            message: '配置的同步根部门 0 不在当前通讯录权限范围内。',
            suggestion: '请将同步根部门改为已授权部门。',
            code: 40004,
          },
        ],
      },
    }))
    return
  }

  if (request.url?.startsWith('/api/v1/identity/users')) {
    response.end(JSON.stringify({
      code: 200,
      data: { items: [currentUser], total: 1, offset: 0, limit: 100 },
    }))
    return
  }

  if (request.url === '/api/v1/identity/external-identity-bindings/conflicts') {
    response.end(JSON.stringify({ code: 200, data: [] }))
    return
  }

  if (request.url?.startsWith('/api/v1/identity/external-identity-bindings')) {
    response.end(JSON.stringify({
      code: 200,
      data: { items: [], page: 1, page_size: 20, total: 0 },
    }))
    return
  }

  if (request.url === '/api/v1/identity/sync/all' && request.method === 'POST') {
    response.end(JSON.stringify({
      code: 200,
      data: {
        status: 'ok',
        message: '同步完成：部门 1 个，部门用户 1 名，直接授权用户 0 名。',
        bindings: { created: 1, existing: 0, conflicts: [] },
      },
    }))
    return
  }

  if (request.url?.startsWith('/api/v1/identity/feishu-config/authorizations')) {
    response.end(JSON.stringify({ code: 200, data: { items: [] } }))
    return
  }

  if (request.url?.startsWith('/api/v1/agent/control/tools/page')) {
    response.end(JSON.stringify({
      code: 200,
      data: {
        items: [{
          operation: 'quality.get_deviation',
          module: 'quality',
          version: '1',
          summary: '查询偏差',
          status: 'active',
          risk_level: 'low',
          write: false,
          confirmation_required: false,
          permission_key: 'quality.deviation.read',
          input_schema: {},
          output_schema: {
            'x-dazah-schema-source': 'return_annotation',
            type: 'object',
            additionalProperties: true,
          },
          timeout_seconds: 30,
          idempotent: true,
        }],
        page: 1,
        page_size: 20,
        total: 1,
      },
    }))
    return
  }

  if (request.url === '/api/v1/agent/control/tools') {
    response.end(JSON.stringify({
      code: 200,
      data: [
        { operation: 'energy.read', module: 'energy' },
        { operation: 'procurement.read', module: 'procurement' },
        { operation: 'quality.get_deviation', module: 'quality' },
        { operation: 'warehouse.read', module: 'warehouse' },
        { operation: 'agent.read', module: null },
      ],
    }))
    return
  }

  if (request.url?.startsWith('/api/v1/agent/control/confirmations')) {
    response.end(JSON.stringify({
      code: 200,
      data: { items: [], page: 1, page_size: 20, total: 0 },
    }))
    return
  }

  if (request.url?.startsWith('/api/v1/agent/push-deliveries')) {
    response.end(JSON.stringify({
      code: 200,
      data: { items: [], page: 1, page_size: 50, total: 0 },
    }))
    return
  }

  if (request.url === '/api/v1/agent/operations/health') {
    response.end(JSON.stringify({
      code: 200,
      data: { status: 'healthy', delivery_statuses: {} },
    }))
    return
  }

  if (request.url === '/api/v1/agent/control/runtime-overview') {
    response.end(JSON.stringify({
      code: 200,
      data: {
        pending_confirmations: 0,
        failed_deliveries: 0,
        latest_error_trace_id: '00000000-0000-0000-0000-000000000099',
        latest_error_at: '2026-07-31T09:00:00Z',
      },
    }))
    return
  }

  if (request.url === '/api/v1/agent/control/traces/00000000-0000-0000-0000-000000000099') {
    response.end(JSON.stringify({
      code: 200,
      data: {
        trace_id: '00000000-0000-0000-0000-000000000099',
        counts: {
          messages: 2,
          tool_calls: 1,
          confirmations: 0,
          domain_events: 0,
          deliveries: 0,
          capability_searches: 1,
          audit_receipts: 1,
        },
        timeline: [
          {
            type: 'inbound_message',
            id: 'event-1',
            occurred_at: '2026-07-31T09:00:00Z',
            status: 'recorded',
            summary: '飞书入站消息（正文已隐藏）',
            error_code: null,
          },
          {
            type: 'capability_search',
            id: 'capability-search-e2e',
            occurred_at: new Date().toISOString(),
            status: 'recorded',
            summary: 'search_agent_tools',
            operation: null,
            error_code: null,
          },
          {
            type: 'audit_receipt',
            id: 'audit-receipt-e2e',
            occurred_at: new Date().toISOString(),
            status: 'recorded',
            summary: 'docs +update',
            operation: 'docs +update',
            error_code: null,
          },
        ],
      },
    }))
    return
  }

  if (request.url === '/api/v1/agent/control/traces/00000000-0000-0000-0000-000000000099/export') {
    response.setHeader('Content-Disposition', 'attachment; filename="livzon-trace-e2e.json"')
    response.end(JSON.stringify({
      schema_version: '1.0',
      content_policy: 'metadata_only_no_business_body_or_credentials',
      trace: { trace_id: '00000000-0000-0000-0000-000000000099' },
      verification: { sha256: 'e2e' },
    }))
    return
  }

  if (request.url === '/api/v1/agent/automation-capability-impacts') {
    response.end(JSON.stringify({ code: 200, data: [] }))
    return
  }

  if (
    request.method === 'POST' &&
    request.url?.match(/\/api\/v1\/procurement\/purchase-requests\/.+\/(approve|reject)$/)
  ) {
    response.statusCode = 503
    response.end(
      JSON.stringify({
        code: 503,
        message: '模拟审批服务暂时不可用',
        data: null,
      }),
    )
    return
  }

  if (request.url?.startsWith('/api/v1/procurement/purchase-requests')) {
    response.end(
      JSON.stringify({
        code: 200,
        message: 'success',
        data: [pendingPurchaseRequest],
        meta: { page: 1, page_size: 20, total: 1 },
      }),
    )
    return
  }

  response.end(
    JSON.stringify({
      code: 200,
      message: 'success',
      data: [],
      meta: { page: 1, page_size: 20, total: 0 },
    }),
  )
})

server.listen(port, '127.0.0.1', () => {
  console.warn(`E2E mock API listening on http://127.0.0.1:${port}`)
})

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => server.close(() => process.exit(0)))
}
