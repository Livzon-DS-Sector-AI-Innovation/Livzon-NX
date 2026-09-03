'use client'

import { Drawer, Descriptions, Space, Tag, Tooltip } from 'antd'

const validationTypeLabelMap: Record<string, string> = {
  equipment_qualification: '设备确认',
  process_validation: '工艺验证',
  cleaning_validation: '清洁验证',
  other_validation: '其他验证',
}

const statusLabelMap: Record<string, string> = {
  completed: '完成',
  incomplete: '未完成',
  pending: '待完成',
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

function renderText(value: string | string[] | null | undefined): string {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.length ? value.join('、') : '-'
  return value
}

interface ValidationDetailDrawerProps {
  open: boolean
  record: Record<string, unknown> | null
  onClose: () => void
}

/** 验证记录详情抽屉：展示单条验证记录的全部字段。 */
export function ValidationDetailDrawer({
  open,
  record,
  onClose,
}: ValidationDetailDrawerProps) {
  if (!record) {
    return (
      <Drawer open={open} title="验证记录详情" width={640} onClose={onClose}>
        <span>-</span>
      </Drawer>
    )
  }
  const validationType = record.validation_type as string | null | undefined
  const status = record.status as string | null | undefined
  const normalizedStatus = status ? (statusLabelMap[status] ?? status) : null
  const productCodes = record.product_codes
  const revalidationYears = record.revalidation_cycle_years

  const items: Array<{ label: string; content: React.ReactNode }> = [
    { label: '确认名称', content: renderText(record.title as string) },
    {
      label: '验证类别',
      content:
        validationTypeLabelMap[validationType ?? ''] ?? validationType ?? '-',
    },
    {
      label: '产品代码',
      content:
        productCodes && (!Array.isArray(productCodes) || productCodes.length) ? (
          <Space wrap>
            {(Array.isArray(productCodes) ? productCodes : [productCodes]).map((code) => (
              <Tag key={String(code)}>{String(code)}</Tag>
            ))}
          </Space>
        ) : (
          '-'
        ),
    },
    { label: '部门名称', content: renderText(record.department as string) },
    { label: '设备编码', content: renderText(record.equipment_code as string) },
    { label: '验证到期时间', content: renderText(record.planned_end_date as string) },
    {
      label: '任务状态',
      content: normalizedStatus ? (
        <Tag color={normalizedStatus === '完成' ? 'green' : normalizedStatus === '待完成' ? 'orange' : 'red'}>
          {normalizedStatus}
        </Tag>
      ) : (
        '-'
      ),
    },
    { label: '群组', content: renderText(record.group_chat as string) },
    { label: '人员', content: renderText(record.participants as string) },
    { label: '负责人', content: renderText(record.owner_name as string) },
    { label: '方案名称', content: renderText(record.plan_name as string) },
    { label: '方案编码', content: renderText(record.plan_code as string) },
    { label: '起草时间', content: formatDate(record.drafted_at as string) },
    { label: '批准时间', content: formatDate(record.approved_at as string) },
    { label: '报告编号', content: renderText(record.report_no as string) },
    { label: '报告起草时间', content: formatDate(record.drafted_at_1 as string) },
    { label: '报告批准时间', content: formatDate(record.approved_at_1 as string) },
    {
      label: '再验证周期（几年）',
      content: revalidationYears != null ? `${revalidationYears}年` : '-',
    },
  ]

  return (
    <Drawer
      open={open}
      title={
        <Tooltip title={renderText(record.title as string)}>
          <span>验证记录详情</span>
        </Tooltip>
      }
      width={640}
      onClose={onClose}
    >
      <Descriptions bordered size="small" column={1} styles={{ label: { width: 160 } }}>
        {items.map((item) => (
          <Descriptions.Item key={item.label} label={item.label}>
            {item.content}
          </Descriptions.Item>
        ))}
      </Descriptions>
    </Drawer>
  )
}
