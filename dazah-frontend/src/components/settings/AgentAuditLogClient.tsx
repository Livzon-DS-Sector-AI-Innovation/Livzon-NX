'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Badge,
  Button,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from 'antd'
import { EyeOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import {
  fetchAgentAuditSession,
  fetchAgentAuditSessions,
  type AgentAuditOperationItem,
  type AgentAuditSessionDetail,
  type AgentAuditSessionItem,
} from '@/lib/api/agentAudit'

const { Text, Paragraph } = Typography
const { RangePicker } = DatePicker

const statusLabels: Record<string, string> = {
  active: '进行中',
  archived: '已归档',
  completed: '已完成',
  started: '执行中',
  success: '成功',
  succeeded: '成功',
  executed: '已执行',
  pending: '待确认',
  cancelled: '已取消',
  rejected: '已拒绝',
  denied: '已阻止',
  failed: '失败',
}

function statusTag(status: string) {
  const color = ['success', 'succeeded', 'executed', 'completed'].includes(status)
    ? 'success'
    : ['failed', 'rejected', 'denied'].includes(status)
      ? 'error'
      : status === 'pending'
        ? 'warning'
        : 'processing'
  return <Tag color={color}>{statusLabels[status] || status}</Tag>
}

function formatTime(value: string) {
  return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
}

function JsonBlock({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <Text type="secondary">无</Text>
  return (
    <pre className="m-0 max-h-[320px] overflow-auto rounded-lg bg-[var(--color-surface)] p-3 text-[12px] leading-5 text-[var(--color-charcoal)]">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function OperationsTable({ operations }: { operations: AgentAuditOperationItem[] }) {
  return (
    <Table
      rowKey="id"
      size="small"
      dataSource={operations}
      pagination={false}
      expandable={{
        expandedRowRender: (record) => (
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <Text strong>请求参数（已脱敏）</Text>
              <div className="mt-2"><JsonBlock value={record.request_payload} /></div>
            </div>
            <div>
              <Text strong>执行结果</Text>
              <div className="mt-2"><JsonBlock value={record.response_payload} /></div>
              {record.error_message && (
                <Paragraph className="mb-0 mt-2" type="danger">
                  {record.error_message}
                </Paragraph>
              )}
            </div>
          </div>
        ),
      }}
      columns={[
        { title: '操作', dataIndex: 'operation', ellipsis: true },
        {
          title: '结果',
          dataIndex: 'status',
          width: 110,
          render: statusTag,
        },
        {
          title: '关联 ID',
          dataIndex: 'correlation_id',
          width: 210,
          ellipsis: true,
          render: (value: string) => <Text copyable>{value}</Text>,
        },
        {
          title: '时间',
          dataIndex: 'created_at',
          width: 170,
          render: formatTime,
        },
      ]}
    />
  )
}

export default function AgentAuditLogClient() {
  const { message } = App.useApp()
  const [items, setItems] = useState<AgentAuditSessionItem[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [channel, setChannel] = useState<string>()
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null)
  const [detail, setDetail] = useState<AgentAuditSessionDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await fetchAgentAuditSessions({
        page,
        pageSize,
        keyword: keyword || undefined,
        channel,
        startedAt: range?.[0].startOf('day').toISOString(),
        endedAt: range?.[1].endOf('day').toISOString(),
      })
      setItems(result.items || [])
      setTotal(result.total)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载审计日志失败')
    } finally {
      setLoading(false)
    }
  }, [channel, keyword, message, page, pageSize, range])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timeoutId)
  }, [load])

  const openDetail = async (record: AgentAuditSessionItem) => {
    setDetailLoading(true)
    try {
      setDetail(await fetchAgentAuditSession(record.id))
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载审计详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const columns = [
    {
      title: '用户',
      key: 'user',
      width: 190,
      render: (_: unknown, record: AgentAuditSessionItem) => (
        <div>
          <div className="font-medium text-[var(--color-charcoal)]">{record.user_name}</div>
          <Text type="secondary" className="text-[12px]">
            {record.department || record.username || '未填写部门'}
          </Text>
        </div>
      ),
    },
    {
      title: '对话',
      key: 'conversation',
      render: (_: unknown, record: AgentAuditSessionItem) => (
        <div className="min-w-0">
          <div className="truncate font-medium">{record.title || '未命名对话'}</div>
          <Text type="secondary" className="text-[12px]">
            {record.channel === 'feishu' ? '飞书' : 'Web'} · {record.id}
          </Text>
        </div>
      ),
    },
    {
      title: '活动',
      key: 'activity',
      width: 190,
      render: (_: unknown, record: AgentAuditSessionItem) => (
        <Space size={12}>
          <span>{record.message_count} 条消息</span>
          <span>{record.tool_call_count} 次操作</span>
        </Space>
      ),
    },
    {
      title: '异常',
      dataIndex: 'failed_operation_count',
      width: 85,
      render: (count: number) => count ? <Badge count={count} /> : <Text type="secondary">0</Text>,
    },
    {
      title: '最近活动',
      dataIndex: 'updated_at',
      width: 170,
      render: formatTime,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: statusTag,
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      fixed: 'right' as const,
      render: (_: unknown, record: AgentAuditSessionItem) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => void openDetail(record)}>
          查看
        </Button>
      ),
    },
  ]

  const detailMessages = detail?.messages ?? []
  const detailOperations = detail?.operations ?? []
  const detailConfirmations = detail?.confirmations ?? []
  const detailTabs = detail ? [
    {
      key: 'conversation',
      label: `对话记录 (${detailMessages.length})`,
      children: detailMessages.length ? (
        <Timeline
          items={detailMessages.map((item) => ({
            color: item.role === 'user' ? 'blue' : item.role === 'assistant' ? 'purple' : 'gray',
            children: (
              <div className="pb-3">
                <Space className="mb-2">
                  <Tag>{item.role === 'user' ? '用户' : item.role === 'assistant' ? 'Livzon' : item.role}</Tag>
                  <Text type="secondary">{formatTime(item.created_at)}</Text>
                </Space>
                <Paragraph className="mb-0 whitespace-pre-wrap">{item.content}</Paragraph>
              </div>
            ),
          }))}
        />
      ) : <Empty description="该会话没有消息记录" />,
    },
    {
      key: 'operations',
      label: `操作明细 (${detailOperations.length})`,
      children: detailOperations.length
        ? <OperationsTable operations={detailOperations} />
        : <Empty description="该会话没有调用工具" />,
    },
    {
      key: 'confirmations',
      label: `确认记录 (${detailConfirmations.length})`,
      children: detailConfirmations.length ? (
        <Timeline items={detailConfirmations.map((item) => ({
          color: item.status === 'executed' ? 'green' : item.status === 'rejected' ? 'red' : 'orange',
          children: (
            <div className="pb-3">
              <Space wrap><Text strong>{item.summary}</Text>{statusTag(item.status)}<Tag>{item.risk_level}</Tag></Space>
              <div className="mt-1 text-[12px] text-[var(--color-steel)]">{item.operation} · {formatTime(item.created_at)}</div>
              <div className="mt-2"><JsonBlock value={{ request: item.request_payload, result: item.result_payload }} /></div>
            </div>
          ),
        }))} />
      ) : <Empty description="该会话没有人工确认记录" />,
    },
    {
      key: 'context',
      label: '会话上下文',
      children: <JsonBlock value={detail.context} />,
    },
  ] : []

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="m-0 text-[20px] font-semibold text-[var(--color-charcoal)]">Livzon 对话审计</h2>
          <Text className="text-[13px] text-[var(--color-steel)]">
            按用户追溯对话、工具调用、确认决策和执行结果。敏感凭证不会在此显示。
          </Text>
        </div>
        <Space wrap>
          <Input
            allowClear
            value={keywordInput}
            prefix={<SearchOutlined />}
            placeholder="用户、部门或对话标题"
            style={{ width: 240 }}
            onChange={(event) => setKeywordInput(event.target.value)}
            onPressEnter={() => { setPage(1); setKeyword(keywordInput.trim()) }}
          />
          <Select
            allowClear
            placeholder="全部入口"
            style={{ width: 130 }}
            value={channel}
            options={[{ value: 'web', label: 'Web' }, { value: 'feishu', label: '飞书' }]}
            onChange={(value) => { setPage(1); setChannel(value) }}
          />
          <RangePicker
            value={range}
            onChange={(value) => { setPage(1); setRange(value as [Dayjs, Dayjs] | null) }}
          />
          <Button type="primary" onClick={() => { setPage(1); setKeyword(keywordInput.trim()) }}>查询</Button>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
        </Space>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        scroll={{ x: 1120 }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (value) => `共 ${value} 个会话`,
          onChange: (nextPage, nextPageSize) => {
            setPage(nextPageSize === pageSize ? nextPage : 1)
            setPageSize(nextPageSize)
          },
        }}
      />

      <Drawer
        open={!!detail || detailLoading}
        loading={detailLoading}
        width="min(960px, 92vw)"
        title="Livzon 对话审计详情"
        destroyOnHidden
        onClose={() => setDetail(null)}
      >
        {detail && (
          <div className="space-y-5">
            <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
              <Descriptions.Item label="用户">{detail.session.user_name}</Descriptions.Item>
              <Descriptions.Item label="部门">{detail.session.department || '-'}</Descriptions.Item>
              <Descriptions.Item label="对话">{detail.session.title || '未命名对话'}</Descriptions.Item>
              <Descriptions.Item label="入口">{detail.session.channel === 'feishu' ? '飞书' : 'Web'}</Descriptions.Item>
              <Descriptions.Item label="会话 ID" span={2}><Text copyable>{detail.session.id}</Text></Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatTime(detail.session.created_at)}</Descriptions.Item>
              <Descriptions.Item label="最近活动">{formatTime(detail.session.updated_at)}</Descriptions.Item>
            </Descriptions>
            <Tabs items={detailTabs} />
          </div>
        )}
      </Drawer>
    </div>
  )
}
