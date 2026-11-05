'use client'

import { useEffect, useState, useCallback } from 'react'
import { App, Drawer, Descriptions, Table, Tabs, Tag, Space, Empty, Spin } from 'antd'
import { ToolOutlined, SearchOutlined, CalendarOutlined, HeartOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { Equipment, MaintenancePlan, WorkOrder, EquipmentHealth, RepairProfile, HealthGrade } from '@/types/equipment'
import type { InspectionFeishuRecord } from '@/types/inspection-feishu'
import { fetchMaintenancePlansClient, fetchWorkOrdersClient, fetchEquipmentHealthClient, fetchRepairProfileClient } from '@/lib/api/equipment-client'
import { fetchInspectionFeishuRecords } from '@/lib/api/inspection-feishu'
import { monoFont, pillNeutral, pillSuccess, pillWarning, pillError, pillInfo, pillPurple, statusPill } from '@/components/equipment/shared-styles'
import type { EquipmentStatus, EquipmentImportance } from '@/types/equipment'

interface EquipmentDetailDrawerProps {
  open: boolean
  equipment: Equipment | null
  categoryName: string
  locationName: string
  onClose: () => void
}

const MAINTENANCE_STATUS_MAP: Record<string, { color: string; bg: string }> = {
  '启用': { color: '#1aae39', bg: '#d9f3e1' },
  '停用': { color: '#787671', bg: '#f0eeec' },
  '已完成': { color: '#0075de', bg: '#dcecfa' },
}

const WORK_ORDER_STATUS_MAP: Record<string, { color: string; bg: string }> = {
  '待处理': { color: '#dd5b00', bg: '#ffe8d4' },
  '执行中': { color: '#7b3ff2', bg: '#e6e0f5' },
  '待验收': { color: '#0075de', bg: '#dcecfa' },
  '已完成': { color: '#1aae39', bg: '#d9f3e1' },
  '已关闭': { color: '#787671', bg: '#f0eeec' },
}

const TASK_STATUS_MAP: Record<string, { color: string; bg: string }> = {
  '待执行': { color: '#0075de', bg: '#dcecfa' },
  '执行中': { color: '#dd5b00', bg: '#ffe8d4' },
  '已完成': { color: '#1aae39', bg: '#d9f3e1' },
  '已关闭': { color: '#787671', bg: '#f0eeec' },
}

function localStatusPill(color: string, bg: string): React.CSSProperties {
  return { display: 'inline-flex', alignItems: 'center', padding: '2px 10px', borderRadius: 4, fontSize: 12, fontWeight: 600, lineHeight: '20px', color, background: bg }
}

const EQUIP_STATUS_MAP: Record<EquipmentStatus, React.CSSProperties> = {
  '在用': statusPill('#1aae39', '#d9f3e1'),
  '备用': statusPill('#0075de', '#dcecfa'),
  '维修中': statusPill('#dd5b00', '#ffe8d4'),
  '停用': statusPill('#787671', '#f0eeec'),
  '报废': statusPill('#e03131', '#fde0ec'),
}

const IMPORTANCE_MAP: Record<EquipmentImportance, React.CSSProperties> = {
  '高': pillPurple,
  '中': pillNeutral,
  '低': pillNeutral,
}

const HEALTH_GRADE_MAP: Record<HealthGrade, { label: string; style: React.CSSProperties }> = {
  G: { label: '绿档', style: statusPill('#1aae39', '#d9f3e1') },
  Y: { label: '黄档', style: statusPill('#dd5b00', '#ffe8d4') },
  R: { label: '红档', style: statusPill('#e03131', '#fde0ec') },
}

export function EquipmentDetailDrawer({ open, equipment, categoryName, locationName, onClose }: EquipmentDetailDrawerProps) {
  const { message } = App.useApp()
  const [activeTab, setActiveTab] = useState<'plans' | 'history' | 'orders' | 'health'>('plans')

  // 维护保养计划
  const [plans, setPlans] = useState<MaintenancePlan[]>([])
  const [plansLoading, setPlansLoading] = useState(false)

  // 巡检记录
  const [history, setHistory] = useState<InspectionFeishuRecord[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  // 维修工单
  const [orders, setOrders] = useState<WorkOrder[]>([])
  const [ordersLoading, setOrdersLoading] = useState(false)

  // 健康档案
  const [health, setHealth] = useState<EquipmentHealth | null>(null)
  const [profile, setProfile] = useState<RepairProfile | null>(null)
  const [healthLoading, setHealthLoading] = useState(false)

  const loadPlans = useCallback(async () => {
    if (!equipment) return
    setPlansLoading(true)
    try {
      const result = await fetchMaintenancePlansClient({ equipment_id: equipment.id, page: 1, page_size: 50 })
      setPlans(result.items)
    } catch {
      message.error('加载维护保养计划失败')
    } finally {
      setPlansLoading(false)
    }
  }, [equipment, message])

  const loadHistory = useCallback(async () => {
    if (!equipment) return
    setHistoryLoading(true)
    try {
      // 巡检记录以飞书多维表格镜像为准，按设备编号匹配
      const result = await fetchInspectionFeishuRecords({
        keyword: equipment.equipment_no || equipment.name || undefined,
        page: 1,
        page_size: 50,
      })
      setHistory(result.items)
    } catch {
      message.error('加载巡检记录失败')
    } finally {
      setHistoryLoading(false)
    }
  }, [equipment, message])

  const loadOrders = useCallback(async () => {
    if (!equipment) return
    setOrdersLoading(true)
    try {
      const result = await fetchWorkOrdersClient({ equipment_id: equipment.id, page: 1, page_size: 50 })
      setOrders(result.items)
    } catch {
      message.error('加载维修工单失败')
    } finally {
      setOrdersLoading(false)
    }
  }, [equipment, message])

  // 健康档案：所有 setState 都在首个 await 之后（避免 effect 内同步 setState）
  const loadHealth = useCallback(async () => {
    if (!equipment) return
    const [h, p] = await Promise.all([
      fetchEquipmentHealthClient(equipment.id).catch(() => null),
      fetchRepairProfileClient(equipment.id).catch(() => null),
    ])
    setHealth(h)
    setProfile(p)
    setHealthLoading(false)
  }, [equipment])

  useEffect(() => {
    if (open && equipment) {
      loadPlans()
      loadHistory()
      loadOrders()
      loadHealth()
      setActiveTab('plans')
    }
  }, [open, equipment, loadPlans, loadHistory, loadOrders, loadHealth])

  // ── 维护保养计划列 ──
  const planColumns: ColumnsType<MaintenancePlan> = [
    { title: '计划名称', dataIndex: 'plan_name', key: 'plan_name', width: 150, ellipsis: true },
    {
      title: '类型', dataIndex: 'plan_type', key: 'plan_type', width: 100,
      render: (t: string) => <Tag>{t}</Tag>,
    },
    {
      title: '周期', key: 'frequency', width: 100,
      render: (_: unknown, r: MaintenancePlan) => `${r.frequency}${r.frequency_unit}`,
    },
    { title: '上次维护', dataIndex: 'last_maintenance_date', key: 'last_maintenance_date', width: 110, render: (d: string | null) => d || '-' },
    { title: '下次维护', dataIndex: 'next_maintenance_date', key: 'next_maintenance_date', width: 110, render: (d: string | null) => d || '-' },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (s: string) => {
        const m = MAINTENANCE_STATUS_MAP[s] || { color: '#787671', bg: '#f0eeec' }
        return <span style={localStatusPill(m.color, m.bg)}>{s}</span>
      },
    },
  ]

  // ── 巡检记录列（飞书镜像）──
  const AM_PM_KEYS = [
    'am_clean', 'am_lubrication', 'am_fastening', 'am_sealing',
    'am_vibration', 'am_sound', 'am_surface',
    'pm_clean', 'pm_lubrication', 'pm_fastening', 'pm_sealing',
    'pm_vibration', 'pm_sound', 'pm_surface',
  ] as const
  const historyColumns: ColumnsType<InspectionFeishuRecord> = [
    { title: '日期', dataIndex: 'record_date', key: 'record_date', width: 100, render: (d: string | null) => d || '-' },
    {
      title: '上午/下午检查', key: 'checks', width: 120,
      render: (_: unknown, r: InspectionFeishuRecord) => {
        const values = AM_PM_KEYS.map((k) => r[k])
        const ok = values.filter((v) => v === '√').length
        const bad = values.filter((v) => v === '×').length
        if (ok + bad === 0) return <span style={{ color: '#a4a097' }}>未填写</span>
        return (
          <span>
            <span style={{ color: '#1aae39' }}>√{ok}</span>
            {' / '}
            <span style={{ color: bad > 0 ? '#c0392b' : '#a4a097' }}>×{bad}</span>
            {' / 14'}
          </span>
        )
      },
    },
    { title: '来源', dataIndex: 'source', key: 'source', width: 80, render: (s: string) => (s === 'today' ? '今日巡检' : '历史记录') },
    {
      title: '结果', key: 'result', width: 75,
      render: (_: unknown, r: InspectionFeishuRecord) => (
        r.has_abnormal
          ? <span style={pillError}>异常</span>
          : <span style={pillSuccess}>正常</span>
      ),
    },
    {
      title: '异常情况', dataIndex: 'anomaly_note', key: 'anomaly_note', width: 170, ellipsis: true,
      render: (v: string | null) => v || '-',
    },
  ]

  // ── 维修工单列 ──
  const orderColumns: ColumnsType<WorkOrder> = [
    {
      title: '工单编号', dataIndex: 'work_order_no', key: 'work_order_no', width: 170,
      render: (no: string) => <span style={monoFont}>{no}</span>,
    },
    {
      title: '类型', dataIndex: 'order_type', key: 'order_type', width: 90,
      render: (t: string) => <Tag>{t}</Tag>,
    },
    {
      title: '优先级', dataIndex: 'priority', key: 'priority', width: 70,
      render: (p: string) => {
        const cmap: Record<string, React.CSSProperties> = { '紧急': { color: '#e03131', fontWeight: 600 }, '高': { color: '#dd5b00', fontWeight: 600 } }
        return <span style={{ fontSize: 13, ...cmap[p] }}>{p}</span>
      },
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (s: string) => {
        const m = WORK_ORDER_STATUS_MAP[s] || { color: '#787671', bg: '#f0eeec' }
        return <span style={localStatusPill(m.color, m.bg)}>{s}</span>
      },
    },
    { title: '报修人', dataIndex: 'reporter_name', key: 'reporter_name', width: 80, render: (n: string | undefined) => n || '-' },
    { title: '维修人', dataIndex: 'assignee_name', key: 'assignee_name', width: 80, render: (n: string | undefined) => n || '-' },
    { title: '报修时间', dataIndex: 'reported_at', key: 'reported_at', width: 100, render: (d: string) => d?.slice(0, 10) || '-' },
  ]

  // ── 健康档案内容 ──
  const latestSnapshot = health?.latest ?? null
  const latestMetrics = (latestSnapshot?.metrics ?? null) as Record<string, number | null> | null
  const healthTab = (
    <Spin spinning={healthLoading}>
      {!latestSnapshot && !profile ? (
        <Empty description="暂无健康快照（每日 03:30 自动生成）" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {latestSnapshot && (
            <div>
              <h4 style={{ fontSize: 13, fontWeight: 600, margin: '0 0 8px 0' }}>健康评分</h4>
              <Space size={12} align="center" wrap>
                <span style={{ fontSize: 26, fontWeight: 700, lineHeight: 1 }}>
                  {Math.round(latestSnapshot.score)}
                </span>
                <span style={HEALTH_GRADE_MAP[latestSnapshot.grade]?.style ?? pillNeutral}>
                  {HEALTH_GRADE_MAP[latestSnapshot.grade]?.label ?? latestSnapshot.grade}
                </span>
                <span style={{ color: '#8a867d', fontSize: 12 }}>
                  快照日期 {latestSnapshot.snapshot_date}
                </span>
              </Space>
              <Descriptions
                bordered
                size="small"
                column={3}
                style={{ marginTop: 12 }}
                styles={{ label: { fontWeight: 500, width: 110 } }}
              >
                <Descriptions.Item label="近90天故障">
                  {latestMetrics?.fault_count_90d ?? '-'} 次
                </Descriptions.Item>
                <Descriptions.Item label="平均修复时长">
                  {latestMetrics?.mttr_min_90d != null ? `${latestMetrics.mttr_min_90d} 分钟` : '暂无'}
                </Descriptions.Item>
                <Descriptions.Item label="重复故障(90天)">
                  {latestMetrics?.max_repeat_fault_90d ?? 0} 次
                </Descriptions.Item>
                <Descriptions.Item label="超期保养">
                  <span style={{ color: (latestMetrics?.overdue_maintenance_count ?? 0) > 0 ? '#c0392b' : undefined }}>
                    {latestMetrics?.overdue_maintenance_count ?? 0} 项
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="超期校准">
                  <span style={{ color: (latestMetrics?.overdue_calibration_count ?? 0) > 0 ? '#c0392b' : undefined }}>
                    {latestMetrics?.overdue_calibration_count ?? 0} 项
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="趋势">
                  {(health?.snapshots ?? []).length > 1
                    ? health!.snapshots.slice(-7).map((s) => Math.round(s.score)).join(' → ')
                    : '首个快照'}
                </Descriptions.Item>
              </Descriptions>
            </div>
          )}
          {profile && (
            <div>
              <h4 style={{ fontSize: 13, fontWeight: 600, margin: '0 0 8px 0' }}>维修病历</h4>
              <Descriptions bordered size="small" column={3} styles={{ label: { fontWeight: 500, width: 110 } }}>
                <Descriptions.Item label="累计工单">{profile.total_orders} 单</Descriptions.Item>
                <Descriptions.Item label="累计故障维修">{profile.total_faults} 次</Descriptions.Item>
                <Descriptions.Item label="累计维修用时">
                  {Math.round(profile.total_downtime_min / 60)} 小时
                </Descriptions.Item>
                <Descriptions.Item label="累计备件费用">
                  ¥{Number(profile.total_spare_cost ?? 0).toLocaleString()}
                </Descriptions.Item>
                <Descriptions.Item label="平均故障间隔">
                  {profile.mtbf_days != null ? `${profile.mtbf_days} 天` : '暂无'}
                </Descriptions.Item>
                <Descriptions.Item label="病历更新">
                  {profile.updated_at?.slice(0, 10) ?? '-'}
                </Descriptions.Item>
              </Descriptions>
              {(profile.last_3_faults ?? []).length > 0 && (
                <div style={{ marginTop: 8 }}>
                  {profile!.last_3_faults!.map((f) => (
                    <div key={f.work_order_no} style={{ fontSize: 12, color: '#5d5b54', padding: '2px 0' }}>
                      <span style={monoFont}>{f.work_order_no}</span>
                      {f.reported_at ? ` · ${f.reported_at.slice(0, 10)}` : ''}
                      {f.symptom ? ` · ${f.symptom}` : ''}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Spin>
  )

  const tabItems = [
    {
      key: 'plans' as const,
      label: <span><CalendarOutlined /> 维护保养计划</span>,
      children: (
        <Spin spinning={plansLoading}>
          {plans.length === 0 ? (
            <Empty description="暂无维护保养计划" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Table columns={planColumns} dataSource={plans} rowKey="id" size="small" pagination={false} scroll={{ x: 'max-content' }} />
          )}
        </Spin>
      ),
    },
    {
      key: 'history' as const,
      label: <span><SearchOutlined /> 巡检记录</span>,
      children: (
        <Spin spinning={historyLoading}>
          {history.length === 0 ? (
            <Empty description="暂无巡检记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Table columns={historyColumns} dataSource={history} rowKey="id" size="small" pagination={false} scroll={{ x: 'max-content' }} />
          )}
        </Spin>
      ),
    },
    {
      key: 'orders' as const,
      label: <span><ToolOutlined /> 维修工单</span>,
      children: (
        <Spin spinning={ordersLoading}>
          {orders.length === 0 ? (
            <Empty description="暂无维修工单" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Table columns={orderColumns} dataSource={orders} rowKey="id" size="small" pagination={false} scroll={{ x: 'max-content' }} />
          )}
        </Spin>
      ),
    },
    {
      key: 'health' as const,
      label: <span><HeartOutlined /> 健康档案</span>,
      children: healthTab,
    },
  ]

  if (!equipment) return null

  return (
    <Drawer
      title="设备详情"
      size={860}
      open={open}
      onClose={onClose}
      destroyOnHidden
      styles={{
        header: { borderBottom: '1px solid #e5e3df', padding: '16px 24px' },
        body: { padding: '24px' },
      }}
    >
      {/* 基本信息 */}
      <div style={{ marginBottom: 24 }}>
        <h3 style={{ fontSize: 15, fontWeight: 600, color: '#1a1a1a', margin: '0 0 16px 0' }}>基本信息</h3>
        <Descriptions bordered size="small" column={2} styles={{ label: { fontWeight: 500, color: '#5d5b54', width: 100 } }}>
          <Descriptions.Item label="设备编号">
            <span style={monoFont}>{equipment.equipment_no}</span>
          </Descriptions.Item>
          <Descriptions.Item label="设备名称">
            <span style={{ fontWeight: 600 }}>{equipment.name}</span>
          </Descriptions.Item>
          <Descriptions.Item label="设备分类">{categoryName || '-'}</Descriptions.Item>
          <Descriptions.Item label="安装地点">{locationName || '-'}</Descriptions.Item>
          <Descriptions.Item label="归属部门">{equipment.department_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="负责人">{equipment.responsible_person_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="设备状态">
            <span style={EQUIP_STATUS_MAP[equipment.status] || pillNeutral}>{equipment.status}</span>
          </Descriptions.Item>
          <Descriptions.Item label="重要性">
            <span style={IMPORTANCE_MAP[equipment.importance as EquipmentImportance] || pillNeutral}>{equipment.importance}</span>
          </Descriptions.Item>
          <Descriptions.Item label="规格型号">{equipment.model || '-'}</Descriptions.Item>
          <Descriptions.Item label="生产厂家">{equipment.manufacturer || '-'}</Descriptions.Item>
          <Descriptions.Item label="出厂日期">{equipment.production_date || '-'}</Descriptions.Item>
          <Descriptions.Item label="出厂编号">{equipment.factory_no || '-'}</Descriptions.Item>
          <Descriptions.Item label="入厂日期">{equipment.arrival_date || '-'}</Descriptions.Item>
          <Descriptions.Item label="技术参数" span={2}>
            {equipment.technical_params && Object.keys(equipment.technical_params).length > 0
              ? Object.entries(equipment.technical_params)
                  .map(([key, value]) => `${key}：${String(value)}`)
                  .join('；')
              : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="备注" span={2}>{equipment.description || '-'}</Descriptions.Item>
          {equipment.data_issue_note && (
            <Descriptions.Item label="数据待修正" span={2}>
              <span style={{ color: '#c0392b' }}>{equipment.data_issue_note}</span>
            </Descriptions.Item>
          )}
        </Descriptions>
      </div>

      {/* 关联记录 */}
      <div>
        <h3 style={{ fontSize: 15, fontWeight: 600, color: '#1a1a1a', margin: '0 0 16px 0' }}>关联记录</h3>
        <Tabs
          activeKey={activeTab}
          onChange={(k) => setActiveTab(k as 'plans' | 'history' | 'orders' | 'health')}
          items={tabItems}
        />
      </div>
    </Drawer>
  )
}
