// Deterministic overlay fixtures, isolated from other tests by their synthetic token.
const deleted = new Set()
export function handleProductionOverlays(request, response, token) {
  if (!token.startsWith('production-overlays-')) return false
  const path = new URL(request.url, 'http://localhost').pathname
  const row = { id: 'overlay-record', point_id: 'LOCAL-OVERLAY-TEST', area: '其他',
    standard_pressure: 15, pressure_value: 16, record_time: '2026-10-19T08:00:00',
    date: '2026-10-19', status: 'pending', input_type: 'manual', time_slot: '上午',
    time_slot_values: { 上午: 16 } }
  const archive = { id: 'overlay-archive', file_name: 'LOCAL-OVERLAY-TEST.xlsx',
    sheet_name: '排产计划', row_count: 1, col_count: 1, rows: [['本地测试']],
    merges: [], col_widths: [120], created_at: '2026-10-19T08:00:00', created_by_name: '测试用户' }
  let data
  if (path === '/api/v1/identity/me') {
    data = { id: token, name: '浮层测试管理员', role: 'admin', status: 'active',
      module_codes: ['production'], page_permissions: [], auth_source: 'local' }
  } else if (!path.startsWith('/api/v1/production/')) return false
  else if (request.method !== 'GET') {
    deleted.add(`${token}:${path}`)
    data = { success: true, success_count: 1 }
  } else if (path.endsWith('/schedule-excel')) data = deleted.has(`${token}:${path}/overlay-archive`) ? [] : [archive]
  else if (path.endsWith('/schedule-excel/overlay-archive')) data = archive
  else if (path.endsWith('/records/merged') || path.endsWith('/pressure/records') || path.endsWith('/point-mappings')) data = [row]
  else if (path.endsWith('/audit/stats')) data = { pending_count: 1, today_approved_count: 0, rejected_count: 0 }
  else if (path.endsWith('/ai-history')) data = { records: [{ id: 'overlay-history',
    created_at: '2026-10-19T08:00:00', batch_no: 'LOCAL-OVERLAY-TEST', stage: 'refinement',
    stage_label: '精制', severity: 'medium', summary: '本地浮层验收记录，检查窄屏下所有列可横向滚动查看。' }] }
  else if (path.endsWith('/lineage/trace')) data = { stages: [{ stage: path.includes('/mc/') ? 'refinement' : 'fermentation', label: '精制', nodes: [{batch_no: 'LOCAL-OVERLAY-TEST', quantity: 100, yield_rate: 95}] }], target_batch: 'LOCAL-OVERLAY-TEST', target_stage: path.includes('/mc/') ? 'refinement' : 'fermentation' }
  else if (path.endsWith('/yield-distribution') || path.endsWith('/material-reuse') || path.includes('/extraction-records') || path.endsWith('/acidifications') || path.endsWith('/fa/records')) data = []
  else if (path.endsWith('/dr/records/years')) data = [2026]
  else if (path.endsWith('/dr/records')) data = { total: 1, items: [{ fl_batch_no: 'DR-LOCAL', production_date: '2026-10-19',
    refinement_batch_no: 'DR-LOCAL-R1', remarks: '本地验收备注。'.repeat(80) }] }
  else if (path.endsWith('/fermentation-board')) data = {
    period: { start: '2026-09-27', end: '2026-10-26', label: '本地验收周期' },
    now: '2026-10-19T08:00:00', is_current_period: true,
    kpis: { month_planned: 1, month_done_planned: 1, done_with_yield: 1, yield_pending: 0,
      month_done_yield_kg: 100, running: 0, pending: 0 },
    tanks: [], recent: [], dumped_batches: [], extraction_ledger: [], alerts: [], maintenance: [], trend: { batches: [], outputs: [] }, recent_finished: [], }
  else if (path.endsWith('/fermentation-batch-actuals')) data = [{ id: 'overlay-actual', batch_no: 'FA-LOCAL-TEST', tank_no: '302A', dump_date: '2026-10-19', yield_kg: 100 }]
  else data = null
  response.end(JSON.stringify({ code: 200, message: 'success', data, meta: { total: Array.isArray(data) ? data.length : 1 } }))
  return true
}
