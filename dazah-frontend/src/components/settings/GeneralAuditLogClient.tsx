'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Alert,
  Button,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { EyeOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import {
  fetchGeneralAuditLog,
  fetchGeneralAuditLogs,
  type GeneralAuditCategory,
  type GeneralAuditLogDetail,
  type GeneralAuditLogItem,
} from '@/lib/api/generalAudit'
import { auditActionLabel, auditModuleLabels, auditRequestLabel, auditRiskLabel, auditStatusLabel, auditToolLabel } from './auditLabels'

const { Text } = Typography
const { RangePicker } = DatePicker

const categoryConfig: Record<GeneralAuditCategory, { title: string; description: string }> = {
  operations: {
    title: '用户操作审计',
    description: '按请求追溯平台用户的查询、下载和写入操作。',
  },
  permissions: {
    title: '权限与授权审计',
    description: '追溯用户模块权限、授权版本及 Livzon 有效访问范围的变更和查询。',
  },
  agent_tools: {
    title: 'Agent 工具审计',
    description: '查看工具执行、策略拒绝、人工确认、风险等级和脱敏后的执行结果。',
  },
  automations: {
    title: '自动化访问记录',
    description: '追踪对 Livzon 自动化定义、版本、计划、运行和事件的查询操作。',
  },
  feishu: {
    title: '飞书交互审计',
    description: '查看飞书资源操作、平台交互和业务模块的飞书记录变更，不展示敏感凭证。',
  },
  business: {
    title: '业务与平台事件',
    description: '查看业务模块及其他平台能力显式记录的资源操作、变更前后值和结果。',
  },
}

function formatTime(value: string) {
  return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
}

function actor(record: GeneralAuditLogItem) {
  return record.actor_name || record.actor_username || record.actor_user_id || '系统'
}

function summaryOf(record: GeneralAuditLogItem) {
  return record.summary || {}
}

function resultTag(record: GeneralAuditLogItem) {
  const status = String(summaryOf(record).status || summaryOf(record).result || '')
  if (status) {
    const color = ['succeeded', 'success', 'executed', 'processed'].includes(status)
      ? 'success'
      : ['failed', 'rejected', 'denied'].includes(status)
        ? 'error'
        : 'processing'
    return <Tag color={color}>{auditStatusLabel(status)}</Tag>
  }
  if (record.status_code === undefined || record.status_code === null) return <Text type="secondary">-</Text>
  return <Tag color={record.status_code < 400 ? 'success' : 'error'}>{record.status_code}</Tag>
}

function JsonBlock({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无数据" />
  return (
    <pre className="m-0 max-h-[360px] overflow-auto rounded-lg bg-[var(--color-surface)] p-3 text-[12px] leading-5 text-[var(--color-charcoal)]">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function detailSections(category: GeneralAuditCategory, detail: GeneralAuditLogDetail) {
  if (category === 'operations') {
    return [
      { title: '请求参数与内容', value: detail.extra?.request },
      { title: '响应摘要', value: detail.extra?.response },
      { title: '关联业务变更', value: Array.isArray(detail.extra?.related_events)
        ? detail.extra.related_events.map((event: Record<string, unknown>) => ({
          ...event,
          操作描述: auditActionLabel(String(event.action || ''), String(event.resource_type || detail.resource_type || '')),
        }))
        : detail.extra?.related_events },
      ...(detail.extra?.related_events_truncated
        ? [{ title: '关联记录提示', value: '仅展示前 20 条；可使用请求 ID 检索其余记录。' }]
        : []),
    ]
  }
  if (category === 'permissions') {
    return [
      { title: '变更前', value: detail.old_value },
      { title: '变更后', value: detail.new_value },
      { title: '授权上下文', value: detail.extra },
    ]
  }
  if (category === 'agent_tools') {
    return [
      { title: '脱敏请求', value: detail.extra?.request },
      { title: '执行结果', value: detail.new_value },
      { title: '执行上下文', value: detail.extra },
    ]
  }
  if (category === 'automations') {
    return [
      { title: '自动化操作结果', value: detail.new_value },
      { title: '自动化上下文', value: detail.extra },
    ]
  }
  if (category === 'feishu') {
    return [
      { title: '交互结果', value: detail.new_value },
      { title: '飞书事件标识', value: detail.extra },
    ]
  }
  return [
    { title: '变更前', value: detail.old_value },
    { title: '变更后', value: detail.new_value },
    { title: '操作上下文', value: detail.extra },
  ]
}

export default function GeneralAuditLogClient({ category }: { category: GeneralAuditCategory }) {
  const { message } = App.useApp()
  const [items, setItems] = useState<GeneralAuditLogItem[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null)
  const [module, setModule] = useState<string | undefined>()
  const [detail, setDetail] = useState<GeneralAuditLogDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const config = categoryConfig[category]

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await fetchGeneralAuditLogs({
        category,
        page,
        pageSize,
        keyword: keyword || undefined,
        startedAt: range?.[0].startOf('day').toISOString(),
        endedAt: range?.[1].endOf('day').toISOString(),
        module: category === 'operations' ? module : undefined,
      })
      setItems(result.items || [])
      setTotal(result.total)
      setLoadError(null)
    } catch (error) {
      const errorText = error instanceof Error ? error.message : '加载审计日志失败'
      setLoadError(errorText)
      message.error(errorText)
    } finally {
      setLoading(false)
    }
  }, [category, keyword, message, module, page, pageSize, range])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timeoutId)
  }, [load])

  const openDetail = async (record: GeneralAuditLogItem) => {
    setDetailLoading(true)
    try {
      setDetail(await fetchGeneralAuditLog(record.id))
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载审计详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const commonActionColumn = {
    title: '操作',
    dataIndex: 'action',
    ellipsis: true,
    render: (value: string, record: GeneralAuditLogItem) => auditActionLabel(value, record.resource_type),
  }
  const commonActorColumn = {
    title: '操作人',
    key: 'actor',
    width: 150,
    render: (_: unknown, record: GeneralAuditLogItem) => actor(record),
  }
  const commonTimeColumn = {
    title: '时间',
    dataIndex: 'created_at',
    width: 170,
    render: formatTime,
  }
  const viewColumn = {
    title: '详情',
    key: 'detail',
    width: 90,
    fixed: 'right' as const,
    render: (_: unknown, record: GeneralAuditLogItem) => (
      <Button type="link" icon={<EyeOutlined />} onClick={() => void openDetail(record)}>
        查看
      </Button>
    ),
  }

  const columns: ColumnsType<GeneralAuditLogItem> = (() => {
    if (category === 'operations') {
      return [
        commonActorColumn,
        { title: '操作', key: 'operation', ellipsis: true, render: (_: unknown, record) => auditRequestLabel(record) },
        { title: '目标对象', key: 'target', width: 180, ellipsis: true, render: (_: unknown, record) => String(summaryOf(record).target || '-') },
        { title: '影响模块', dataIndex: 'resource_type', width: 150, render: (value?: string | null) => value ? auditModuleLabels[value] || value : '-' },
        { title: '结果', key: 'result', width: 110, render: (_: unknown, record) => resultTag(record) },
        commonTimeColumn,
        viewColumn,
      ]
    }
    if (category === 'permissions') {
      return [
        commonActorColumn,
        commonActionColumn,
        {
          title: '目标用户/资源',
          dataIndex: 'resource_id',
          width: 220,
          ellipsis: true,
          render: (value?: string | null) => value || '-',
        },
        {
          title: '版本/原因',
          key: 'permission-summary',
          width: 180,
          render: (_: unknown, record) => summaryOf(record).reason
            ? String(summaryOf(record).reason)
            : summaryOf(record).grant_version !== undefined
              ? `版本 ${summaryOf(record).grant_version}`
              : '-',
        },
        commonTimeColumn,
        viewColumn,
      ]
    }
    if (category === 'agent_tools') {
      return [
        {
          title: '工具',
          key: 'operation',
          ellipsis: true,
          render: (_: unknown, record) => summaryOf(record).operation
            ? auditToolLabel(String(summaryOf(record).operation))
            : auditActionLabel(record.action, record.resource_type),
        },
        commonActorColumn,
        { title: '结果', key: 'result', width: 110, render: (_: unknown, record) => resultTag(record) },
        {
          title: '风险',
          key: 'risk',
          width: 90,
          render: (_: unknown, record) => summaryOf(record).risk_level
            ? <Tag>{auditRiskLabel(String(summaryOf(record).risk_level))}</Tag>
            : '-',
        },
        commonTimeColumn,
        viewColumn,
      ]
    }
    if (category === 'automations') {
      return [
        commonActionColumn,
        commonActorColumn,
        {
          title: '自动化 ID',
          dataIndex: 'resource_id',
          width: 220,
          ellipsis: true,
          render: (value?: string | null) => value || '-',
        },
        { title: '结果', key: 'result', width: 110, render: (_: unknown, record) => resultTag(record) },
        commonTimeColumn,
        viewColumn,
      ]
    }
    if (category === 'feishu') {
      return [
        commonActionColumn,
        commonActorColumn,
        { title: '结果', key: 'result', width: 110, render: (_: unknown, record) => resultTag(record) },
        {
          title: '消息/卡片标识',
          key: 'message',
          width: 240,
          ellipsis: true,
          render: (_: unknown, record) => String(summaryOf(record).message_id || summaryOf(record).card_id || summaryOf(record).feishu_log_id || summaryOf(record).run_id || '-'),
        },
        commonTimeColumn,
        viewColumn,
      ]
    }
    return [
      commonActionColumn,
      {
        title: '业务资源',
        key: 'resource',
        width: 220,
        ellipsis: true,
        render: (_: unknown, record) => record.resource_type || '-',
      },
      commonActorColumn,
      {
        title: '请求结果',
        key: 'request',
        width: 130,
        render: (_: unknown, record) => (
          <Space size={4}><Tag>{record.method || '内部操作'}</Tag>{resultTag(record)}</Space>
        ),
      },
      commonTimeColumn,
      viewColumn,
    ]
  })()

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="m-0 text-[20px] font-semibold text-[var(--color-charcoal)]">{config.title}</h2>
          <Text className="text-[13px] text-[var(--color-steel)]">{config.description}</Text>
        </div>
        <Space wrap>
          {category === 'operations' && (
            <Select
              allowClear
              value={module}
              placeholder="全部模块"
              style={{ width: 160 }}
              options={Object.entries(auditModuleLabels).map(([value, label]) => ({ value, label }))}
              onChange={(value) => { setPage(1); setModule(value) }}
            />
          )}
          <Input
            allowClear
            value={keywordInput}
            prefix={<SearchOutlined />}
            placeholder={category === 'operations' ? '操作、对象、请求 ID 或用户' : '操作、资源、路径或用户'}
            style={{ width: 240 }}
            onChange={(event) => setKeywordInput(event.target.value)}
            onPressEnter={() => { setPage(1); setKeyword(keywordInput.trim()) }}
          />
          <RangePicker
            value={range}
            onChange={(value) => { setPage(1); setRange(value as [Dayjs, Dayjs] | null) }}
          />
          <Button type="primary" onClick={() => { setPage(1); setKeyword(keywordInput.trim()) }}>查询</Button>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
        </Space>
      </div>

      {loadError && <Alert type="error" showIcon title="审计日志加载失败" description={loadError} action={<Button onClick={() => void load()}>重试</Button>} />}

      <Table
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        locale={{ emptyText: category === 'operations' ? '暂无操作记录' : '暂无数据' }}
        scroll={{ x: 980 }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (value) => `共 ${value} 条审计记录`,
          onChange: (nextPage, nextPageSize) => {
            setPage(nextPageSize === pageSize ? nextPage : 1)
            setPageSize(nextPageSize)
          },
        }}
      />

      <Drawer
        open={!!detail || detailLoading}
        loading={detailLoading}
        size="min(960px, 92vw)"
        title={`${config.title}详情`}
        destroyOnHidden
        onClose={() => setDetail(null)}
      >
        {detail && (
          <div className="space-y-5">
            <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
              <Descriptions.Item label="操作">{auditActionLabel(detail.action, detail.resource_type)}</Descriptions.Item>
              {category === 'operations' && <Descriptions.Item label="具体操作">{auditRequestLabel(detail)}</Descriptions.Item>}
              {category === 'agent_tools' && <Descriptions.Item label="具体工具">{auditToolLabel(String(detail.extra?.operation || summaryOf(detail).operation || ''))}</Descriptions.Item>}
              <Descriptions.Item label="原始动作标识"><Text copyable>{detail.action}</Text></Descriptions.Item>
              {category === 'agent_tools' && Boolean(detail.extra?.operation) && <Descriptions.Item label="原始工具标识"><Text copyable>{String(detail.extra?.operation)}</Text></Descriptions.Item>}
              <Descriptions.Item label="操作人">{actor(detail)}</Descriptions.Item>
              <Descriptions.Item label={category === 'operations' ? '影响模块' : '资源类型'}>{category === 'operations' ? auditModuleLabels[detail.resource_type || ''] || detail.resource_type || '-' : detail.resource_type || '-'}</Descriptions.Item>
              <Descriptions.Item label="资源 ID">{detail.resource_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="请求">{detail.method || '-'} {detail.path || ''}</Descriptions.Item>
              <Descriptions.Item label="请求结果">{detail.status_code ?? '-'}</Descriptions.Item>
              {category === 'operations' && <Descriptions.Item label="目标对象">{String(summaryOf(detail).target || '-')}</Descriptions.Item>}
              <Descriptions.Item label="耗时">{detail.duration_ms == null ? '-' : `${detail.duration_ms} ms`}</Descriptions.Item>
              <Descriptions.Item label="来源 IP">{detail.ip_address || '-'}</Descriptions.Item>
              <Descriptions.Item label="客户端">{detail.user_agent || '-'}</Descriptions.Item>
              <Descriptions.Item label="请求 ID">{detail.request_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="发生时间">{formatTime(detail.created_at)}</Descriptions.Item>
            </Descriptions>
            {detailSections(category, detail).map((section) => (
              <section key={section.title}>
                <Text strong>{section.title}</Text>
                <div className="mt-2"><JsonBlock value={section.value} /></div>
              </section>
            ))}
          </div>
        )}
      </Drawer>
    </div>
  )
}
