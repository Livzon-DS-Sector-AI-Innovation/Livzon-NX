'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  ApiOutlined,
  AuditOutlined,
  CloudServerOutlined,
  ExclamationCircleOutlined,
  LinkOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SettingOutlined,
  TeamOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  List,
  Pagination,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  createExternalIdentityBinding,
  exportAgentTrace,
  getAgentCapabilityImpacts,
  getAgentConfirmations,
  getAgentDeliveries,
  getAgentRuntimeOverview,
  getAgentToolCatalog,
  getAgentToolCatalogPage,
  getAgentTrace,
  getExternalIdentityBindings,
  getExternalIdentityConflicts,
  getFeishuAuthorizations,
  getLivzonFeishuConfig,
  getLivzonFeishuGatewayStatus,
  revokeFeishuAuthorization,
  restartLivzonFeishuGateway,
  saveLivzonFeishuConfig,
  setAgentToolEnabled,
  syncLivzonFeishuDirectory,
  testLivzonFeishuConfig,
  updateExternalIdentityBindingStatus,
  type AgentConfirmationGovernanceItem,
  type AgentToolCatalogEntry,
  type AgentTraceResult,
  type AgentRuntimeOverview,
  type ExternalIdentityBinding,
  type ExternalIdentityBindingCreate,
  type ExternalIdentityConflict,
  type FeishuAuthorization,
  type FeishuConfig,
  type FeishuConfigUpsert,
  type FeishuGatewayStatus,
  type FeishuGatewayRestartResult,
} from '@/actions/settings'
import { getUsers, type UserManagementItem } from '@/actions/users'
import MemoryGovernanceClient from './MemoryGovernanceClient'

const { Text, Title } = Typography

export const agentManagementTabKeys = [
  'overview',
  'feishu',
  'identity',
  'tools',
  'authorizations',
  'trace',
] as const

type CredentialsFormValues = Pick<
  FeishuConfigUpsert,
  | 'app_id'
  | 'app_secret'
  | 'tenant_id'
  | 'gateway_enabled'
  | 'allowed_group_chat_ids'
  | 'require_group_mention'
>

const statusLabels: Record<string, string> = {
  active: '有效',
  suspended: '暂停',
  revoked: '已撤销',
  pending: '待处理',
  executed: '已执行',
  rejected: '已拒绝',
  expired: '已过期',
  failed: '失败',
  connected: '已连接',
  inactive: '未启用',
  starting: '连接中',
  restarting: '重启中',
  retry: '等待重试',
  sent: '已发送',
  delivered: '已送达',
  recorded: '已记录',
  unknown: '未知',
}

const traceEventLabels: Record<string, string> = {
  tool_call: '工具调用',
  inbound_message: '收到消息',
  assistant_response: '助手回复',
  confirmation: '业务确认',
  domain_event: '业务事件',
  delivery: '消息投递',
  capability_search: '能力发现',
  audit_receipt: '审计收据',
}

const channelLabels: Record<string, string> = {
  feishu: '飞书',
  web: '网页',
}

function statusTag(status: string) {
  const color = status === 'active' || status === 'connected' || status === 'executed'
    ? 'green'
    : status === 'failed' || status === 'revoked'
      ? 'red'
      : status === 'pending' || status === 'starting' || status === 'restarting'
        ? 'orange'
        : 'default'
  return <Tag color={color}>{statusLabels[status] || status}</Tag>
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function downloadTextFile(filename: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function buildPayload(
  values: CredentialsFormValues,
  config: FeishuConfig | null,
): FeishuConfigUpsert {
  return {
    config_name: config?.config_name || 'Livzon 助手飞书设置',
    app_id: values.app_id.trim(),
    app_secret: values.app_secret?.trim() || undefined,
    tenant_id: values.tenant_id.trim(),
    gateway_enabled: values.gateway_enabled,
    allowed_group_chat_ids: values.allowed_group_chat_ids || [],
    require_group_mention: values.require_group_mention,
    sync_root_department_id: config?.sync_root_department_id,
    sync_member_department_id: config?.sync_member_department_id,
    is_active: config?.is_active ?? true,
  }
}

function Overview({
  config,
  status,
  health,
  onNavigate,
}: {
  config: FeishuConfig | null
  status: FeishuGatewayStatus | null
  health: AgentRuntimeOverview | null
  onNavigate: (key: string, traceId?: string) => void
}) {
  return (
    <Space direction="vertical" size={16} className="w-full">
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8} xl={6}>
          <Card><Statistic title="飞书网关" value={statusLabels[status?.gateway || ''] || status?.gateway || '未知'} /></Card>
        </Col>
        <Col xs={24} md={8} xl={6}>
          <Card><Statistic title="待写入审计事件" value={status?.outbox_depth ?? 0} /></Card>
        </Col>
        <Col xs={24} md={8} xl={6}>
          <Card><Statistic title="待确认" value={status?.pending_confirmations ?? 0} /></Card>
        </Col>
        <Col xs={24} md={8} xl={6}>
          <Card><Statistic title="待投递" value={status?.pending_deliveries ?? 0} /></Card>
        </Col>
      </Row>
      <Card title="运行版本与连接">
        <Descriptions column={{ xs: 1, md: 2, xl: 3 }} size="small">
          <Descriptions.Item label="连接状态">{statusTag(status?.gateway || 'unknown')}</Descriptions.Item>
          <Descriptions.Item label="配置版本">{status?.config_version ?? 0}</Descriptions.Item>
          <Descriptions.Item label="凭证版本">{status?.credential_version ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="重连次数">{status?.gateway_reconnects ?? 0}</Descriptions.Item>
          <Descriptions.Item label="当前消费者">{status?.event_consumer || '—'}</Descriptions.Item>
          <Descriptions.Item label="消费者数量">{status?.event_consumer_count ?? 0}</Descriptions.Item>
          <Descriptions.Item label="Hermes 发布版本">{status?.gateway_upstream?.release_tag || '—'}</Descriptions.Item>
          <Descriptions.Item label="代码版本">{status?.gateway_upstream?.commit_sha?.slice(0, 12) || '—'}</Descriptions.Item>
          <Descriptions.Item label="最近配置变更">{formatDate(config?.updated_at)}</Descriptions.Item>
          <Descriptions.Item label="配置变更人">{config?.updated_by || '—'}</Descriptions.Item>
        </Descriptions>
      </Card>
      {health?.latest_error_trace_id && (
        <Alert
          type="warning"
          showIcon
          title={`最近异常调用链路：${health.latest_error_trace_id}`}
          description={`发生时间：${formatDate(health.latest_error_at)}。这是最近一次失败记录，不代表当前仍异常；若重复出现或已影响业务，请查看完整链路。`}
          action={<Button size="small" onClick={() => onNavigate('trace', health.latest_error_trace_id || undefined)}>查看调用链路</Button>}
        />
      )}
      {health && (
        <Card title="自动化健康摘要">
          <Descriptions size="small">
            <Descriptions.Item label="待确认">{health.pending_confirmations}</Descriptions.Item>
            <Descriptions.Item label="失败投递">{health.failed_deliveries}</Descriptions.Item>
            <Descriptions.Item label="最近异常链路">{health.latest_error_trace_id || '无'}</Descriptions.Item>
          </Descriptions>
        </Card>
      )}
    </Space>
  )
}

function FeishuAccess({
  config,
  status,
  onSaved,
  onRestarted,
}: {
  config: FeishuConfig | null
  status: FeishuGatewayStatus | null
  onSaved: (value: FeishuConfig) => void
  onRestarted: (value: FeishuGatewayRestartResult) => void
}) {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm<CredentialsFormValues>()
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [diagnostic, setDiagnostic] = useState<Awaited<ReturnType<typeof testLivzonFeishuConfig>> | null>(null)
  const [operationFeedback, setOperationFeedback] = useState<{
    type: 'success' | 'error'
    title: string
    description: string
  } | null>(null)

  useEffect(() => {
    if (!config) return
    form.setFieldsValue({
      app_id: config.app_id,
      app_secret: '',
      tenant_id: config.tenant_id,
      gateway_enabled: config.gateway_enabled,
      allowed_group_chat_ids: config.allowed_group_chat_ids || [],
      require_group_mention: config.require_group_mention,
    })
  }, [config, form])

  const save = async () => {
    const values = await form.validateFields()
    const payload = buildPayload(values, config)
    modal.confirm({
      title: payload.gateway_enabled ? '确认更新飞书接入配置' : '确认停用 Hermes 飞书网关',
      icon: <ExclamationCircleOutlined />,
      content: payload.gateway_enabled
        ? '保存后 Hermes 将校验候选凭证并按新版本重建连接。失败时保留当前可用版本。'
        : '停用后丽珠智能助手将停止处理该飞书应用的消息。',
      okText: payload.gateway_enabled ? '确认保存' : '确认停用',
      okButtonProps: { danger: !payload.gateway_enabled },
      async onOk() {
        setSaving(true)
        setOperationFeedback(null)
        try {
          const result = await saveLivzonFeishuConfig(payload)
          onSaved(result)
          form.setFieldValue('app_secret', '')
          const description = `配置版本 ${result.config_version} 已写入，飞书网关${result.gateway_enabled ? '已启用' : '已停用'}。`
          setOperationFeedback({
            type: 'success',
            title: '飞书接入配置保存成功',
            description,
          })
          message.success({
            content: '飞书接入配置保存成功',
            duration: 4,
          })
        } catch (error) {
          const detail = error instanceof Error ? error.message : '未知错误'
          setOperationFeedback({
            type: 'error',
            title: '飞书接入配置保存失败',
            description: detail,
          })
          message.error({
            content: `保存失败：${detail}`,
            duration: 6,
          })
        } finally {
          setSaving(false)
        }
      },
    })
  }

  const test = async () => {
    const payload = buildPayload(await form.validateFields(), config)
    setTesting(true)
    try {
      const result = await testLivzonFeishuConfig(payload)
      setDiagnostic(result)
      if (result.status === 'error') message.error(result.message)
      else message.success(result.message)
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setOperationFeedback({
        type: 'error',
        title: '连通性诊断执行失败',
        description: detail,
      })
      message.error({
        content: `运行诊断失败：${detail}`,
        duration: 6,
      })
    } finally {
      setTesting(false)
    }
  }

  const restartGateway = () => {
    modal.confirm({
      title: '确认重启 Hermes 飞书 Gateway',
      icon: <ExclamationCircleOutlined />,
      content: (
        <Space direction="vertical" size={4}>
          <Text>该操作只重建飞书消息连接，不会重启整个 Hermes 服务，也不会拉取或发布新镜像。</Text>
          <Text type="secondary">重连期间飞书消息可能短暂延迟；待投递记录和审计数据不会被清空。</Text>
        </Space>
      ),
      okText: '确认重启',
      okButtonProps: { danger: true },
      async onOk() {
        setRestarting(true)
        setOperationFeedback(null)
        try {
          const result = await restartLivzonFeishuGateway()
          onRestarted(result)
          setOperationFeedback({
            type: 'success',
            title: '飞书 Gateway 重启成功',
            description: `连接已恢复，重连次数由 ${result.previous_reconnects} 增至 ${result.gateway_reconnects}，当前配置版本 ${result.config_version}。`,
          })
          message.success('飞书 Gateway 已重新建立连接')
        } catch (error) {
          const detail = error instanceof Error ? error.message : '未知错误'
          setOperationFeedback({
            type: 'error',
            title: '飞书 Gateway 重启失败',
            description: detail,
          })
          message.error({ content: `重启失败：${detail}`, duration: 6 })
        } finally {
          setRestarting(false)
        }
      },
    })
  }

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={14}>
        <Card title="飞书应用与网关">
          <Space className="mb-4" wrap>
            <Text strong>当前状态</Text>
            {statusTag(status?.gateway || 'unknown')}
            <Text type="secondary">配置版本 {status?.config_version ?? 0} · 重连 {status?.gateway_reconnects ?? 0}</Text>
          </Space>
          <Form form={form} layout="vertical">
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item name="app_id" label="应用编号（App ID）" rules={[{ required: true, message: '请输入应用编号' }]}>
                  <Input placeholder="cli_xxx" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item name="tenant_id" label="租户标识" rules={[{ required: true, message: '请输入租户标识' }]}>
                  <Input />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item
              name="app_secret"
              label="应用密钥（App Secret）"
              extra={config?.app_secret_configured ? '凭证已保存；留空表示不修改。' : '首次保存必须填写。'}
              rules={[{ required: !config?.app_secret_configured, message: '请输入应用密钥' }]}
            >
              <Input.Password autoComplete="new-password" placeholder="留空则不修改" />
            </Form.Item>
            <Form.Item name="allowed_group_chat_ids" label="允许接入的群聊" extra="输入飞书群聊编号（chat_id）；私聊不受此列表影响。">
              <Select mode="tags" tokenSeparators={[',', ' ']} placeholder="oc_xxx" />
            </Form.Item>
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item name="gateway_enabled" label="启用 Hermes 飞书网关" valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item name="require_group_mention" label="群聊必须 @丽珠智能助手" valuePropName="checked">
                  <Switch disabled />
                </Form.Item>
              </Col>
            </Row>
            <Space>
              <Button type="primary" loading={saving} onClick={() => void save()}>保存配置</Button>
              <Button icon={<ApiOutlined />} loading={testing} onClick={() => void test()}>运行诊断</Button>
              <Button
                danger
                icon={<ReloadOutlined />}
                loading={restarting}
                disabled={!config?.is_active || !status?.gateway_enabled}
                onClick={restartGateway}
              >
                重启飞书网关
              </Button>
            </Space>
            {operationFeedback && (
              <Alert
                className="mt-4"
                type={operationFeedback.type}
                showIcon
                closable
                title={operationFeedback.title}
                description={operationFeedback.description}
                onClose={() => setOperationFeedback(null)}
              />
            )}
          </Form>
        </Card>
      </Col>
      <Col xs={24} xl={10}>
        <Card title="连通性诊断">
          {diagnostic ? (
            <List
              dataSource={diagnostic.steps}
              renderItem={(step) => (
                <List.Item>
                  <List.Item.Meta
                    title={step.name}
                    description={(
                      <Space orientation="vertical" size={0}>
                        <Text type="secondary">{step.message}</Text>
                        {step.suggestion && <Text type="secondary">建议：{step.suggestion}</Text>}
                      </Space>
                    )}
                  />
                  {statusTag(step.status)}
                </List.Item>
              )}
            />
          ) : <Empty description="尚未运行诊断" />}
        </Card>
      </Col>
    </Row>
  )
}

function IdentityAdmission({ tenantId, appId }: { tenantId: string; appId: string }) {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm<ExternalIdentityBindingCreate>()
  const [items, setItems] = useState<ExternalIdentityBinding[]>([])
  const [users, setUsers] = useState<UserManagementItem[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState<string>()
  const [department, setDepartment] = useState<string>()
  const [activeDays, setActiveDays] = useState<number>()
  const [conflicts, setConflicts] = useState<ExternalIdentityConflict[]>([])
  const [syncing, setSyncing] = useState(false)
  const [syncFeedback, setSyncFeedback] = useState<{ status: 'ok' | 'warning'; message: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const feishuUsers = users.filter((user) =>
    Boolean(user.feishu_user_id || user.feishu_open_id || user.feishu_union_id),
  )

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [bindings, userPage, conflictItems] = await Promise.all([
        getExternalIdentityBindings({
          page,
          pageSize: 20,
          keyword,
          tenantId,
          status,
          department,
          activeSince: activeDays
            ? new Date(Date.now() - activeDays * 86_400_000).toISOString()
            : undefined,
        }),
        getUsers({ status: 'active' }),
        getExternalIdentityConflicts(),
      ])
      setItems(bindings.items)
      setTotal(bindings.total)
      setUsers(userPage.items)
      setConflicts(conflictItems)
    } finally {
      setLoading(false)
    }
  }, [activeDays, department, keyword, page, status, tenantId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])
  useEffect(() => {
    form.setFieldsValue({ tenant_id: tenantId, platform: 'feishu', app_fingerprint: appId, source: 'admin' })
  }, [appId, form, tenantId])

  const changeStatus = (item: ExternalIdentityBinding, next: ExternalIdentityBinding['status']) => {
    modal.confirm({
      title: next === 'active' ? '恢复身份绑定' : next === 'revoked' ? '撤销身份绑定' : '暂停身份绑定',
      content: next === 'active' ? '恢复后该飞书身份可以重新使用丽珠智能助手。' : '变更后该身份的新请求将立即失败关闭。',
      okButtonProps: { danger: next !== 'active' },
      async onOk() {
        await updateExternalIdentityBindingStatus(item.id, next)
        message.success('身份状态已更新')
        await load()
      },
    })
  }

  const syncDirectory = () => {
    modal.confirm({
      title: '同步飞书通讯录与身份绑定',
      content: '将读取已授权的飞书部门和用户，更新本地目录并为无冲突用户建立可信身份绑定。冲突项不会自动覆盖。',
      okText: '开始同步',
      async onOk() {
        setSyncing(true)
        try {
          const result = await syncLivzonFeishuDirectory()
          setSyncFeedback({ status: result.status, message: result.message })
          if (result.status === 'warning') message.warning(result.message)
          else message.success(result.message)
          await load()
        } catch (error) {
          message.error(error instanceof Error ? error.message : '飞书通讯录同步失败')
          throw error
        } finally {
          setSyncing(false)
        }
      },
    })
  }

  const columns: ColumnsType<ExternalIdentityBinding> = [
    {
      title: '本地用户',
      width: 220,
      render: (_, item) => item.local_user_name || item.local_user_id,
    },
    { title: '部门', dataIndex: 'local_user_department', width: 160, render: (value) => value || '—' },
    {
      title: '飞书身份',
      width: 220,
      render: (_, item) => item.external_open_id || item.external_union_id || item.external_user_id || '—',
    },
    { title: '租户', dataIndex: 'tenant_id', width: 130 },
    { title: '来源', dataIndex: 'source', width: 120 },
    { title: '最近活动', dataIndex: 'last_seen_at', width: 180, render: formatDate },
    { title: '状态', dataIndex: 'status', width: 100, render: statusTag },
    {
      title: '操作',
      fixed: 'right',
      width: 180,
      render: (_, item) => (
        <Space>
          {item.status !== 'active' && <Button type="link" onClick={() => changeStatus(item, 'active')}>恢复</Button>}
          {item.status === 'active' && <Button type="link" onClick={() => changeStatus(item, 'suspended')}>暂停</Button>}
          {item.status !== 'revoked' && <Button danger type="link" onClick={() => changeStatus(item, 'revoked')}>撤销</Button>}
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={16} className="w-full">
      <Card title="建立可信身份绑定">
        <Form
          form={form}
          layout="vertical"
          onFinish={async (values) => {
            const selectedUser = feishuUsers.find((user) => user.id === values.local_user_id)
            if (!selectedUser) {
              message.error('该用户尚未同步飞书身份，请先同步飞书目录')
              return
            }
            await createExternalIdentityBinding({
              ...values,
              external_user_id: selectedUser.feishu_user_id || undefined,
              external_open_id: selectedUser.feishu_open_id || undefined,
              external_union_id: selectedUser.feishu_union_id || undefined,
            })
            message.success('身份绑定已创建')
            form.resetFields(['local_user_id'])
            await load()
          }}
        >
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item
                name="local_user_id"
                label="飞书用户"
                extra="用户标识从已同步的飞书通讯录自动读取，无需手工填写 Open ID 或 Union ID。"
                rules={[{ required: true, message: '请选择飞书用户' }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder="选择已同步的飞书用户"
                  notFoundContent="暂无已同步的飞书用户，请先同步飞书目录"
                  options={feishuUsers.map((user) => ({
                    value: user.id,
                    label: `${user.name}（${user.department || '未设置部门'}）`,
                  }))}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="tenant_id" hidden><Input /></Form.Item>
          <Form.Item name="platform" hidden><Input /></Form.Item>
          <Form.Item name="app_fingerprint" hidden><Input /></Form.Item>
          <Form.Item name="source" hidden><Input /></Form.Item>
          <Button type="primary" htmlType="submit">创建绑定</Button>
        </Form>
      </Card>
      <Card title="身份与准入目录">
        {syncFeedback && (
          <Alert
            className="mb-4"
            showIcon
            closable
            type={syncFeedback.status === 'ok' ? 'success' : 'warning'}
            title={syncFeedback.message}
            onClose={() => setSyncFeedback(null)}
          />
        )}
        <Space className="mb-4" wrap>
          <Input.Search
            allowClear
            placeholder="搜索飞书外部 ID"
            onSearch={(value) => { setPage(1); setKeyword(value) }}
            style={{ width: 280 }}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 140 }}
            options={[
              { value: 'active', label: '有效' },
              { value: 'suspended', label: '暂停' },
              { value: 'revoked', label: '已撤销' },
            ]}
            onChange={(value) => { setPage(1); setStatus(value) }}
          />
          <Select
            allowClear
            showSearch
            placeholder="部门"
            style={{ width: 180 }}
            options={Array.from(new Set(users.map((user) => user.department).filter(Boolean))).map((value) => ({ value, label: value }))}
            onChange={(value) => { setPage(1); setDepartment(value) }}
          />
          <Select
            allowClear
            placeholder="最近活动"
            style={{ width: 150 }}
            options={[
              { value: 7, label: '最近 7 天' },
              { value: 30, label: '最近 30 天' },
              { value: 90, label: '最近 90 天' },
            ]}
            onChange={(value) => { setPage(1); setActiveDays(value) }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
          <Button type="primary" icon={<TeamOutlined />} loading={syncing} onClick={syncDirectory}>同步飞书目录</Button>
        </Space>
        <Table rowKey="id" columns={columns} dataSource={items} loading={loading} pagination={false} scroll={{ x: 1100 }} />
        <Pagination className="mt-4 text-right" current={page} pageSize={20} total={total} onChange={setPage} />
      </Card>
      <Card title={`身份冲突工作台（${conflicts.length}）`}>
        {conflicts.length ? (
          <Table
            rowKey={(item) => `${item.local_user_id}-${item.conflicting_binding_id}`}
            pagination={false}
            dataSource={conflicts}
            columns={[
              { title: '本地用户', dataIndex: 'local_user_name' },
              { title: '部门', dataIndex: 'department', render: (value) => value || '—' },
              { title: '外部标识', dataIndex: 'external_identifier', ellipsis: true },
              {
                title: '冲突类型',
                dataIndex: 'conflict_type',
                render: (value) => value === 'external_owned_by_other' ? '外部身份已绑定其他用户' : '本地用户已有不同绑定',
              },
              { title: '冲突绑定', dataIndex: 'conflicting_binding_id', ellipsis: true },
            ]}
            scroll={{ x: 900 }}
          />
        ) : <Empty description="未发现身份绑定冲突" />}
      </Card>
    </Space>
  )
}

function ToolGovernance() {
  const { message, modal } = App.useApp()
  const [items, setItems] = useState<AgentToolCatalogEntry[]>([])
  const [moduleOptions, setModuleOptions] = useState<string[]>([])
  const [selected, setSelected] = useState<AgentToolCatalogEntry | null>(null)
  const [impacts, setImpacts] = useState<Array<Record<string, unknown>>>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [keyword, setKeyword] = useState('')
  const [module, setModule] = useState<string>()
  const [risk, setRisk] = useState<string>()
  const [status, setStatus] = useState<string>()
  const [loading, setLoading] = useState(false)
  const selectedOutputSchemaSource = selected?.output_schema?.['x-dazah-schema-source']
  const selectedOutputSchemaIsInferred = selectedOutputSchemaSource === 'return_annotation'

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [catalog, impactRows] = await Promise.all([
        getAgentToolCatalogPage({ page, pageSize: 20, keyword, module, riskLevel: risk, status }),
        getAgentCapabilityImpacts(),
      ])
      setItems(catalog.items)
      setTotal(catalog.total)
      setImpacts(impactRows)
    } finally {
      setLoading(false)
    }
  }, [keyword, module, page, risk, status])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])
  useEffect(() => {
    let active = true
    void getAgentToolCatalog().then((catalog) => {
      if (!active) return
      setModuleOptions(
        Array.from(new Set(catalog.map((item) => item.module || 'platform'))).sort(),
      )
    })
    return () => {
      active = false
    }
  }, [])

  const toggle = (item: AgentToolCatalogEntry, enabled: boolean) => {
    const affected = impacts.filter((impact) => impact.operation === item.operation)
    modal.confirm({
      title: enabled ? '启用 Agent 能力' : '紧急禁用 Agent 能力',
      content: enabled
        ? `确认启用 ${item.operation}。`
        : `禁用后模型、Skill 和自动化均不能调用该能力。当前识别到 ${affected.length} 个自动化影响项。`,
      okButtonProps: { danger: !enabled },
      async onOk() {
        await setAgentToolEnabled(item.operation, enabled)
        message.success(enabled ? '能力已启用' : '能力已禁用')
        await load()
      },
    })
  }

  const columns: ColumnsType<AgentToolCatalogEntry> = [
    { title: 'Operation', dataIndex: 'operation', width: 250, ellipsis: true },
    { title: '摘要', dataIndex: 'summary', width: 280, ellipsis: true },
    { title: '模块', dataIndex: 'module', width: 110, render: (value) => value || 'platform' },
    { title: '版本', dataIndex: 'version', width: 90 },
    { title: '读写', dataIndex: 'write', width: 80, render: (value) => value ? <Tag color="orange">写</Tag> : <Tag>读</Tag> },
    { title: '风险', dataIndex: 'risk_level', width: 90, render: (value) => <Tag color={value === 'high' ? 'red' : value === 'medium' ? 'orange' : 'blue'}>{value}</Tag> },
    { title: '确认', dataIndex: 'confirmation_required', width: 80, render: (value) => value ? '需要' : '无需' },
    { title: '状态', dataIndex: 'status', width: 90, render: statusTag },
    {
      title: '操作',
      fixed: 'right',
      width: 150,
      render: (_, item) => (
        <Space>
          <Button type="link" onClick={() => setSelected(item)}>详情</Button>
          <Switch checked={item.status === 'active'} onChange={(value) => toggle(item, value)} />
        </Space>
      ),
    },
  ]

  return (
    <Card title="企业能力目录与策略">
      <MemoryGovernanceClient />
      <Divider />
      <Space className="mb-4" wrap>
        <Input.Search placeholder="搜索 operation 或摘要" allowClear style={{ width: 280 }} onSearch={(value) => { setPage(1); setKeyword(value) }} />
        <Select aria-label="模块" allowClear placeholder="模块" style={{ width: 140 }} options={moduleOptions.map((value) => ({ value }))} onChange={(value) => { setPage(1); setModule(value) }} />
        <Select allowClear placeholder="风险" style={{ width: 120 }} options={['low', 'medium', 'high'].map((value) => ({ value }))} onChange={(value) => { setPage(1); setRisk(value) }} />
        <Select allowClear placeholder="状态" style={{ width: 120 }} options={[{ value: 'active', label: '有效' }, { value: 'disabled', label: '停用' }]} onChange={(value) => { setPage(1); setStatus(value) }} />
      </Space>
      <Table rowKey="operation" columns={columns} dataSource={items} loading={loading} pagination={false} scroll={{ x: 1350 }} />
      <Pagination className="mt-4 text-right" current={page} pageSize={20} total={total} onChange={setPage} />
      <Drawer title={selected?.operation || '能力详情'} width={680} open={!!selected} onClose={() => setSelected(null)}>
        {selected && (
          <Space direction="vertical" className="w-full">
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="摘要">{selected.summary}</Descriptions.Item>
              <Descriptions.Item label="模块">{selected.module || 'platform'}</Descriptions.Item>
              <Descriptions.Item label="版本">{selected.version}</Descriptions.Item>
              <Descriptions.Item label="状态">{statusTag(selected.status)}</Descriptions.Item>
              <Descriptions.Item label="读写">{selected.write ? <Tag color="orange">写</Tag> : <Tag>读</Tag>}</Descriptions.Item>
              <Descriptions.Item label="风险"><Tag color={selected.risk_level === 'high' ? 'red' : selected.risk_level === 'medium' ? 'orange' : 'blue'}>{selected.risk_level}</Tag></Descriptions.Item>
              <Descriptions.Item label="人工确认">{selected.confirmation_required ? '需要' : '无需'}</Descriptions.Item>
              <Descriptions.Item label="权限键">{selected.permission_key || '—'}</Descriptions.Item>
              <Descriptions.Item label="超时">{selected.timeout_seconds} 秒</Descriptions.Item>
              <Descriptions.Item label="幂等">{selected.idempotent ? '是' : '否'}</Descriptions.Item>
              <Descriptions.Item label="受影响自动化">{impacts.filter((item) => item.operation === selected.operation).length}</Descriptions.Item>
            </Descriptions>
            <Title level={5}>输入数据结构</Title>
            <pre className="max-h-72 overflow-auto rounded bg-slate-50 p-3 text-xs">{JSON.stringify(selected.input_schema, null, 2)}</pre>
            <Space>
              <Title level={5} className="!mb-0">输出数据结构</Title>
              <Tag color={selectedOutputSchemaIsInferred ? 'gold' : 'green'}>
                {selectedOutputSchemaIsInferred ? '通用契约 · 待细化' : '字段级契约'}
              </Tag>
            </Space>
            {selectedOutputSchemaIsInferred && (
              <Alert
                type="warning"
                showIcon
                title="当前数据结构由处理程序的返回类型推导，仅保证容器类型；字段级输出仍需由业务模块补充。"
              />
            )}
            <pre className="max-h-72 overflow-auto rounded bg-slate-50 p-3 text-xs">{JSON.stringify(selected.output_schema, null, 2)}</pre>
          </Space>
        )}
      </Drawer>
    </Card>
  )
}

function AuthorizationConfirmation() {
  const { message, modal } = App.useApp()
  const [userId, setUserId] = useState('')
  const [grants, setGrants] = useState<FeishuAuthorization[]>([])
  const [confirmations, setConfirmations] = useState<AgentConfirmationGovernanceItem[]>([])
  const [confirmationStatus, setConfirmationStatus] = useState<string>()

  const loadConfirmations = useCallback(async () => {
    const result = await getAgentConfirmations({ pageSize: 50, status: confirmationStatus })
    setConfirmations(result.items)
  }, [confirmationStatus])
  useEffect(() => {
    const timer = window.setTimeout(() => void loadConfirmations(), 0)
    return () => window.clearTimeout(timer)
  }, [loadConfirmations])

  const grantColumns: ColumnsType<FeishuAuthorization> = [
    { title: '资源', dataIndex: 'resource', ellipsis: true },
    { title: '动作', dataIndex: 'action', width: 150 },
    { title: '风险', dataIndex: 'risk', width: 90, render: (value) => <Tag>{value}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', width: 180, render: (value: number) => new Date(value * 1000).toLocaleString() },
    {
      title: '操作',
      width: 100,
      render: (_, item) => (
        <Button
          danger
          type="link"
          onClick={() => modal.confirm({
            title: '撤销记忆授权',
            content: '撤销后该资源的下一次写操作将重新要求用户确认。',
            okButtonProps: { danger: true },
            async onOk() {
              await revokeFeishuAuthorization(item.id, userId)
              setGrants(await getFeishuAuthorizations(userId))
              message.success('授权已撤销')
            },
          })}
        >
          撤销
        </Button>
      ),
    },
  ]
  const confirmationColumns: ColumnsType<AgentConfirmationGovernanceItem> = [
    { title: '摘要', dataIndex: 'summary', ellipsis: true },
    { title: 'Operation', dataIndex: 'operation', width: 230, ellipsis: true },
    { title: '风险', dataIndex: 'risk_level', width: 90, render: (value) => <Tag>{value}</Tag> },
    { title: '状态', dataIndex: 'status', width: 100, render: statusTag },
    { title: '创建时间', dataIndex: 'created_at', width: 180, render: formatDate },
    { title: '过期时间', dataIndex: 'expires_at', width: 180, render: formatDate },
  ]

  return (
    <Space direction="vertical" size={16} className="w-full">
      <Card title="Hermes 飞书记忆授权">
        <Space className="mb-4">
          <Input value={userId} onChange={(event) => setUserId(event.target.value)} placeholder="本地用户编号（UUID）" style={{ width: 340 }} />
          <Button icon={<SearchOutlined />} disabled={!userId.trim()} onClick={async () => setGrants(await getFeishuAuthorizations(userId.trim()))}>查询授权</Button>
        </Space>
        <Alert className="mb-4" type="info" showIcon title="高风险操作不允许记忆授权；撤销不会执行或回滚已经完成的操作。" />
        <Table rowKey="id" columns={grantColumns} dataSource={grants} pagination={false} />
      </Card>
      <Card title="业务确认记录">
        <Select
          allowClear
          placeholder="状态"
          style={{ width: 140 }}
          options={['pending', 'executed', 'rejected', 'expired', 'failed'].map((value) => ({ value, label: statusLabels[value] }))}
          onChange={setConfirmationStatus}
          className="mb-4"
        />
        <Table rowKey="id" columns={confirmationColumns} dataSource={confirmations} scroll={{ x: 1050 }} />
      </Card>
    </Space>
  )
}

function TraceDelivery({
  traceId,
  trace,
  onTraceIdChange,
  onQuery,
}: {
  traceId: string
  trace: AgentTraceResult | null
  onTraceIdChange: (value: string) => void
  onQuery: (traceId: string) => Promise<void>
}) {
  const { message } = App.useApp()
  const [deliveryStatus, setDeliveryStatus] = useState<string>()
  const [deliveries, setDeliveries] = useState<Array<Record<string, unknown>>>([])
  const [deliveryLoading, setDeliveryLoading] = useState(false)
  const [deliveryError, setDeliveryError] = useState<string>()

  const loadDeliveries = useCallback(async () => {
    setDeliveryLoading(true)
    setDeliveryError(undefined)
    try {
      const result = await getAgentDeliveries(deliveryStatus)
      const source = Array.isArray(result) ? result : Array.isArray(result.items) ? result.items : []
      setDeliveries(source as Array<Record<string, unknown>>)
    } catch (error) {
      const detail = error instanceof Error ? error.message : '加载投递队列失败'
      setDeliveryError(detail)
      message.error(detail)
    } finally {
      setDeliveryLoading(false)
    }
  }, [deliveryStatus, message])
  useEffect(() => {
    const timer = window.setTimeout(() => void loadDeliveries(), 0)
    return () => window.clearTimeout(timer)
  }, [loadDeliveries])

  const deliveryColumns: ColumnsType<Record<string, unknown>> = [
    { title: '投递编号', dataIndex: 'id', width: 230, ellipsis: true },
    { title: '运行编号', dataIndex: 'run_id', width: 230, ellipsis: true },
    { title: '渠道', dataIndex: 'channel', width: 90, render: (value) => channelLabels[String(value)] || String(value) },
    { title: '状态', dataIndex: 'status', width: 110, render: (value) => statusTag(String(value)) },
    { title: '尝试次数', dataIndex: 'attempt_count', width: 100 },
    { title: '错误码', dataIndex: 'last_error_code', width: 180, ellipsis: true },
    { title: '飞书消息 ID', dataIndex: 'external_message_id', width: 200, ellipsis: true },
  ]

  return (
    <Space direction="vertical" size={16} className="w-full">
      <Card title="调用链路查询">
        <Space.Compact className="mb-4 w-full max-w-[720px]">
          <Input value={traceId} onChange={(event) => onTraceIdChange(event.target.value)} placeholder="输入调用链路编号或运行编号" />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            disabled={!traceId.trim()}
            onClick={() => onQuery(traceId.trim())}
          >
            查询
          </Button>
        </Space.Compact>
        {trace ? (
          <>
            <Descriptions size="small" className="mb-4">
              <Descriptions.Item label="工具调用">{trace.counts.tool_calls}</Descriptions.Item>
              <Descriptions.Item label="会话事件">{trace.counts.messages}</Descriptions.Item>
              <Descriptions.Item label="确认">{trace.counts.confirmations}</Descriptions.Item>
              <Descriptions.Item label="领域事件">{trace.counts.domain_events}</Descriptions.Item>
              <Descriptions.Item label="投递">{trace.counts.deliveries}</Descriptions.Item>
              <Descriptions.Item label="能力发现">{trace.counts.capability_searches}</Descriptions.Item>
              <Descriptions.Item label="审计收据">{trace.counts.audit_receipts}</Descriptions.Item>
            </Descriptions>
            <Button
              className="mb-4"
              onClick={async () => {
                try {
                  const exported = await exportAgentTrace(trace.trace_id)
                  downloadTextFile(exported.filename, exported.content)
                  message.success('已导出脱敏链路诊断文件')
                } catch (error) {
                  message.error(error instanceof Error ? error.message : '调用链路导出失败')
                }
              }}
            >
              导出安全诊断
            </Button>
            <List
              dataSource={trace.timeline}
              locale={{ emptyText: '该调用链路暂无事件' }}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta title={`${traceEventLabels[item.type] || item.type} · ${item.summary}`} description={`${formatDate(item.occurred_at)} · ${item.error_code || '无错误码'}`} />
                  {statusTag(item.status)}
                </List.Item>
              )}
            />
          </>
        ) : <Empty description="输入链路编号查询完整调用过程" />}
      </Card>
      <Card title="飞书投递队列">
        <Select
          allowClear
          placeholder="投递状态"
          style={{ width: 160 }}
          options={['pending', 'retry', 'sent', 'delivered', 'failed'].map((value) => ({ value, label: statusLabels[value] }))}
          onChange={setDeliveryStatus}
          className="mb-4"
        />
        <Table
          rowKey={(item) => String(item.id)}
          columns={deliveryColumns}
          dataSource={deliveries}
          loading={deliveryLoading}
          locale={{ emptyText: deliveryError || '暂无自动任务投递记录' }}
          scroll={{ x: 1150 }}
        />
      </Card>
    </Space>
  )
}

export default function FeishuSettingsClient() {
  const { message } = App.useApp()
  const [activeKey, setActiveKey] = useState('overview')
  const [config, setConfig] = useState<FeishuConfig | null>(null)
  const [status, setStatus] = useState<FeishuGatewayStatus | null>(null)
  const [health, setHealth] = useState<AgentRuntimeOverview | null>(null)
  const [traceQuery, setTraceQuery] = useState<{
    traceId: string
    result: AgentTraceResult | null
  }>({ traceId: '', result: null })
  const [loading, setLoading] = useState(true)

  const queryTrace = useCallback(async (traceId: string) => {
    const normalizedTraceId = traceId.trim()
    if (!normalizedTraceId) return
    setTraceQuery({ traceId: normalizedTraceId, result: null })
    try {
      const result = await getAgentTrace(normalizedTraceId)
      setTraceQuery({ traceId: normalizedTraceId, result })
    } catch (error) {
      message.error(error instanceof Error ? error.message : '调用链路查询失败')
    }
  }, [message])

  const loadOverview = useCallback(async () => {
    setLoading(true)
    const [configResult, statusResult, healthResult] = await Promise.allSettled([
      getLivzonFeishuConfig(),
      getLivzonFeishuGatewayStatus(),
      getAgentRuntimeOverview(),
    ])
    if (configResult.status === 'fulfilled') setConfig(configResult.value)
    else message.error('加载飞书配置失败')
    if (statusResult.status === 'fulfilled') setStatus(statusResult.value)
    if (healthResult.status === 'fulfilled') setHealth(healthResult.value)
    setLoading(false)
  }, [message])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadOverview(), 0)
    return () => window.clearTimeout(timer)
  }, [loadOverview])

  const items = [
    {
      key: 'overview',
      label: <Space><CloudServerOutlined />运行总览</Space>,
      children: <Overview config={config} status={status} health={health} onNavigate={(key, traceId) => { if (traceId) void queryTrace(traceId); setActiveKey(key) }} />,
    },
    {
      key: 'feishu',
      label: <Space><LinkOutlined />飞书接入</Space>,
      children: (
        <FeishuAccess
          config={config}
          status={status}
          onSaved={(value) => { setConfig(value); void loadOverview() }}
          onRestarted={() => { void loadOverview() }}
        />
      ),
    },
    {
      key: 'identity',
      label: <Space><TeamOutlined />身份与准入</Space>,
      children: config
        ? <IdentityAdmission tenantId={config.tenant_id} appId={config.app_id} />
        : <Alert type="warning" showIcon title="请先完成飞书接入配置" />,
    },
    {
      key: 'tools',
      label: <Space><ToolOutlined />能力目录与策略</Space>,
      children: <ToolGovernance />,
    },
    {
      key: 'authorizations',
      label: <Space><SafetyCertificateOutlined />授权与确认</Space>,
      children: <AuthorizationConfirmation />,
    },
    {
      key: 'trace',
      label: <Space><AuditOutlined />调用链路与投递诊断</Space>,
      children: (
        <TraceDelivery
          traceId={traceQuery.traceId}
          trace={traceQuery.result}
          onTraceIdChange={(traceId) => setTraceQuery({ traceId, result: null })}
          onQuery={queryTrace}
        />
      ),
    },
  ]

  return (
    <div className="w-full">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <Title level={3} style={{ margin: 0 }}>
            <SettingOutlined className="mr-2" />
            Livzon Agent管理
          </Title>
          <Text type="secondary">统一管理助手编排服务（Hermes）、飞书接入、可信身份、企业能力、授权确认与调用链路。</Text>
        </div>
        <Button loading={loading} icon={<ReloadOutlined />} onClick={() => void loadOverview()}>刷新运行状态</Button>
      </div>
      {status?.gateway === 'failed' && (
        <Alert type="error" showIcon title="Hermes 飞书网关连接失败" description="请先在“飞书接入”运行诊断，再通过“调用链路与投递诊断”定位失败环节。" className="mb-4" />
      )}
      <Tabs activeKey={activeKey} onChange={setActiveKey} items={items} />
    </div>
  )
}

export {
  AuthorizationConfirmation,
  FeishuAccess,
  IdentityAdmission,
  Overview,
  ToolGovernance,
  TraceDelivery,
}
