'use client'

import { Drawer, Descriptions, Divider, Tag, Button, Timeline } from 'antd'
import { UserOutlined } from '@ant-design/icons'
import Link from 'next/link'
import { PositionTransferRecord, ApprovalFlow } from '@/types/hr'

interface PositionTransferDetailDrawerProps {
  open: boolean
  record: PositionTransferRecord | null
  onClose: () => void
}

const approvalStatusColorMap: Record<string, string> = {
  草稿: 'default',
  待审批: 'processing',
  已通过: 'success',
  已拒绝: 'error',
}

const approvalStepStatusColorMap: Record<string, string> = {
  pending: 'default',
  approved: 'success',
  rejected: 'error',
  skipped: 'warning',
}

const approvalStepStatusLabelMap: Record<string, string> = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已拒绝',
  skipped: '已跳过',
}

export default function PositionTransferDetailDrawer({
  open,
  record,
  onClose,
}: PositionTransferDetailDrawerProps) {
  if (!record) return null

  const flow: ApprovalFlow | undefined = record.approval_flow

  return (
    <Drawer
      title={`岗位调动详情 - ${record.employee_name}`}
      placement="right"
      open={open}
      onClose={onClose}
      styles={{ wrapper: { width: 720 } }}
      extra={
        record.employee_id ? (
          <Link href={`/hr/profile?employee_id=${record.employee_id}`}>
            <Button size="small" icon={<UserOutlined />}>查看员工档案</Button>
          </Link>
        ) : undefined
      }
    >
      <Descriptions title="基本信息" bordered column={2} size="small">
        <Descriptions.Item label="申请人">{record.employee_name}</Descriptions.Item>
        <Descriptions.Item label="工号">{record.employee_number || '-'}</Descriptions.Item>
        <Descriptions.Item label="序号">{record.seq_number ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="联系电话">{record.contact_phone || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="调动信息" bordered column={2} size="small">
        <Descriptions.Item label="原部门">{record.department_before || '-'}</Descriptions.Item>
        <Descriptions.Item label="原职位">{record.original_position || '-'}</Descriptions.Item>
        <Descriptions.Item label="申请部门">{record.apply_department || '-'}</Descriptions.Item>
        <Descriptions.Item label="申请职位">{record.apply_position || '-'}</Descriptions.Item>
        <Descriptions.Item label="生效日期">{record.effective_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="联系电话">{record.contact_phone || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="申请人确认" bordered column={2} size="small">
        <Descriptions.Item label="确认说明" span={2}>
          {record.applicant_confirmation_text || '-'}
        </Descriptions.Item>
        <Descriptions.Item label="签名">{record.applicant_signature || '-'}</Descriptions.Item>
        <Descriptions.Item label="确认日期">{record.applicant_confirmation_date || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <div className="mb-2 flex items-center gap-2">
        <span className="text-[14px] font-medium text-[var(--color-charcoal)]">审批流程</span>
        <Tag color={approvalStatusColorMap[record.approval_status] || 'default'}>
          {record.approval_status}
        </Tag>
        {flow?.is_supervisor_level !== undefined && (
          <Tag color="blue">
            {flow.is_supervisor_level ? '主管级' : '非主管级'}
          </Tag>
        )}
      </div>

      {flow && flow.steps && flow.steps.length > 0 ? (
        <Timeline
          items={flow.steps.map((step, index) => ({
            color: step.status === 'approved' ? 'green'
              : step.status === 'rejected' ? 'red'
              : step.status === 'skipped' ? 'gray'
              : index === flow.current_step ? 'blue' : 'gray',
            content: (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium">{step.label}</span>
                <Tag color={approvalStepStatusColorMap[step.status] || 'default'}>
                  {approvalStepStatusLabelMap[step.status] || step.status}
                </Tag>
                {step.signer && <span className="text-gray-600">审批人：{step.signer}</span>}
                {step.date && <span className="text-gray-500 text-xs">{step.date}</span>}
                {step.opinion && <span className="text-gray-500 text-xs">意见：{step.opinion}</span>}
              </div>
            ),
          }))}
        />
      ) : (
        <div className="text-gray-400 text-sm mb-4">尚未提交审批</div>
      )}

      <Divider />

      <Descriptions title="同步信息" bordered column={2} size="small">
        <Descriptions.Item label="飞书记录ID">{record.feishu_record_id || '-'}</Descriptions.Item>
        <Descriptions.Item label="同步时间">{record.feishu_synced_at || '-'}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{record.created_at || '-'}</Descriptions.Item>
        <Descriptions.Item label="更新时间">{record.updated_at || '-'}</Descriptions.Item>
      </Descriptions>
    </Drawer>
  )
}
