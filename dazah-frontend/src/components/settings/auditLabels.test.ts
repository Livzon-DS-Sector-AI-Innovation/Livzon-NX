import { describe, expect, it } from 'vitest'
import { auditActionLabel, auditRequestLabel, auditRiskLabel, auditStatusLabel, auditToolLabel } from './auditLabels'

describe('audit presentation labels', () => {
  it('names permission, automation, Feishu and business actions in Chinese', () => {
    expect(auditActionLabel('rbac_user_roles_updated')).toBe('修改用户角色')
    expect(auditActionLabel('list_agent_automation_runs')).toBe('查询自动化运行记录')
    expect(auditActionLabel('base.record.update')).toBe('修改飞书多维表格记录')
    expect(auditActionLabel('production_line_status_set')).toBe('设置生产线状态')
  })

  it('keeps unknown action and request descriptions readable in Chinese', () => {
    expect(auditActionLabel('update_quality_item', 'quality')).toBe('记录质量管理操作')
    expect(auditActionLabel('unknown_event')).toBe('其他已记录操作')
    expect(auditRequestLabel({ operation: 'unknown_agent_query', resource_type: 'agent', method: 'GET' })).toBe('查询智能助手信息')
  })

  it('names tool calls, statuses and risks in Chinese', () => {
    expect(auditToolLabel('quality.list_deviations')).toBe('查询偏差记录')
    expect(auditToolLabel('agent.run_automation')).toBe('立即运行自动化')
    expect(auditToolLabel('quality.unrecognized')).toBe('执行质量管理工具')
    expect(auditStatusLabel('failed')).toBe('失败')
    expect(auditRiskLabel('high')).toBe('高风险')
  })
})
