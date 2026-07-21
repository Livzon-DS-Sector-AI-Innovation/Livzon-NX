'use client'

import { useState, useCallback } from 'react'
import { Table, Button, Space, Tag, App, Modal, Input, Select } from 'antd'
import {
  PlusOutlined, EyeOutlined, DeleteOutlined, ReloadOutlined, ExportOutlined,
} from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import dayjs from 'dayjs'
import type { ValidationAuditTaskListItem, TaskStatus, AuditMode } from '@/types/validation-audit'
import {
  AUDIT_MODE_LABELS, STATUS_LABELS, CONCLUSION_LABELS,
} from '@/types/validation-audit'
import { deleteValidationAuditTask } from '@/actions/validation-audit'

interface Props {
  initialTasks: ValidationAuditTaskListItem[]
  initialTotal: number
}

export default function ValidationAuditListClient({ initialTasks, initialTotal }: Props) {
  const { message, modal } = App.useApp()
  const router = useRouter()
  const [tasks, setTasks] = useState(initialTasks)
  const [total, setTotal] = useState(initialTotal)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const handleDelete = useCallback((taskId: string, taskName: string) => {
    modal.confirm({
      title: '确认删除',
      content: `确定要删除审核任务「${taskName}」吗？关联的文件、问题和报告将一并删除。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        const result = await deleteValidationAuditTask(taskId)
        if (result.success) {
          message.success(result.message)
          setTasks(prev => prev.filter(t => t.id !== taskId))
          setTotal(prev => prev - 1)
        } else {
          message.error(result.message)
        }
      },
    })
  }, [modal, message])

  const columns = [
    {
      title: '任务名称',
      dataIndex: 'task_name',
      key: 'task_name',
      width: 200,
      ellipsis: true,
    },
    {
      title: '品种',
      dataIndex: 'product_name',
      key: 'product_name',
      width: 150,
      ellipsis: true,
    },
    {
      title: '来源公司',
      dataIndex: 'source_company',
      key: 'source_company',
      width: 160,
      ellipsis: true,
    },
    {
      title: '审核模式',
      dataIndex: 'audit_mode',
      key: 'audit_mode',
      width: 140,
      render: (mode: AuditMode) => AUDIT_MODE_LABELS[mode] || mode,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: TaskStatus) => {
        const cfg = STATUS_LABELS[status]
        return cfg ? <Tag color={cfg.color}>{cfg.label}</Tag> : status
      },
    },
    {
      title: '审核结论',
      dataIndex: 'conclusion',
      key: 'conclusion',
      width: 110,
      render: (conclusion: string | null) => {
        if (!conclusion) return <span className="text-[var(--color-stone)]">—</span>
        const cfg = CONCLUSION_LABELS[conclusion as keyof typeof CONCLUSION_LABELS]
        return cfg ? <Tag color={cfg.color}>{cfg.label}</Tag> : conclusion
      },
    },
    {
      title: '问题数',
      key: 'issues',
      width: 140,
      render: (_: unknown, record: ValidationAuditTaskListItem) => (
        <Space size={4}>
          {record.serious_count > 0 && <Tag color="error">{record.serious_count} 严重</Tag>}
          {record.general_count > 0 && <Tag color="warning">{record.general_count} 一般</Tag>}
          {record.suggestion_count > 0 && <Tag color="blue">{record.suggestion_count} 建议</Tag>}
          {record.serious_count + record.general_count + record.suggestion_count === 0 && (
            <span className="text-[var(--color-stone)]">—</span>
          )}
        </Space>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (val: string) => dayjs(val).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      fixed: 'right' as const,
      render: (_: unknown, record: ValidationAuditTaskListItem) => (
        <Space size={4}>
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => router.push(`/registration/validation-audit/${record.id}`)}
          >
            查看
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record.id, record.task_name)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-1">
            验证文件审核
          </h1>
          <p className="text-[14px] text-[var(--color-steel)]">
            上传验证方案/报告，AI 自动审核合规性
          </p>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          size="large"
          onClick={() => router.push('/registration/validation-audit/new')}
          style={{ borderRadius: 8 }}
        >
          新建审核任务
        </Button>
      </div>

      <div
        className="bg-[var(--color-canvas)] border border-[var(--color-hairline)]"
        style={{ borderRadius: 12 }}
      >
        <Table
          columns={columns}
          dataSource={tasks}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps) },
          }}
          scroll={{ x: 1200 }}
          size="middle"
        />
      </div>
    </div>
  )
}
