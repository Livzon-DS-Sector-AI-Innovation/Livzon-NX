'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Table, Tag, Space, Popconfirm, Select, Modal, Input, App } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { EyeOutlined, DeleteOutlined, MailOutlined } from '@ant-design/icons'
import { Candidate } from '@/types/hr'
import { storeCandidateListContext } from './candidateHelpers'
import { sendOfferEmailAction } from '@/actions/hr'

interface CandidateListViewProps {
  candidates: Candidate[]
  total: number
  page: number
  pageSize: number
  loading: boolean
  onPageChange: (page: number, pageSize: number) => void
  onDelete: (id: string) => void
  onTransfer?: (id: string) => void
  transferring?: boolean
  onRefresh?: () => void
  onStatusChange?: (candidateId: string, newStatus: string) => void
}

export default function CandidateListView({
  candidates,
  total,
  page,
  pageSize,
  loading,
  onPageChange,
  onDelete,
  onTransfer,
  transferring,
  onRefresh,
  onStatusChange,
}: CandidateListViewProps) {
  const router = useRouter()
  const { message } = App.useApp()
  const [updatingStatus, setUpdatingStatus] = useState<string | null>(null)
  const [emailModalOpen, setEmailModalOpen] = useState(false)
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null)
  const [emailTo, setEmailTo] = useState('')
  const [emailSubject, setEmailSubject] = useState('')
  const [emailBody, setEmailBody] = useState('')
  const [sending, setSending] = useState(false)

  const handleRowClick = (record: Candidate) => {
    storeCandidateListContext(candidates, record.id)
    router.push(`/hr/recruitment/${record.id}`)
  }

  const handleStatusChange = (candidateId: string, newStatus: string) => {
    // 使用父组件传入的回调（已包含乐观更新和错误处理）
    onStatusChange?.(candidateId, newStatus)
  }

  const handleOpenEmailModal = (candidate: Candidate) => {
    setSelectedCandidate(candidate)
    setEmailTo(candidate.email || '')
    setEmailSubject(`录用通知 - ${candidate.name}`)
    setEmailBody(`尊敬的 ${candidate.name}：\n\n您好！\n\n感谢您参加我司 ${candidate.job_position || '职位'} 的面试。经过综合评估，我们很高兴地通知您，您已通过面试。\n\n请您于近期携带相关材料到公司办理入职手续。\n\n如有任何疑问，请随时与我们联系。\n\n祝好！\n人力资源部`)
    setEmailModalOpen(true)
  }

  const handleOpenRejectEmailModal = (candidate: Candidate) => {
    setSelectedCandidate(candidate)
    setEmailTo(candidate.email || '')
    setEmailSubject(`面试结果通知 - ${candidate.name}`)
    setEmailBody(`尊敬的 ${candidate.name}：\n\n您好！\n\n感谢您参加我司 ${candidate.job_position || '职位'} 的面试。经过综合评估，很遗憾地通知您，您未能通过本次面试。\n\n我们已将您的简历纳入人才库，未来如有合适职位将优先联系您。\n\n祝您求职顺利！\n人力资源部`)
    setEmailModalOpen(true)
  }

  const handleSendEmail = async () => {
    if (!selectedCandidate) return
    setSending(true)
    try {
      await sendOfferEmailAction({
        candidate_id: selectedCandidate.id,
        to_email: emailTo,
        subject: emailSubject,
        body: emailBody,
      })
      message.success('邮件发送成功')
      setEmailModalOpen(false)
      onRefresh?.()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '邮件发送失败')
    } finally {
      setSending(false)
    }
  }

  const fitLevelColors: Record<string, string> = {
    '非常满足': 'purple',
    '高': 'green',
    '中': 'orange',
    '低': 'red',
  }

  const interviewStatusColors: Record<string, string> = {
    '待安排': 'default',
    '已安排': 'processing',
    '已完成': 'blue',
    '通过': 'green',
    '未通过': 'red',
  }

  const INTERVIEW_STATUS_OPTIONS = [
    { value: '待安排', label: '待安排' },
    { value: '已安排', label: '已安排' },
    { value: '已完成', label: '已完成' },
    { value: '通过', label: '通过' },
    { value: '未通过', label: '未通过' },
  ]

  const columns: ColumnsType<Candidate> = [
    {
      title: '姓名',
      dataIndex: 'name',
      key: 'name',
      width: 70,
    },
    {
      title: '应聘职位',
      dataIndex: 'job_position',
      key: 'job_position',
      width: 90,
    },
    {
      title: '联系方式',
      dataIndex: 'contact',
      key: 'contact',
      width: 120,
      ellipsis: true,
      render: (_: any, record: Candidate) =>
        record.contact || record.phone || record.email || '-',
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      width: 150,
      ellipsis: true,
      render: (val: string) => val || '-',
    },
    {
      title: '学历',
      dataIndex: 'education',
      key: 'education',
      width: 55,
    },
    {
      title: (
        <div style={{ textAlign: 'center', lineHeight: 1.2 }}>
          <div>工作经验</div>
          <div>(年)</div>
        </div>
      ),
      dataIndex: 'work_years',
      key: 'work_years',
      width: 65,
      align: 'center',
      render: (val: number | undefined) => val != null ? val : '-',
    },
    {
      title: (
        <div style={{ textAlign: 'center', lineHeight: 1.2 }}>
          <div>技能</div>
          <div>匹配度</div>
        </div>
      ),
      dataIndex: 'match_rate',
      key: 'match_rate',
      width: 65,
      align: 'center',
      render: (val: number | undefined) => val != null ? `${val}%` : '-',
    },
    {
      title: (
        <div style={{ textAlign: 'center', lineHeight: 1.2 }}>
          <div>简历</div>
          <div>评分</div>
        </div>
      ),
      dataIndex: 'resume_score',
      key: 'resume_score',
      width: 55,
      align: 'center',
      render: (val: number | undefined) => val != null ? `${val}分` : '-',
    },
    {
      title: (
        <div style={{ textAlign: 'center', lineHeight: 1.2 }}>
          <div>招聘</div>
          <div>符合程度</div>
        </div>
      ),
      dataIndex: 'fit_level',
      key: 'fit_level',
      width: 70,
      align: 'center',
      render: (val: string) =>
        val ? (
          <Tag color={fitLevelColors[val] || 'default'}>{val}</Tag>
        ) : (
          '-'
        ),
    },
    {
      title: '面试状态',
      dataIndex: 'interview_status',
      key: 'interview_status',
      width: 90,
      align: 'center',
      render: (val: string, record: Candidate) => (
        <Select
          value={val || undefined}
          placeholder="待安排"
          size="small"
          style={{ width: '100%', minWidth: 80 }}
          loading={updatingStatus === record.id}
          onChange={(v) => handleStatusChange(record.id, v)}
          options={INTERVIEW_STATUS_OPTIONS}
          allowClear
        />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      fixed: 'right',
      render: (_: any, record: Candidate) => (
        <Space size="small">
          <a onClick={() => handleRowClick(record)}>
            <EyeOutlined /> 查看
          </a>
          {record.interview_status === '通过' && (
            <>
              <a onClick={() => handleOpenEmailModal(record)} className="text-blue-500">
                <MailOutlined /> 发Offer
              </a>
              <Popconfirm
                title="确认转入职"
                description={`确定将「${record.name}」转入入职管理吗？`}
                onConfirm={() => onTransfer?.(record.id)}
                okText="确认"
                cancelText="取消"
                disabled={transferring}
              >
                <a className={`text-green-500 ${transferring ? 'opacity-50 pointer-events-none' : ''}`}>
                  {transferring ? '转入职中...' : '转入职'}
                </a>
              </Popconfirm>
            </>
          )}
          {record.interview_status === '未通过' && (
            <a onClick={() => handleOpenRejectEmailModal(record)} className="text-orange-500">
              <MailOutlined /> 发邮件通知
            </a>
          )}
          <Popconfirm
            title="确认删除"
            description={`确定要删除候选人「${record.name}」的简历吗？`}
            onConfirm={() => onDelete(record.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <a className="text-red-500" onClick={(e) => e.stopPropagation()}>
              <DeleteOutlined /> 删除
            </a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
      <Table
        columns={columns}
        dataSource={candidates}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: onPageChange,
        }}
        scroll={{ x: 900 }}
        size="small"
      />

      <Modal
        title="发送邮件"
        open={emailModalOpen}
        onCancel={() => setEmailModalOpen(false)}
        onOk={handleSendEmail}
        okText="是"
        cancelText="否"
        confirmLoading={sending}
        width={600}
      >
        <div className="space-y-4 py-2">
          <div>
            <label className="block text-sm mb-1 font-medium">收件人邮箱</label>
            <Input value={emailTo} onChange={(e) => setEmailTo(e.target.value)} placeholder="请输入收件人邮箱" />
          </div>
          <div>
            <label className="block text-sm mb-1 font-medium">邮件主题</label>
            <Input value={emailSubject} onChange={(e) => setEmailSubject(e.target.value)} placeholder="请输入邮件主题" />
          </div>
          <div>
            <label className="block text-sm mb-1 font-medium">邮件正文</label>
            <Input.TextArea
              value={emailBody}
              onChange={(e) => setEmailBody(e.target.value)}
              rows={12}
              placeholder="请输入邮件正文"
            />
          </div>
        </div>
      </Modal>
    </>
  )
}
