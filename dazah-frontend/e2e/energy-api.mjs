const states = new Map()
const taskId = 'a1000000-0000-0000-0000-000000000001'
const datasetNames = ['饮用水码', '冰水码', '蒸汽码', '循环水码', '空气码', '电量', '饮用水量', '蒸汽量', '冰水量', '空气量', '循环水量', '日总量', '101车间', '102-1车间', '103-1车间', '103-2车间', '201-1车间', '201-2车间', '203-1车间', '203-2车间', '203-3车间']
function stateFor(token) {
  if (!states.has(token)) states.set(token, { source: null, task: { id: taskId, task_date: '2026-07-02', name: '101能源抄表组', owner_ids: ['00000000-0000-0000-0000-000000000001'], deadline_time: '10:00', total_count: 2, completed_count: 0, items: [
    { id: 'a2000000-0000-0000-0000-000000000001', point_id: 'a3000000-0000-0000-0000-000000000001', name: '101车间水表', category: 'drinking_water', unit: 'm3', precision: 3, multiplier: '1', frequency: 'daily', reading_type: 'counter', reading_date: '2026-07-02', value: null, draft_value: null, previous_value: '100', previous_date: '2026-07-01', version: 0, submitted_at: null },
    { id: 'a2000000-0000-0000-0000-000000000002', point_id: 'a3000000-0000-0000-0000-000000000002', name: '101车间电量', category: 'electricity', unit: 'kWh', precision: 3, multiplier: '1', frequency: 'daily', reading_type: 'direct', reading_date: '2026-07-01', value: null, draft_value: null, previous_value: null, previous_date: null, version: 0, submitted_at: null },
  ] } })
  return states.get(token)
}

export async function handleEnergyRequest(request, response, token) {
  const url = new URL(request.url, 'http://localhost')
  if (!url.pathname.startsWith('/api/v1/energy/')) return false
  const state = stateFor(token)
  const send = (data, status = 200) => { response.statusCode = status; response.end(JSON.stringify({ code: status, data })); return true }
  if (url.pathname.endsWith('/reporting/datasets')) return send(datasetNames.map(name => ({ name, kind: name.endsWith('码') ? 'reading' : name === '电量' ? 'mixed' : 'usage' })))
  if (url.pathname.endsWith('/reporting/metrics')) return send([{ metric_key: 'point:p1', name: '101车间水表', category: 'drinking_water', unit: 'm3' }])
  if (url.pathname.endsWith('/reporting/workbook')) {
    const dataset = url.searchParams.get('dataset')
    const raw = dataset.endsWith('码')
    return send({ year: Number(url.searchParams.get('year')), month: Number(url.searchParams.get('month')), dataset, columns: [{ key: '2', label: '101车间水表', unit: 'm3', value_kind: raw ? 'reading' : 'usage', quantity_kind: 'volume' }], rows: [{ date: '2026-07-01', cells: { '2': { value: raw ? '100' : '10', status: 'complete', provenance: {} } } }], available_count: 1, expected_count: 1 })
  }
  if (url.pathname.endsWith('/e2e-state')) return send(state)
  if (url.pathname.endsWith('/ledger-options')) return send({ is_manager: true, people: [] })
  if (url.pathname.endsWith('/entry-tasks') && request.method === 'GET') return send({ items: [state.task], total: 1 })
  if (url.pathname === `/api/v1/energy/entry-tasks/${taskId}`) return send(state.task)
  if (url.pathname === `/api/v1/energy/entry-tasks/${taskId}/submit`) {
    const chunks = []; for await (const chunk of request) chunks.push(chunk)
    const body = JSON.parse(Buffer.concat(chunks).toString())
    if (body.values.some(item => item.value === '999')) { response.statusCode = 503; response.end(JSON.stringify({ message: '模拟能源服务暂不可用，输入已保留' })); return true }
    if (body.values.some(item => state.task.items.find(row => row.id === item.reading_id)?.version !== item.version)) { response.statusCode = 409; response.end(JSON.stringify({ message: '数据已被其他人修改，请刷新' })); return true }
    for (const item of body.values) {
      const row = state.task.items.find(row => row.id === item.reading_id)
      row.version++
      if (body.draft) row.draft_value = item.value
      else { row.value = item.value; row.draft_value = null; row.submitted_at = new Date().toISOString() }
    }
    state.source = body.source
    state.task.completed_count = state.task.items.filter(item => item.value !== null).length
    return send(state.task)
  }
  if (url.pathname.endsWith('/reporting') || url.pathname.endsWith('/data-quality')) {
    const rows = state.task.items.map((item, index) => ({ id: `a4000000-0000-0000-0000-00000000000${index + 1}`, metric_key: `point:p${index}`, usage_date: '2026-07-01', name: item.name, category: item.category, unit: item.unit, workshop: '101车间', department: '101车间', report_scope: 'detail', quantity_kind: index ? 'electricity' : 'volume', temperature: '', calculated_value: item.value === null ? null : String(Number(item.value) - (index ? 0 : 100)), effective_value: item.value === null ? null : String(Number(item.value) - (index ? 0 : 100)), status: item.value === null ? 'missing_reading' : 'complete', provenance: { reading_dates: ['2026-07-01', '2026-07-02'], reading_values: [item.previous_value, item.value], configuration_version: 1 } }))
    const totals = rows.map(row => ({ category: row.category, unit: row.unit, quantity_kind: row.quantity_kind, temperature: '', value: row.effective_value, expected_count: 1, available_count: row.effective_value === null ? 0 : 1 }))
    const selected = url.pathname.endsWith('/data-quality') ? rows.filter(row => row.effective_value === null) : rows
    return send({ start_date: '2026-07-01', end_date: '2026-07-01', status: state.task.completed_count === 2 ? 'complete' : 'partial', rows: selected, totals, trend: totals.map(row => ({ ...row, usage_date: '2026-07-01' })), distribution: totals.map(row => ({ ...row, workshop: '101车间' })), period_metrics: [], total_count: selected.length, latest_complete_date: state.task.completed_count === 2 ? '2026-07-01' : null, entry_total: 2, entry_completed: state.task.completed_count })
  }
  if (/\/(meter-points|calculation-rules|entry-plans|period-locks|notification-runs|snapshot-options)$/.test(url.pathname)) return send([])
  if (url.pathname.endsWith('/bot-config')) return send({ definition: { app_id: '', base_url: '', enabled: false }, secret_configured: false, version: 0 })
  return false
}
