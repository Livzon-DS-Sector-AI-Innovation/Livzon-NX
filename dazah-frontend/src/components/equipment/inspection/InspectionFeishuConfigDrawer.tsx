'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  App, Button, Drawer, Form, Input, Space, Switch, Tag, Typography,
} from 'antd'
import {
  SaveOutlined, SecurityScanOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import {
  fetchInspectionFeishuConfig,
  testInspectionFeishuConfig,
  updateInspectionFeishuConfig,
} from '@/lib/api/inspection-feishu'
import { parseFeishuBitableUrl } from '@/lib/feishu-url'
import type {
  InspectionFeishuConfigDetail,
  InspectionFeishuConfigUpdateRequest,
} from '@/types/inspection-feishu'
import { InspectionQueryProvider } from './InspectionQueryProvider'

const C = {
  ink: '#1a1a1a', slate: '#5d5b54', stone: '#a4a097',
  hairline: '#e5e3df', green: '#1aae39', red: '#c0392b',
}

const CONFIG_QUERY_KEY = ['equipment', 'inspection-feishu-config'] as const

type ConfigFormValues = {
  is_enabled: boolean
  app_id: string
  app_secret?: string
  app_token: string
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
  open, onClose, onSaved,
}: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<ConfigFormValues>()
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const configQuery = useQuery<InspectionFeishuConfigDetail>({
    queryKey: CONFIG_QUERY_KEY,
    queryFn: fetchInspectionFeishuConfig,
    enabled: open,
  })
  const detail = configQuery.data ?? null

  // 每次打开时拉取最新配置（含缓存场景），随后按数据回填表单
  useEffect(() => {
    if (open) {
      void queryClient.invalidateQueries({ queryKey: CONFIG_QUERY_KEY })
    }
  }, [open, queryClient])

  useEffect(() => {
    if (!open || !configQuery.data) return
    form.setFieldsValue({
      is_enabled: configQuery.data.is_enabled,
      app_id: configQuery.data.app_id,
      app_secret: '',
      app_token: configQuery.data.app_token,
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
        app_id: values.app_id.trim(),
        app_secret: values.app_secret?.trim() || null,
        app_token: values.app_token.trim(),
        today_table_id: values.today_table_id.trim(),
        history_table_id: values.history_table_id.trim(),
        device_table_id: values.device_table_id.trim(),
        is_enabled: values.is_enabled,
      }
      await updateInspectionFeishuConfig(payload)
      form.setFieldValue('app_secret', '')
      await queryClient.invalidateQueries({ queryKey: CONFIG_QUERY_KEY })
      message.success('飞书配置已保存')
      onSaved()
    } catch (error) {
      message.error((error as Error).message || '保存飞书配置失败')
    } finally {
      setSaving(false)
    }
  }, [form, message, onSaved, queryClient])

  const handleTest = useCallback(async () => {
    setTesting(true)
    try {
      const result = await testInspectionFeishuConfig()
      if (result.success) {
        message.success(result.message || '连接测试通过')
      } else {
        message.error(result.message || '连接测试未通过')
      }
      await queryClient.invalidateQueries({ queryKey: CONFIG_QUERY_KEY })
    } catch (error) {
      message.error((error as Error).message || '连接测试失败')
    } finally {
      setTesting(false)
    }
  }, [message, queryClient])

  return (
    <Drawer
      title="飞书同步配置"
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
            name="app_id" label="App ID"
            rules={[{ required: true, message: '请输入飞书应用 App ID' }]}
          >
            <Input placeholder="cli_xxxxxxxx" autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="app_secret" label="App Secret"
            extra={
              detail?.app_secret_configured
                ? `已保存（${detail.app_secret_masked}），留空保持不变`
                : '首次保存必填'
            }
          >
            <Input.Password
              placeholder={detail?.app_secret_configured ? '留空保持当前 Secret 不变' : '请输入飞书应用 App Secret'}
              autoComplete="new-password"
            />
          </Form.Item>
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
