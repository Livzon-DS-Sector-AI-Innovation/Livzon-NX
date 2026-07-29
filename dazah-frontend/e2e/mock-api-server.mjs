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
  module_codes: ['procurement'],
}

const pendingPurchaseRequest = {
  id: '22222222-2222-2222-2222-222222222222',
  category: 'hardware',
  request_department: '工程设备部',
  request_date: '2026-07-29',
  total_amount: '1280.00',
  status: 'pending_department_head',
  items: [],
  approvals: [],
}

const server = createServer((request, response) => {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  const authorization = request.headers.authorization || ''

  if (request.url === '/health') {
    response.end(JSON.stringify({ status: 'ok' }))
    return
  }

  if (request.url?.startsWith('/api/v1/identity/me')) {
    const user = authorization.includes('restricted')
      ? { ...currentUser, module_codes: [] }
      : currentUser
    response.end(JSON.stringify({ code: 200, message: 'success', data: user }))
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
