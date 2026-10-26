'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  App, Button, Drawer, Form, Input, Select, Space, Switch, Tag, Typography,
} from 'antd'
import {
  SaveOutlined, SecurityScanOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import {
  fetchFeishuApps,
  fetchInspectionFeishuConfig,
  testInspectionFeishuConfig,
  updateInspectionFeishuConfig,
} from '@/lib/api/inspection-feishu'
import { parseFeishuBitableUrl } from '@/lib/feishu-url'
import type {
  FeishuAppSummary,
  InspectionFeishuConfigDetail,
  InspectionFeishuConfigUpdateRequest,
} from '@/types/inspection-feishu'
import { InspectionQueryProvider } from './InspectionQueryProvider'

const C = {
  ink: 'var(--color-ink)', slate: 'var(--color-slate)', stone: 'var(--color-stone)',
  hairline: 'var(--color-hairline)', green: '#1aae39', red: '#c0392b',
}

const CONFIG_QUERY_KEY = ['equipment', 'inspection-feishu-config'] as const
const FEISHU_APPS_QUERY_KEY = ['equipment', 'feishu-apps'] as const
/** 下拉里的「手动输入新应用」哨兵值 */
const MANUAL_APP = '__manual__'
type ConfigFormValues = {
  is_enabled: boolean
  /** 已登记应用 ID，或 MANUAL_APP（手动输入新应用） */
  feishu_app_id?: string
  app_id?: string
  app_secret?: string
  app_name?: string
  app_token: string
  base_url?: string
  today_table_id: string
  history_table_id: string
  device_table_id: string
}

function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  return dayjs(iso).format('YYYY-MM-DD HH:mm')
}

/**
 * 设备巡检页未挂模块级 React Query Provider，抽屉自带 Provider，
 * 避免在无 QueryClient 上下文的页面上抛错触发路由错误边界。
 */
export function InspectionFeishuConfigDrawer(props: {
  workshopCode: string
  workshopLabel: string
  open: boolean
  onClose: () => void
  onSaved: () => void
}) {
  return (
    <InspectionQueryProvider>
      <InspectionFeishuConfigDrawerInner {...props} />
    </InspectionQueryProvider>
  )
}

function InspectionFeishuConfigDrawerInner({
  workshopCode, workshopLabel, open, onClose, onSaved,
}: {
  workshopCode: string
  workshopLabel: string
  open: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<ConfigFormValues>()
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  // 配置按车间隔离，缓存键与请求都带车间代码（memo 保持引用稳定，避免 effect 循环）
  const configQueryKey = useMemo(
    () => [...CONFIG_QUERY_KEY, workshopCode] as const,
    [workshopCode],
  )
  const configQuery = useQuery<InspectionFeishuConfigDetail>({
    queryKey: configQueryKey,
    queryFn: () => fetchInspectionFeishuConfig(workshopCode),
    enabled: open,
  })
  const detail = configQuery.data ?? null

  // 已登记应用清单：下拉选择直接复用凭据（与飞书配置页应用管理区同源）
  const appsQuery = useQuery<FeishuAppSummary[]>({
    queryKey: FEISHU_APPS_QUERY_KEY,
    queryFn: () => fetchFeishuApps(),
    enabled: open,
  })
  const apps = appsQuery.data ?? []

  // 哨兵值联动：选中「手动输入新应用」时展开凭据输入区
  const selectedApp = Form.useWatch('feishu_app_id', form)
  const manualMode = selectedApp === MANUAL_APP

  // 每次打开时拉取最新配置（含缓存场景），随后按数据回填表单
  useEffect(() => {
    if (open) {
      void queryClient.invalidateQueries({ queryKey: configQueryKey })
    }
  }, [open, queryClient, configQueryKey])

  useEffect(() => {
    if (!open || !configQuery.data) return
    form.setFieldsValue({
      is_enabled: configQuery.data.is_enabled,
      feishu_app_id: configQuery.data.feishu_app_id ?? undefined,
      app_id: '',
      app_secret: '',
      app_name: '',
      app_token: configQuery.data.app_token,
      base_url: configQuery.data.base_url ?? '',
      today_table_id: configQuery.data.today_table_id,
      history_table_id: configQuery.data.history_table_id,
      device_table_id: configQuery.data.device_table_id,
    })
  }, [open, configQuery.data, form])

  // 粘贴多维表格链接后自动提取 App Token；知识库链接保留原样由后端解析
  const handleTokenBlur = useCallback(() => {
    const raw = ((form.getFieldValue('app_token') as string | undefined) || '').trim()
    if (!raw.startsWith('http')) return
    const parsed = parseFeishuBitableUrl(raw)
    if (!parsed) {
      message.warning('无法识别该网址，请粘贴 /base/ 链接、/wiki/ 知识库链接或直接填写 App Token')
      return
    }
    if (parsed.is_wiki) {
      message.info('已识别知识库链接，保存时将自动解析为多维表格 App Token')
      return
    }
    form.setFieldValue('app_token', parsed.app_token)
    message.success('已从链接提取 App Token')
  }, [form, message])

  const handleSave = useCallback(async () => {
    let values: ConfigFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    setSaving(true)
    try {
      const payload: InspectionFeishuConfigUpdateRequest = {
        app_token: values.app_token.trim(),
        base_url: values.base_url?.trim() || '',
        today_table_id: values.today_table_id.trim(),
        history_table_id: values.history_table_id.trim(),
        device_table_id: values.device_table_id.trim(),
        is_enabled: values.is_enabled,
      }
      if (values.feishu_app_id && values.feishu_app_id !== MANUAL_APP) {
        payload.feishu_app_id = values.feishu_app_id
      } else {
        // 手动输入：App ID 已登记则后端直接关联；未登记则连同 Secret 登记为新应用
        payload.app_id = values.app_id?.trim() || ''
        payload.app_secret = values.app_secret?.trim() || null
        payload.app_name = values.app_name?.trim() || ''
      }
      await updateInspectionFeishuConfig(workshopCode, payload)
      form.setFieldValue('app_secret', '')
      await queryClient.invalidateQueries({ queryKey: configQueryKey })
      await queryClient.invalidateQueries({ queryKey: FEISHU_APPS_QUERY_KEY })
      message.success('飞书配置已保存')
      onSaved()
    } catch (error) {
      message.error((error as Error).message || '保存飞书配置失败')
    } finally {
      setSaving(false)
    }
  }, [workshopCode, form, message, onSaved, queryClient, configQueryKey])

  const handleTest = useCallback(async () => {
    setTesting(true)
    try {
      const result = await testInspectionFeishuConfig(workshopCode)
      if (result.success) {
        message.success(result.message || '连接测试通过')
      } else {
        message.error(result.message || '连接测试未通过')
      }
      await queryClient.invalidateQueries({ queryKey: configQueryKey })
    } catch (error) {
      message.error((error as Error).message || '连接测试失败')
    } finally {
      setTesting(false)
    }
  }, [workshopCode, message, queryClient, configQueryKey])

  return (
    <Drawer
      title={`飞书同步配置 · ${workshopLabel}`}
      open={open}
      onClose={onClose}
      size={480}
      destroyOnHidden
      footer={
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <Button
            icon={<SecurityScanOutlined />}
            loading={testing}
            onClick={() => void handleTest()}
          >
            测试连接（已保存配置）
          </Button>
          <Space>
            <Button onClick={onClose}>关闭</Button>
            <Button
              type="primary" icon={<SaveOutlined />}
              loading={saving}
              onClick={() => void handleSave()}
            >
              保存配置
            </Button>
          </Space>
        </div>
      }
    >
      <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
        {configQuery.error && (
          <Typography.Paragraph type="danger" style={{ fontSize: 13, marginBottom: 0 }}>
            加载飞书配置失败：{(configQuery.error as Error).message}
          </Typography.Paragraph>
        )}
        {detail && (
          <div style={{ fontSize: 13, color: C.slate, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <Tag color={detail.source === 'database' ? 'green' : 'default'}>
              {detail.source === 'database' ? '数据库配置' : '环境变量回退'}
            </Tag>
            {detail.enabled
              ? <span style={{ color: C.green }}>● 同步已启用</span>
              : <span style={{ color: C.red }}>● 同步未启用</span>}
            {detail.last_test_status && (
              <span>
                最近测试：
                {detail.last_test_status === 'success'
                  ? <Tag color="success" style={{ marginLeft: 4 }}>成功</Tag>
                  : <Tag color="error" style={{ marginLeft: 4 }}>失败</Tag>}
                <span style={{ color: C.stone, marginLeft: 4 }}>
                  {fmtDateTime(detail.last_tested_at)}
                </span>
              </span>
            )}
          </div>
        )}
        {detail?.last_test_error && (
          <Typography.Paragraph
            type="danger" style={{ fontSize: 12, marginBottom: 0 }}
            ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
          >
            {detail.last_test_error}
          </Typography.Paragraph>
        )}

        <Form
          form={form} layout="vertical" requiredMark={false}
          disabled={configQuery.isFetching && !detail}
        >
          <Form.Item
            name="is_enabled" label="启用镜像同步"
            valuePropName="checked"
            extra="关闭后平台停止自动同步，已同步数据仍可查看"
          >
            <Switch />
          </Form.Item>
          <Form.Item
            name="feishu_app_id"
            label="自建应用"
            rules={[{ required: true, message: '请选择已登记应用，或选择「手动输入新应用」' }]}
            extra={
              detail?.source === 'environment' && detail.app_id
                ? `当前生效 App ID（环境变量回退）：${detail.app_id}；选择应用保存后数据库配置优先`
                : '选择已登记应用直接复用凭据；应用库为空时选「手动输入新应用」'
            }
          >
            <Select
              placeholder="选择已登记的自建应用"
              allowClear
              showSearch
              optionFilterProp="label"
              loading={appsQuery.isLoading}
              options={[
                ...apps.map((a) => ({
                  value: a.id,
                  label: `${a.name}（${a.app_id}）`,
                })),
                { value: MANUAL_APP, label: '＋ 手动输入新应用' },
              ]}
            />
          </Form.Item>
          {manualMode && (
            <>
              <Form.Item
                name="app_name"
                label="应用名称（可选）"
                extra="保存后自动登记到应用库，其他车间下次可直接选择"
              >
                <Input placeholder="如：设备巡检应用" maxLength={100} autoComplete="off" />
              </Form.Item>
              <Form.Item
                name="app_id"
                label="App ID"
                rules={[{ required: true, message: '请输入飞书应用 App ID' }]}
              >
                <Input placeholder="cli_xxxxxxxx" autoComplete="off" />
              </Form.Item>
              <Form.Item
                name="app_secret"
                label="App Secret"
                rules={[{ required: true, message: '请输入飞书应用 App Secret' }]}
              >
                <Input.Password
                  placeholder="请输入飞书应用 App Secret"
                  autoComplete="new-password"
                />
              </Form.Item>
            </>
          )}
          <Form.Item
            name="app_token" label="多维表格 App Token"
            rules={[{ required: true, message: '请填写 App Token 或粘贴多维表格链接' }]}
            extra="支持直接粘贴 /base/ 链接或 /wiki/ 知识库链接，知识库链接在保存时自动解析"
          >
            <Input
              placeholder="bascnxxxxxxxx 或多维表格链接"
              onBlur={handleTokenBlur}
            />
          </Form.Item>
          <Form.Item
            name="base_url" label="多维表格完整链接（可选）"
            extra="粘贴带公司域名的完整链接（如 https://xxx.feishu.cn/base/…），飞书配置页可直接打开"
            rules={[{ pattern: /^https:\/\//, message: '链接需以 https:// 开头' }]}
          >
            <Input placeholder="https://xxx.feishu.cn/base/bascn…" autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="today_table_id" label="今日巡检表 Table ID"
            extra="对应飞书「今日巡检」子表，可粘贴子表链接自动提取"
          >
            <Input placeholder="tblxxxxxxxx" />
          </Form.Item>
          <Form.Item name="history_table_id" label="设备历史巡检记录表 Table ID">
            <Input placeholder="tblxxxxxxxx" />
          </Form.Item>
          <Form.Item
            name="device_table_id" label="设备档案表 Table ID"
            extra="未配置的表会记录同步失败，不影响其他表"
          >
            <Input placeholder="tblxxxxxxxx" />
          </Form.Item>
        </Form>
      </Space>
    </Drawer>
  )
}
