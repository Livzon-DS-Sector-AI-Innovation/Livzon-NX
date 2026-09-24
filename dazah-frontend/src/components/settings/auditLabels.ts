/** Audit labels are presentation only. Keep raw identifiers in the detail view. */
export const auditModuleLabels: Record<string, string> = {
  administration: '行政管理', agent: '智能助手', audit: '审计日志', dossier_writer: '申报资料撰写',
  energy: '能源管理', environment: '环保管理', equipment: '设备管理', hr: '人事管理',
  identity: '身份与权限', llm: '模型配置', procurement: '采购管理', product: '产品管理',
  production: '生产管理', quality: '质量管理', registration: '注册管理',
  regulatory_tracker: '法规追踪', research: '研发管理', safety: '安全管理',
  storage: '文件存储', system: '系统管理', warehouse: '仓储管理',
}

const actionLabels: Record<string, string> = {
  platform_api_request: '访问平台接口',
  replace_user_module_permissions: '修改用户模块权限',
  view_user_module_permissions: '查看用户模块权限',
  view_user_page_permissions: '查看用户页面权限',
  view_user_permission_audit: '查看权限审计',
  replace_user_page_permissions: '修改用户页面权限',
  replace_role_page_permissions: '修改角色页面权限',
  rollback_user_page_permissions: '回退用户页面权限',
  rollback_role_page_permissions: '回退角色页面权限',
  update_user_authorization_context: '更新用户授权范围',
  view_user_livzon_access_scope: '查看用户智能助手访问范围',
  sync_user_livzon_access_scope: '同步用户智能助手访问范围',
  view_own_agent_access_scope: '查看本人智能助手访问范围',
  create_external_identity_binding: '创建外部身份绑定',
  update_external_identity_binding_status: '修改外部身份绑定状态',
  rbac_data_scope_deleted: '删除数据权限范围',
  rbac_data_scope_updated: '修改数据权限范围',
  rbac_department_role_rule_created: '创建部门角色规则',
  rbac_department_role_rule_deleted: '删除部门角色规则',
  rbac_menu_created: '创建菜单',
  rbac_menu_deleted: '删除菜单',
  rbac_menu_updated: '修改菜单',
  rbac_role_created: '创建角色',
  rbac_role_deleted: '删除角色',
  rbac_role_updated: '修改角色',
  rbac_role_menus_updated: '修改角色菜单',
  rbac_role_permissions_updated: '修改角色权限',
  rbac_user_role_removed: '移除用户角色',
  rbac_user_roles_updated: '修改用户角色',
  agent_tool_execute: '执行智能助手工具',
  agent_tool_reject: '拒绝智能助手工具',
  agent_tool_confirm: '确认智能助手工具',
  search_agent_tools: '搜索智能助手工具',
  describe_agent_tool: '查看智能助手工具说明',
  set_agent_tool_enabled: '修改智能助手工具启用状态',
  export_agent_trace_diagnostic: '导出智能助手诊断记录',
  list_agent_automations: '查询自动化列表',
  view_agent_automation: '查看自动化详情',
  list_agent_automation_versions: '查询自动化版本',
  list_agent_automation_audit: '查询自动化修改记录',
  list_agent_automation_runs: '查询自动化运行记录',
  view_agent_automation_run: '查看自动化运行详情',
  list_agent_automation_run_events: '查询自动化运行事件',
  list_agent_scheduled_triggers: '查询自动化定时触发',
  simulate_agent_automation_schedule: '预览自动化执行计划',
  list_agent_automation_capability_impacts: '查询自动化能力影响',
  list_agent_domain_events: '查询智能助手关联事件',
  list_agent_push_deliveries: '查询智能助手推送记录',
  view_agent_push_delivery: '查看智能助手推送详情',
  list_automation_templates: '查询自动化模板',
  view_automation_health: '查看自动化健康状态',
  view_automation_suggestions: '查看自动化建议',
  view_automation_trends: '查看自动化趋势',
  view_operations_report: '查看自动化运行报告',
  list_agent_conversation_audit: '查询智能助手对话审计',
  view_agent_conversation_audit: '查看智能助手对话审计详情',
  feishu_card_action_callback: '处理飞书卡片操作回调',
  feishu_record_created: '创建飞书记录',
  feishu_record_updated: '修改飞书记录',
  feishu_record_deleted: '删除飞书记录',
  restart_livzon_feishu_gateway: '重启智能助手飞书连接',
  sync_livzon_feishu_directory: '同步智能助手飞书通讯录',
  sync_user_management_feishu_directory: '同步用户管理飞书通讯录',
  incremental_sync_requested: '请求飞书资源增量同步',
  'base.record.get': '查看飞书多维表格记录',
  'base.record.list': '查询飞书多维表格记录',
  'base.record.create': '创建飞书多维表格记录',
  'base.record.update': '修改飞书多维表格记录',
  'base.record.delete': '删除飞书多维表格记录',
  procurement_material_source_config_updated: '修改采购物料来源配置',
  procurement_material_source_synced: '同步采购物料来源',
  production_line_status_set: '设置生产线状态',
  schedule_excel_history_fix: '修正排产表历史记录',
  'validation_review.delete': '删除验证审核记录',
  'validation_review.rerun': '重新执行验证审核',
  approve: '批准业务记录', reject: '驳回业务记录',
  start: '启动业务流程', close: '关闭业务流程', complete: '完成业务流程',
  create: '创建业务记录', update: '修改业务记录', delete: '删除业务记录',
  inserted: '新增业务记录', updated: '更新业务记录', unchanged: '确认记录未变更',
  bulk_import: '批量导入业务记录', sensitive_export: '导出敏感数据',
  clear: '清除业务数据', forget: '删除个人记忆', sync_config: '同步配置',
  store_true: '启用配置',
}

const legacyRequestLabels: Record<string, string> = {
  list_automations: '查询自动化列表',
  list_interaction_requests: '查询交互请求列表',
  list_skills: '查询技能列表',
  get_control_plane_runtime_overview: '查看控制平面运行概况',
}

const agentToolLabels: Record<string, string> = {
  'agent.list_automations': '查询自动化列表',
  'agent.get_automation': '查看自动化详情',
  'agent.list_automation_audit': '查看自动化版本与修改记录',
  'agent.list_automation_runs': '查询自动化运行记录',
  'agent.get_automation_run': '查看自动化运行与步骤',
  'agent.run_automation': '立即运行自动化',
  'agent.retry_automation_run': '重试失败的自动化运行',
  'agent.create_automation': '创建自动化流程',
  'agent.create_scheduled_task': '创建定时任务',
  'agent.create_automation_draft': '创建自动化草案',
  'agent.update_automation': '修改自动化定义',
  'agent.confirm_automation': '确认并启用自动化',
  'agent.set_automation_enabled': '启用或暂停自动化',
  'agent.archive_automation': '归档自动化',
  'agent.list_push_deliveries': '查询飞书自动化推送',
  'agent.get_push_delivery': '查看飞书自动化推送',
  'agent.get_my_access_scope': '查询本人智能助手访问范围',
}

const toolObjects: Record<string, string> = {
  deviations: '偏差记录', deviation: '偏差记录',
  capas: '纠正预防措施', capa: '纠正预防措施',
  changes: '变更记录', change: '变更记录',
  validations: '验证记录', validation: '验证记录',
  inspection_records: '检验记录',
  oos_oot_records: '超标与超趋势记录',
  purchase_requests: '采购申请', purchase_request: '采购申请',
  purchase_orders: '采购订单',
  suppliers: '供应商',
  raw_materials: '原辅料', packaging_materials: '包装材料',
  products: '产品',
  automation_runs: '自动化运行记录', automations: '自动化',
  feishu_tables: '飞书表格',
  current_time: '当前时间',
}

const toolVerbs: Array<[string, string]> = [
  ['auto_fill_', '自动填充'], ['resubmit_', '重新提交'], ['submit_', '提交'],
  ['approve_', '批准'], ['reject_', '驳回'], ['create_', '创建'],
  ['update_', '修改'], ['delete_', '删除'], ['archive_', '归档'],
  ['complete_', '完成'], ['list_', '查询'], ['get_', '查看'],
  ['search_', '搜索'], ['export_', '导出'], ['import_', '导入'],
  ['sync_', '同步'], ['pull_', '拉取'], ['run_', '运行'],
  ['retry_', '重试'], ['preview_', '预览'], ['validate_', '校验'],
  ['generate_', '生成'], ['send_', '发送'], ['trigger_', '触发'],
  ['set_', '设置'], ['add_', '添加'], ['link_', '关联'],
]

const hasChinese = (value: string) => /[\u3400-\u9fff]/u.test(value)

export function auditActionLabel(action: string, resourceType?: string | null): string {
  const value = action?.trim() || ''
  if (!value) return '未记录操作'
  if (actionLabels[value]) return actionLabels[value]
  if (hasChinese(value)) return value
  if (value.includes('.')) return auditToolLabel(value)
  const moduleName = resourceType && auditModuleLabels[resourceType]
  return moduleName ? `记录${moduleName}操作` : '其他已记录操作'
}

export function auditRequestLabel(record: {
  operation?: string | null
  resource_type?: string | null
  method?: string | null
}): string {
  const operation = record.operation?.trim() || ''
  if (legacyRequestLabels[operation]) return legacyRequestLabels[operation]
  if (operation && hasChinese(operation)) return operation
  const moduleName = record.resource_type && auditModuleLabels[record.resource_type] || '系统'
  switch (record.method) {
    case 'GET': return `查询${moduleName}信息`
    case 'POST': return `执行${moduleName}操作`
    case 'PUT':
    case 'PATCH': return `修改${moduleName}信息`
    case 'DELETE': return `删除${moduleName}记录`
    default: return `访问${moduleName}接口`
  }
}

export function auditToolLabel(operation: string, summary?: string | null): string {
  if (summary && hasChinese(summary)) return summary
  const value = operation?.trim() || ''
  if (!value) return '未记录工具操作'
  if (agentToolLabels[value]) return agentToolLabels[value]
  if (hasChinese(value)) return value
  const [module, action] = value.split('.', 2)
  const moduleName = auditModuleLabels[module]
  if (!moduleName || !action) return '其他工具操作'
  const verb = toolVerbs.find(([prefix]) => action.startsWith(prefix))
  if (!verb) return `执行${moduleName}工具`
  const object = toolObjects[action.slice(verb[0].length)] || `${moduleName}数据`
  return `${verb[1]}${object}`
}

export function auditStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: '进行中', archived: '已归档', completed: '已完成', started: '执行中',
    success: '成功', succeeded: '成功', executed: '已执行', processed: '已处理',
    pending: '待确认', cancelled: '已取消', rejected: '已拒绝', denied: '已阻止',
    failed: '失败', draft: '草稿', enabled: '已启用', disabled: '已禁用',
    paused: '已暂停', waiting: '等待中', queued: '排队中', running: '运行中',
    sent: '已发送', delivered: '已送达', interacted: '已交互',
  }
  return labels[status] || (hasChinese(status) ? status : '其他状态')
}

export function auditRiskLabel(risk: string): string {
  return ({ low: '低风险', medium: '中风险', high: '高风险', critical: '极高风险' } as Record<string, string>)[risk]
    || (hasChinese(risk) ? risk : '未分类风险')
}
