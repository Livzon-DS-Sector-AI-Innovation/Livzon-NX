'use client'

import { useState, useEffect } from 'react'
import { App, Drawer, Descriptions, Tag, Timeline, Button, Space, Select, Input, Image, Modal, InputNumber } from 'antd'
import {
  ClockCircleOutlined, UserOutlined, ToolOutlined,
  CheckCircleOutlined, CloseCircleOutlined, StopOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useEquipmentStore } from '@/stores/equipment'
import { assignWorkOrder, startWorkOrder, completeWorkOrder, verifyWorkOrder, closeWorkOrder, claimWorkOrder, updateWorkOrderExternalCost, transferWorkOrder } from '@/actions/equipment'
import { WorkOrderStatus, WorkOrderPriority, Maintainer, SparePart } from '@/types/equipment'
import { fetchMaintainersClient, fetchWorkOrderByIdClient, fetchSparePartsClient, fetchWorkOrderEventsClient } from '@/lib/api/equipment-client'
import { MaterialConsumeDrawer } from './MaterialConsumeDrawer'
import { MaterialRecordTable } from './MaterialRecordTable'

const { TextArea } = Input

const statusConfig: Record<WorkOrderStatus, { color: string; label: string }> = {
  '待处理': { color: '#e03131', label: '待处理' },
  '执行中': { color: '#dd5b00', label: '执行中' },
  '待验收': { color: '#d4b106', label: '待验收' },
  '已完成': { color: '#1aae39', label: '已完成' },
  '已关闭': { color: '#787671', label: '已关闭' },
}

const priorityConfig: Record<WorkOrderPriority, { color: string }> = {
  '紧急': { color: '#e03131' },
  '高': { color: '#dd5b00' },
  '中': { color: '#5645d4' },
  '低': { color: '#787671' },
}

function formatDuration(minutes: number | null): string {
  if (minutes === null || minutes === undefined) return '-'
  if (minutes < 60) return `${minutes}分钟`
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  return mins > 0 ? `${hours}小时${mins}分` : `${hours}小时`
}

function formatTime(time: string | null): string {
  if (!time) return '-'
  return new Date(time).toLocaleString('zh-CN')
}

interface WorkOrderDetailDrawerProps {
  onRefresh?: () => void
}

export function WorkOrderDetailDrawer({ onRefresh }: WorkOrderDetailDrawerProps) {
  const { message, modal } = App.useApp()
  const { workOrderDetailOpen, viewingWorkOrder, closeWorkOrderDetail, setViewingWorkOrder } = useEquipmentStore()

  const [maintainers, setMaintainersState] = useState<Maintainer[]>([])
  const [spareParts, setSpareParts] = useState<SparePart[]>([])
  // 领料成功后递增 key 重建领料记录表（记录表挂载时自取数）
  const [materialsKey, setMaterialsKey] = useState(0)

  const refreshDetail = async (id: string) => {
    try {
      const updated = await fetchWorkOrderByIdClient(id)
      setViewingWorkOrder(updated)
    } catch { /* 静默失败，列表刷新已覆盖 */ }
    onRefresh?.()
  }
  useEffect(() => {
    if (workOrderDetailOpen) {
      fetchMaintainersClient().then(setMaintainersState).catch(() => {})
      fetchSparePartsClient({ page_size: 200 })
        .then((res) => setSpareParts(res.items))
        .catch(() => {})
    }
  }, [workOrderDetailOpen])

  if (!viewingWorkOrder) return null

  const wo = viewingWorkOrder
  const statusCfg = statusConfig[wo.status]
  const priorityCfg = priorityConfig[wo.priority]

  const handleAssign = () => {
    let assigneeId = ''
    modal.confirm({
      title: '指派维修人',
      content: (
        <div style={{ marginTop: 16 }}>
          <Select
            placeholder="选择维修人员"
            style={{ width: '100%' }}
            showSearch
            optionFilterProp="label"
            onChange={(val) => { assigneeId = val }}
            options={maintainers.map((m) => ({
              label: `${m.name} (${m.employee_no || '-'})`,
              value: m.user_id,
            }))}
          />
        </div>
      ),
      okText: '确认指派',
      cancelText: '取消',
      onOk: async () => {
        if (!assigneeId) { message.warning('请选择维修人员'); throw new Error('请选择维修人员') }
        try {
          await assignWorkOrder(wo.id, { assignee_id: assigneeId })
          message.success('指派成功')
          await refreshDetail(wo.id)
        } catch (error) {
          message.error(error?.message || '指派失败')
          throw error
        }
      },
    })
  }

  const handleStart = async () => {
    try {
      await startWorkOrder(wo.id)
      message.success('已开始维修')
      await refreshDetail(wo.id)
    } catch (error) {
      message.error(error?.message || '操作失败')
    }
  }

  const handleTransfer = () => {
    if (!maintainers.length) {
      message.warning('暂无可转派的维修人员')
      return
    }
    let selectedId: string | undefined
    let reason = ''
    modal.confirm({
      title: `转派维修人${(wo.transfer_count ?? 0) > 0 ? `（已转派 ${wo.transfer_count} 次）` : ''}`,
      content: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 8 }}>
          <Select
            placeholder="选择新维修人"
            showSearch
            optionFilterProp="label"
            style={{ width: '100%' }}
            onChange={(v) => { selectedId = v }}
            options={maintainers
              .filter((m) => m.user_id !== wo.assignee_id)
              .map((m) => ({ label: `${m.name}（${m.employee_no || '-'}）`, value: m.user_id }))}
          />
          <Input
            placeholder="转派原因（选填）"
            maxLength={200}
            onChange={(e) => { reason = e.target.value }}
          />
        </div>
      ),
      okText: '确认转派',
      onOk: async () => {
        if (!selectedId) {
          message.warning('请选择新维修人')
          return false // 返回 false 阻止弹窗关闭；禁止裸 reject（逃逸 Unhandled Rejection）
        }
        try {
          await transferWorkOrder(wo.id, {
            assignee_id: selectedId,
            reason: reason || undefined,
          })
          message.success('已转派')
          onRefresh?.()
        } catch (error) {
          message.error(error instanceof Error ? error.message : '转派失败')
          return false
        }
      },
    })
  }

  const handleComplete = () => {
    let repairDetail = ''
    modal.confirm({
      title: '提交维修完成',
      content: (
        <div style={{ marginTop: 16 }}>
          <div style={{ marginBottom: 8, fontSize: 14, color: '#37352f' }}>维修过程描述 *</div>
          <TextArea
            placeholder="请详细描述维修过程和处理措施"
            rows={4}
            maxLength={1000}
            showCount
            onChange={(e) => { repairDetail = e.target.value }}
          />
        </div>
      ),
      okText: '提交',
      cancelText: '取消',
      onOk: async () => {
        if (!repairDetail.trim()) { message.warning('请填写维修过程描述'); throw new Error() }
        try {
          await completeWorkOrder(wo.id, { repair_detail: repairDetail })
          message.success('已提交验收')
          await refreshDetail(wo.id)
        } catch (error) {
          message.error(error?.message || '操作失败')
          throw error
        }
      },
    })
  }

  const handleVerify = (result: '合格' | '不合格') => {
    let remark = ''
    modal.confirm({
      title: result === '合格' ? '验收通过' : '验收不通过',
      content: (
        <div style={{ marginTop: 16 }}>
          {result === '不合格' && <div style={{ marginBottom: 8, fontSize: 14, color: '#37352f' }}>不通过原因 *</div>}
          <TextArea
            placeholder={result === '合格' ? '验收备注（可选）' : '请说明不通过的原因'}
            rows={3} maxLength={500} showCount
            onChange={(e) => { remark = e.target.value }}
          />
        </div>
      ),
      okText: '确认',
      cancelText: '取消',
      okButtonProps: result === '不合格' ? { danger: true } : {},
      onOk: async () => {
        if (result === '不合格' && !remark.trim()) { message.warning('请填写不通过原因'); throw new Error() }
        try {
          await verifyWorkOrder(wo.id, { result, remark: remark || undefined })
          message.success(result === '合格' ? '验收通过' : '已打回重修')
          await refreshDetail(wo.id)
        } catch (error) {
          message.error(error?.message || '操作失败')
          throw error
        }
      },
    })
  }

  const handleClose = async () => {
    try {
      await closeWorkOrder(wo.id)
      message.success('工单已关闭')
      await refreshDetail(wo.id)
    } catch (error) {
      message.error(error?.message || '操作失败')
    }
  }

  const handleClaim = async () => {
    try {
      await claimWorkOrder(wo.id)
      message.success('抢单成功')
      await refreshDetail(wo.id)
    } catch (error) {
      message.error(error?.message || '抢单失败')
    }
  }

  const timelineItems = []
  if (wo.reported_at) {
    timelineItems.push({
      color: '#e03131',
      icon: <ClockCircleOutlined style={{ fontSize: 14 }} />,
      content: (
        <div>
          <div style={{ fontWeight: 500, color: '#1a1a1a' }}>报修</div>
          <div style={{ fontSize: 13, color: '#787671' }}>{formatTime(wo.reported_at)}</div>
        </div>
      ),
    })
  }
  if (wo.assigned_at) {
    timelineItems.push({
      color: '#5645d4',
      icon: <UserOutlined style={{ fontSize: 14 }} />,
      content: (
        <div>
          <div style={{ fontWeight: 500, color: '#1a1a1a' }}>已指派</div>
          <div style={{ fontSize: 13, color: '#787671' }}>{formatTime(wo.assigned_at)}</div>
        </div>
      ),
    })
  }
  if (wo.started_at) {
    timelineItems.push({
      color: '#dd5b00',
      icon: <ToolOutlined style={{ fontSize: 14 }} />,
      content: (
        <div>
          <div style={{ fontWeight: 500, color: '#1a1a1a' }}>开始维修</div>
          <div style={{ fontSize: 13, color: '#787671' }}>{formatTime(wo.started_at)}</div>
        </div>
      ),
    })
  }
  if (wo.completed_at) {
    timelineItems.push({
      color: '#d4b106',
      icon: <CheckCircleOutlined style={{ fontSize: 14 }} />,
      content: (
        <div>
          <div style={{ fontWeight: 500, color: '#1a1a1a' }}>提交完成</div>
          <div style={{ fontSize: 13, color: '#787671' }}>{formatTime(wo.completed_at)}</div>
          {wo.repair_detail && <div style={{ fontSize: 13, color: '#5d5b54', marginTop: 4 }}>维修描述: {wo.repair_detail}</div>}
        </div>
      ),
    })
  }
  if (wo.verified_at) {
    timelineItems.push({
      color: wo.verification_result === '合格' ? '#1aae39' : '#e03131',
      icon: wo.verification_result === '合格'
        ? <CheckCircleOutlined style={{ fontSize: 14 }} />
        : <CloseCircleOutlined style={{ fontSize: 14 }} />,
      content: (
        <div>
          <div style={{ fontWeight: 500, color: '#1a1a1a' }}>
            验收 - <Tag color={wo.verification_result === '合格' ? 'success' : 'error'}>{wo.verification_result}</Tag>
          </div>
          <div style={{ fontSize: 13, color: '#787671' }}>{formatTime(wo.verified_at)}</div>
          {wo.verification_remark && <div style={{ fontSize: 13, color: '#5d5b54', marginTop: 4 }}>备注: {wo.verification_remark}</div>}
        </div>
      ),
    })
  }
  if (wo.status === '已关闭') {
    timelineItems.push({
      color: '#787671',
      icon: <StopOutlined style={{ fontSize: 14 }} />,
      content: <div><div style={{ fontWeight: 500, color: '#1a1a1a' }}>已关闭</div></div>,
    })
  }

  return (
    <Drawer
      title={
        <div className="flex items-center gap-3">
          <span style={{ fontWeight: 600 }}>{wo.work_order_no}</span>
          <Tag style={{ color: statusCfg.color, background: statusCfg.color + '18', border: 'none', borderRadius: 4, fontWeight: 500 }}>
            {statusCfg.label}
          </Tag>
        </div>
      }
      size={520}
      open={workOrderDetailOpen}
      onClose={closeWorkOrderDetail}
      destroyOnHidden
    >
      <Descriptions column={2} size="small" styles={{ label: { color: '#787671', fontSize: 13 }, content: { color: '#1a1a1a', fontSize: 14 } }}>
        <Descriptions.Item label="工单类型">
          <Tag style={{
            color: wo.order_type === '故障维修' || wo.order_type === '异常处理' ? '#dd5b00'
                 : wo.order_type === '日常维护' ? '#0075de'
                 : '#5645d4',
            background: wo.order_type === '故障维修' || wo.order_type === '异常处理' ? '#fff7e6'
                      : wo.order_type === '日常维护' ? '#dcecfa'
                      : '#ede9f7',
            border: 'none', borderRadius: 4,
          }}>{wo.order_type}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="优先级">
          <span style={{ color: priorityCfg.color, fontWeight: 500 }}>{wo.priority}</span>
        </Descriptions.Item>
        <Descriptions.Item label="关联设备" span={2}>{wo.equipment_name || wo.equipment_id}</Descriptions.Item>
        <Descriptions.Item label="故障现象" span={2}>{wo.symptom_name || '-'}</Descriptions.Item>
        <Descriptions.Item label="故障描述" span={2}>{wo.fault_description || '-'}</Descriptions.Item>
        <Descriptions.Item label="报修人">{wo.reporter_name || '-'}</Descriptions.Item>
        <Descriptions.Item label="维修人">{wo.assignee_name || '-'}</Descriptions.Item>
        <Descriptions.Item label="责任人">{wo.responsible_person_name || '-'}</Descriptions.Item>
        <Descriptions.Item label="报修时间">{formatTime(wo.reported_at)}</Descriptions.Item>
        <Descriptions.Item label="维修耗时">{formatDuration(wo.actual_duration)}</Descriptions.Item>
      </Descriptions>

      {/* 维修成本（方案C）：备件 + 工时（完成时自动按费率计算）+ 外委（补录） */}
      <div style={{ marginTop: 24, padding: '12px 16px', background: 'var(--color-surface)', borderRadius: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: '#1a1a1a' }}>维修成本</span>
          <Space size={12}>
            <span style={{ color: '#5d5b54', fontSize: 13 }}>
              备件 ¥{(wo.spare_parts_cost ?? 0).toFixed(2)} · 工时 ¥{(wo.labor_cost ?? 0).toFixed(2)} · 外委 ¥
              {(wo.external_cost ?? 0).toFixed(2)}
            </span>
            <ExternalCostButton workOrderId={wo.id} initialCost={wo.external_cost ?? null} initialVendor={wo.external_vendor ?? null} />
          </Space>
        </div>
        <div style={{ fontSize: 20, fontWeight: 700, color: '#1a1a1a' }}>
          合计 ¥{((wo.spare_parts_cost ?? 0) + (wo.labor_cost ?? 0) + (wo.external_cost ?? 0)).toFixed(2)}
          {wo.external_vendor ? (
            <span style={{ fontSize: 12, fontWeight: 400, color: '#8a867d', marginLeft: 10 }}>
              外委厂商：{wo.external_vendor}
            </span>
          ) : null}
        </div>
      </div>

      {wo.images && wo.images.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#1a1a1a', marginBottom: 12 }}>故障图片</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {wo.images.map((img) => (
              <Image
                key={img.id}
                src={`/api/v1/equipment/maintenance/work-orders/${wo.id}/images/${img.id}/file`}
                alt={img.file_name}
                width={100}
                height={100}
                style={{ objectFit: 'cover', borderRadius: 6, cursor: 'pointer' }}
              />
            ))}
          </div>
        </div>
      )}

      <div style={{ marginTop: 24, marginBottom: 24 }}>
        <div style={{ fontSize: 15, fontWeight: 600, color: '#1a1a1a', marginBottom: 16 }}>工单进度</div>
        <Timeline items={timelineItems} />
      </div>

      {/* 领料记录：维修期间可领用备件（扣库存），完成后仅可回看 */}
      <div style={{ marginTop: 24, marginBottom: 24 }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 12,
        }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#1a1a1a' }}>领料记录</div>
          {['待处理', '执行中', '待验收'].includes(wo.status) && (
            <MaterialConsumeDrawer
              workOrderId={wo.id}
              spareParts={spareParts}
              onRefresh={() => {
                setMaterialsKey((k) => k + 1)
                fetchSparePartsClient({ page_size: 200 })
                  .then((res) => setSpareParts(res.items))
                  .catch(() => {})
              }}
            />
          )}
        </div>
        <MaterialRecordTable key={materialsKey} workOrderId={wo.id} />
      </div>

      <div style={{ borderTop: '1px solid #ede9e4', paddingTop: 16 }}>
        <Space wrap>
          {wo.status === '待处理' && (
            <>
              <Button type="primary" onClick={handleStart}>开始执行</Button>
              <Button onClick={handleAssign}>指派维修人</Button>
              <Button icon={<ThunderboltOutlined />} onClick={handleClaim}>抢单</Button>
            </>
          )}
          {wo.status === '执行中' && <Button type="primary" onClick={handleComplete}>提交完成</Button>}
          {(wo.status === '待处理' || wo.status === '执行中') && (
            <Button onClick={handleTransfer}>
              ↗️ 转派{(wo.transfer_count ?? 0) > 0 ? `（${wo.transfer_count}次）` : ''}
            </Button>
          )}
          {wo.status === '待验收' && (
            <>
              <Button type="primary" onClick={() => handleVerify('合格')}>验收通过</Button>
              <Button danger onClick={() => handleVerify('不合格')}>打回重修</Button>
            </>
          )}
          {wo.status === '已完成' && <Button onClick={handleClose}>关闭工单</Button>}
        </Space>
      </div>
    </Drawer>
  )
}

// 外委费用补录（方案C）：小按钮 + 弹窗，保存走 Server Action
function ExternalCostButton({
  workOrderId,
  initialCost,
  initialVendor,
}: {
  workOrderId: string
  initialCost: number | null
  initialVendor: string | null
}) {
  const { message } = App.useApp()
  const [open, setOpen] = useState(false)
  const [cost, setCost] = useState<number | null>(initialCost)
  const [vendor, setVendor] = useState<string | null>(initialVendor)
  const [submitting, setSubmitting] = useState(false)

  const handleSave = async () => {
    setSubmitting(true)
    try {
      await updateWorkOrderExternalCost(workOrderId, {
        external_cost: cost ?? 0,
        external_vendor: vendor,
      })
      message.success('外委费用已保存，刷新后生效')
      setOpen(false)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <Button size="small" onClick={() => setOpen(true)}>
        补录外委
      </Button>
      <Modal
        title="补录外委费用"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={handleSave}
        confirmLoading={submitting}
        destroyOnHidden
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 8 }}>
          <label style={{ fontSize: 13, color: '#5d5b54' }}>
            外委金额（元）
            <InputNumber
              min={0}
              precision={2}
              value={cost ?? undefined}
              onChange={(v) => setCost(v ?? 0)}
              style={{ width: '100%', marginTop: 4 }}
            />
          </label>
          <label style={{ fontSize: 13, color: '#5d5b54' }}>
            外委厂商
            <Input
              maxLength={100}
              value={vendor ?? ''}
              onChange={(e) => setVendor(e.target.value)}
              placeholder="选填"
              style={{ marginTop: 4 }}
            />
          </label>
        </div>
      </Modal>
    </>
  )
}
