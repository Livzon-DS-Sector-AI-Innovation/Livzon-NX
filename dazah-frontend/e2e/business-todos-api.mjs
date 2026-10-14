export const businessTodoGrants = [
  ['quality:deviations:deviation-ledger', 'quality', 'deviations'],
  ['registration:project:declaration-progress:international-planned-in-progress', 'registration', 'validation-audits'],
  ['hr:training:plan-tracking', 'hr', 'plan-tracking'],
  ['hr:position-transfer', 'hr', 'position-transfer'],
]

export function businessTodoUser(base, token) {
  const permissions = token === 'business-todos-readonly' ? ['access', 'query'] : ['access', 'query', 'operate']
  return { ...base, id: '00000000-0000-0000-0000-000000000099', role: 'user', module_codes: ['quality', 'registration', 'hr'],
    page_permission_rollouts: { quality: 'enforced', registration: 'enforced', hr: 'enforced' },
    page_permissions: businessTodoGrants.map(([page_key, module_code]) => ({ page_key, module_code, permissions, sensitive_actions: page_key === 'hr:position-transfer' ? ['approve'] : [], source: 'user', data_scope: { scope_type: module_code === 'registration' ? 'all' : 'departments', department_ids: ['11111111-1111-1111-1111-111111111111'] } })),
  }
}

export function handleBusinessTodos(request, response, token) {
  const url = new URL(request.url || '/', 'http://localhost')
  if (!/^\/api\/v1\/(quality|registration|hr|equipment|safety)\/my-todos$/.test(url.pathname)) return false
  const source = businessTodoGrants.find(([key, module, kind]) => request.headers['x-dazah-page-key'] === key && url.pathname === `/api/v1/${module}/my-todos` && url.searchParams.get('kind') === kind)
  if (token.startsWith('business-todos') && (!source || token === 'business-todos-readonly' || (token === 'business-todos-error' && source[1] === 'quality'))) {
    response.statusCode = 403; response.end(JSON.stringify({ detail: '权限已变化' })); return true
  }
  const moduleCode = source?.[1]
  const title = source?.[2] === 'position-transfer' ? '本人岗位调动审批' : { quality: '本人偏差调查', registration: '本人注册审核', hr: '本人培训跟踪' }[moduleCode]
  response.end(JSON.stringify({ items: title && token.startsWith('business-todos') ? [{ id: `${source[2]}-mine`, title, detail: '待本人处理', due_date: '2026-10-01' }] : [], total: title && token.startsWith('business-todos') ? 1 : 0, page: 1, page_size: 5 }))
  return true
}
