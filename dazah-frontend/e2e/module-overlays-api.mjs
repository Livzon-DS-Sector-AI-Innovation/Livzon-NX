// Only synthetic overlay sessions use these fixtures; no external system writes.
const writes = new Map()
export function handleModuleOverlays(request, response, token) {
  if (!token.startsWith('module-overlays-')) return false
  const path = new URL(request.url, 'http://localhost').pathname
  let data
  if (path === '/api/v1/quality/__test/module-overlay-writes') data = writes.get(token) || 0
  else if (path === '/api/v1/identity/me') data = {
    id: token, name: '四模块浮层测试管理员', role: 'admin', status: 'active',
    module_codes: ['quality', 'hr', 'warehouse', 'registration'], page_permissions: [], auth_source: 'local',
  }
  else if (!/^\/api\/v1\/(quality|hr|warehouse|registration)\//.test(path)) return false
  else if (request.method !== 'GET') {
    writes.set(token, (writes.get(token) || 0) + 1)
    data = { success: true }
  }
  else if (path.endsWith('/return-application')) data = [{ record_id: 'overlay-return', product_name: '浮层验收退货', batch_number: 'LOCAL-OVERLAY-TEST' }]
  else if (path.endsWith('/person-directory') || path.endsWith('/person-options')) data = [{ open_id: 'overlay-person', id: 'overlay-person', name: '浮层验收联系人', department: '质量保证' }]
  else if (path.endsWith('/feishu/validations')) data = []
  else if (path.endsWith('/dept-mappings')) data = [{
    id: 'overlay-mapping', source_name: 'LOCAL-OVERLAY-TEST'.repeat(8), target_name: '质量保证',
    mapping_type: 'person', match_level: 'both', priority: 1, enabled: true, remark: '仅用于浮层布局验收',
  }]
  else if (path.endsWith('/contracts')) data = { data: [{
    id: 'overlay-contract', employee_number: 'LOCAL-OVERLAY-TEST', name: '浮层验收员工',
    contract_opinion: '同意续签', contract_sequence: '第二次', signed_status: '待签署',
  }], total: 1, page: 1, page_size: 50 }
  else if (path.endsWith('/departments')) data = ['质量保证']
  else if (path.endsWith('/inspection-contacts')) data = [{ id: 'overlay-contact', test_item: '浮层验收项目', agency_name: '本地测试机构', contact_name: '测试联系人' }]
  else if (path.includes('/material-pages/')) {
    if (path.includes('/records/')) data = { record_id: 'overlay-warehouse', fields: [
      { field_name: '物料名称', field_type: 1, value: '浮层验收物料', editable: true },
      { field_name: '备注', field_type: 1, value: 'LOCAL-OVERLAY-TEST'.repeat(20), editable: true },
    ] }
    else if (path.endsWith('/form-links')) data = { inbound_form_url: null, outbound_form_url: null }
    else data = { page_key: 'raw-ledger', page_title: '原辅料出库总账', table_name: '原辅料出库总账',
      columns: [{ key: '物料名称', title: '物料名称', field_type: 1 }, { key: '入库日期', title: '入库日期', field_type: 5 }],
      rows: [{ __record_id: 'overlay-warehouse', 物料名称: '浮层验收物料', 入库日期: '2026-10-19' }],
      total: 1, page: 1, page_size: 50, last_sync_time: '2026-10-19T08:00:00Z', source: 'feishu_bitable',
    }
  }
  else if (path.endsWith('/person-avatar-map')) data = {}
  else data = []
  response.end(JSON.stringify({ code: 200, message: 'success', data, meta: { total: Array.isArray(data) ? data.length : 1 } }))
  return true
}
