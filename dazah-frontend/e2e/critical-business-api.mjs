const permitId = '31000000-0000-4000-8000-000000000001'
const nodeId = '31000000-0000-4000-8000-000000000002'
const permitsPath = '/api/v1/safety/work-permits'
const certificatesPath = '/api/v1/safety/work-certificates'
const permitsKey = 'safety:ops-safety:work-permits'
const certificatesKey = 'safety:ops-safety:work-certificates'
const assetsKey = 'equipment:assets'

const workshops = [
  { code: '201-1', name: '设备测试一车间', is_enabled: true },
  { code: '201-2', name: '设备测试二车间', is_enabled: true },
  { code: '203', name: '设备受限车间', is_enabled: true },
]
const equipmentNames = { '201-1': '一车间测试真空泵', '201-2': '二车间测试反应釜' }
const emptyEquipmentStats = { total: 0, by_status: {}, by_category: {}, by_location: {} }

const permit = {
  id: permitId, permit_no: 'DH-E2E-001', permit_type: 'hot_work', permit_level: 'grade2',
  status: 'pending_approval', apply_department: '测试车间', work_description: '罐区动火核验', work_location: '测试罐区',
  approval_round: 1, current_node_seq: 1,
  persons: [], risk_identifications: [], safety_measures: [], type_data: {}, relations: [], attachments: [], gas_analyses: [],
  nodes: [{ id: nodeId, round: 1, seq: 1, node_kind: 'approve', node_key: 'review', node_name: '车间审批', status: 'pending' }],
}
const draft = { ...permit, id: '31000000-0000-4000-8000-000000000003', permit_no: 'DH-E2E-002', status: 'draft' }
const certificates = [
  { id: '31000000-0000-4000-8000-000000000004', person_name: '到期证件测试员', certificate_no: 'E2E-CERT-001', certificate_category: '焊接与热切割作业', status: 'expiring', days_to_expiry: 12, files: [] },
  { id: '31000000-0000-4000-8000-000000000005', person_name: '过期证件测试员', certificate_no: 'E2E-CERT-002', certificate_category: '焊接与热切割作业', status: 'expired', days_to_expiry: -5, files: [] },
]
const decisions = new Map()
const decisionAttempts = new Map()

const grant = (moduleCode, pageKey, permissions, extra) => ({
  module_code: moduleCode, page_key: pageKey, permissions, source: 'user', data_scope: { scope_type: 'all' }, ...extra,
})

export async function handleCriticalBusiness(request, response, token, baseUser) {
  const equipment = token.startsWith('critical-equipment-')
  const safety = token.startsWith('critical-safety-')
  if (!equipment && !safety) return false

  const url = new URL(request.url, 'http://localhost')
  const path = url.pathname
  const reply = (data, status = 200, message = 'success', meta) => {
    response.statusCode = status
    response.end(JSON.stringify({ code: status, message, data, meta }))
    return true
  }
  const canReview = token.startsWith('critical-safety-reviewer-')
  const read = ['access', 'query']
  if (path === '/api/v1/identity/me') {
    const moduleCode = equipment ? 'equipment' : 'safety'
    return reply({ ...baseUser, id: token, role: 'user', roles: [], module_codes: [moduleCode],
      page_permission_rollouts: { [moduleCode]: 'enforced' },
      page_permissions: equipment
        ? [grant(moduleCode, assetsKey, read, { visible_sections: ['201-1', '201-2'] })]
        : [grant(moduleCode, permitsKey, canReview ? [...read, 'operate'] : read), grant(moduleCode, certificatesKey, read)],
    })
  }

  if (equipment) {
    if (path === '/api/v1/equipment/workshops') return reply(workshops)
    if (['categories', 'locations', 'departments'].some((resource) => path === `/api/v1/equipment/${resource}`)) return reply([])
    if (path === '/api/v1/equipment/equipments/statistics') {
      return token.startsWith('critical-equipment-partial-')
        ? reply(null, 503, '设备统计暂不可用')
        : reply({ ...emptyEquipmentStats, total: 1, by_status: { 在用: 1 } })
    }
    if (path === '/api/v1/equipment/equipments') {
      const workshop = url.searchParams.get('workshop')
      if (!Object.hasOwn(equipmentNames, workshop)) return reply(null, 403, '当前账号无权查询该车间')
      return reply([{ id: `equipment-${workshop}`, equipment_no: `E2E-${workshop}`,
        name: equipmentNames[workshop], status: '在用', importance: 'B', category_ids: [], location_id: 'test-location',
      }], 200, 'success', { total: 1, page: 1, page_size: 20 })
    }
    return false
  }

  const decision = decisions.get(token)
  const activePermit = decision ? { ...permit, status: decision.status,
    nodes: [{ ...permit.nodes[0], status: decision.status, opinion: decision.opinion, acted_by_name: '测试审批人' }],
  } : permit
  if (path === '/api/v1/safety/__test/permit-decision') {
    return reply({ decision: decision ?? null, attempts: decisionAttempts.get(token) ?? 0 })
  }
  if (path === `${permitsPath}/meta`) return reply({ permit_types: [{ value: 'hot_work', label: '动火作业' }], level_options: {} })
  if (path === `${permitsPath}/stats`) return reply({ total: 2, draft: 1, pending_approval: 1, my_pending_approvals: Number(canReview) })
  if (path === permitsPath) {
    const status = url.searchParams.get('status')
    const items = [activePermit, draft].filter((item) => !status || item.status === status)
    return reply({ items, total: items.length })
  }
  if (path === `${permitsPath}/${permitId}`) return reply(activePermit)
  const actionPath = `${permitsPath}/${permitId}/nodes/${nodeId}/`
  if (request.method === 'POST' && [actionPath + 'approve', actionPath + 'reject'].includes(path)) {
    decisionAttempts.set(token, (decisionAttempts.get(token) ?? 0) + 1)
    if (!canReview) return reply(null, 403, '当前账号无审批权限')
    const chunks = []
    for await (const chunk of request) chunks.push(chunk)
    const { opinion } = JSON.parse(Buffer.concat(chunks).toString('utf8'))
    const reject = path.endsWith('/reject')
    if (reject && !opinion?.trim()) return reply(null, 422, '请填写驳回意见')
    const status = reject ? 'rejected' : 'approved'
    decisions.set(token, { status, opinion, nodeId })
    return reply({ status })
  }
  if (path === `${certificatesPath}/categories`) return reply({ categories: [] })
  if (path === `${certificatesPath}/expiry-summary`) return reply({ total: 2, valid: 0, expiring_in_30d: 1, expired: 1 })
  if (path === certificatesPath) {
    const status = url.searchParams.get('status')
    const items = certificates.filter((item) => !status || item.status === status)
    return reply({ items, total: items.length })
  }
  return false
}
