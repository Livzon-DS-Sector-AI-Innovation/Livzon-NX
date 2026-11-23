'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  App, Button, Drawer, Form, Input, Select, Space, Switch, Tag, Typography,
} from 'antd'
import { SaveOutlined, SecurityScanOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { fetchFeishuApps } from '@/lib/api/inspection-feishu'
import {
  fetchRepairConfig,
  testRepairConfig,
  updateRepairConfig,
  type RepairConfigDetail,
  type RepairConfigUpdateRequest,
} from '@/lib/api/repair-ledger'
import { parseFeishuBitableUrl } from '@/lib/feishu-url'
import type { FeishuAppSummary } from '@/types/inspection-feishu'

const MANUAL_APP = '__manual__'

type ConfigFormValues = {
  is_enabled: boolean
  /** 已登记应用 ID，或 MANUAL_APP（手动输入新应用） */
  feishu_app_id?: string
  app_id?: string
  app_secret?: string
  app_name?: string
  app_token: string
  table_id: string
  base_url?: string
}

function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  return dayjs(iso).format('YYYY-MM-DD HH:mm')
}

/** 设备检修页的飞书同步配置：每个车间一张维修记录表。 */
export function RepairLedgerConfigDrawer({
  workshopCode, workshopLabel, open, onClose, onSaved,
}: {
  workshopCode: string
  workshopLabel: string
  open: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const { message } = App.useApp()
  const [form] = Form.useForm<ConfigFormValues>()
  const [detail, setDetail] = useState<RepairConfigDetail | null>(null)
  const [apps, setApps] = useState<FeishuAppSummary[]>([])
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  // 保存或测试连接后 +1，重新拉取配置
  const [reloadKey, setReloadKey] = useState(0)
  // 加载态由 detail 是否已取回推导
  const loading = detail === null

  // 选中「手动输入新应用」时展开凭据输入区
  const manualMode = Form.useWatch('feishu_app_id', form) === MANUAL_APP

  // 打开时拉取最新配置与应用清单并回填表单
  useEffect(() => {
    if (!open) return
    let cancelled = false
    Promise.all([fetchRepairConfig(workshopCode), fetchFeishuApps()])
      .then(([config, appList]) => {
        if (cancelled) return
        setDetail(config)
        setApps(appList)
        form.setFieldsValue({
          is_enabled: config.is_enabled,
          feishu_app_id: config.feishu_app_id ?? undefined,
          app_id: '',
          app_secret: '',
          app_name: '',
          app_token: config.app_token,
          table_id: config.table_id,
          base_url: config.base_url,
        })
      })
      .catch((error: unknown) => {
        message.error((error as Error).message || '加载检修表配置失败')
      })
    return () => { cancelled = true }
  }, [open, workshopCode, form, message, reloadKey])

  // 关闭时清掉已取回的配置，下次打开重新进入加载态
  const handleClose = useCallback(() => {
    setDetail(null)
    onClose()
  }, [onClose])

  // 粘贴多维表格链接后自动拆出 App Token 与数据表 Table ID；
  // 知识库链接保留原样，由后端在保存时解析
  const handleLinkBlur = useCallback(() => {
    const raw = ((form.getFieldValue('app_token') as string | undefined) || '').trim()
    if (!raw.startsWith('http')) return
    const parsed = parseFeishuBitableUrl(raw)
    if (!parsed) {
      message.warning('无法识别该网址，请粘贴 /base/ 链接、/wiki/ 知识库链接或直接填写 App Token')
      return
    }
    const patch: Partial<ConfigFormValues> = { base_url: raw }
    if (!parsed.is_wiki) patch.app_token = parsed.app_token
    if (parsed.table_id) patch.table_id = parsed.table_id
    form.setFieldsValue(patch)
    message.success(
      parsed.is_wiki ? '已识别知识库链接，保存时自动解析' : '已从链接识别多维表格与数据表',
    )
  }, [form, message])

  const handleTableIdBlur = useCallback(() => {
    const raw = ((form.getFieldValue('table_id') as string | undefined) || '').trim()
    if (!raw.startsWith('http')) return
    const tableId = parseFeishuBitableUrl(raw)?.table_id
    if (tableId) form.setFieldValue('table_id', tableId)
  }, [form])

  const handleSave = useCallback(async () => {
    let values: ConfigFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    setSaving(true)
    try {
      const payload: RepairConfigUpdateRequest = {
        app_token: values.app_token.trim(),
        table_id: values.table_id.trim(),
        base_url: values.base_url?.trim() || '',
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
      await updateRepairConfig(workshopCode, payload)
      form.setFieldValue('app_secret', '')
      message.success('检修表配置已保存')
      setReloadKey((value) => value + 1)
      onSaved()
    } catch (error) {
      message.error((error as Error).message || '保存检修表配置失败')
    } finally {
      setSaving(false)
    }
  }, [workshopCode, form, message, onSaved])

  const handleTest = useCallback(async () => {
    setTesting(true)
    try {
      const result = await testRepairConfig(workshopCode)
      if (result.success) {
        message.success(result.message || '连接测试通过')
      } else {
        message.error(result.message || '连接测试未通过')
      }
      setReloadKey((value) => value + 1)
    } catch (error) {
      message.error((error as Error).message || '连接测试失败')
    } finally {
      setTesting(false)
    }
  }, [workshopCode, message])

  return (
    <Drawer
      title={`检修表同步配置 · ${workshopLabel}`}
      open={open}
      onClose={handleClose}
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
            <Button onClick={handleClose}>关闭</Button>
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
        {detail && (
          <div style={{ fontSize: 13, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            {detail.enabled
              ? <span style={{ color: '#1aae39' }}>● 同步已启用</span>
              : <span style={{ color: '#c0392b' }}>● 同步未启用</span>}
            {detail.last_test_status && (
              <span>
                最近测试：
                {detail.last_test_status === 'success'
                  ? <Tag color="success" style={{ marginLeft: 4 }}>成功</Tag>
                  : <Tag color="error" style={{ marginLeft: 4 }}>失败</Tag>}
                <span style={{ marginLeft: 4, color: '#b5b1a8' }}>
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

        <Form form={form} layout="vertical" requiredMark={false} disabled={loading}>
          <Form.Item
            name="is_enabled" label="启用自动同步"
            valuePropName="checked"
            extra="关闭后平台停止自动同步，已同步数据仍可查看"
          >
            <Switch />
          </Form.Item>
          <Form.Item
            name="feishu_app_id" label="飞书自建应用"
            rules={[{ required: true, message: '请选择已登记应用，或选择「手动输入新应用」' }]}
            extra="与设备巡检共用应用库；应用库为空时选「手动输入新应用」"
          >
            <Select
              placeholder="选择已登记的自建应用"
              allowClear
              showSearch
              optionFilterProp="label"
              options={[
                ...apps.map((a) => ({ value: a.id, label: `${a.name}（${a.app_id}）` })),
                { value: MANUAL_APP, label: '＋ 手动输入新应用' },
              ]}
            />
          </Form.Item>
          {manualMode && (
            <>
              <Form.Item
                name="app_name" label="应用名称（可选）"
                extra="保存后自动登记到应用库，其他车间下次可直接选择"
              >
                <Input placeholder="如：设备检修应用" maxLength={100} autoComplete="off" />
              </Form.Item>
              <Form.Item
                name="app_id" label="App ID"
                rules={[{ required: true, message: '请输入飞书应用 App ID' }]}
              >
                <Input placeholder="cli_xxxxxxxx" autoComplete="off" />
              </Form.Item>
              <Form.Item
                name="app_secret" label="App Secret"
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
            name="app_token" label="检修表链接"
            rules={[{ required: true, message: '请粘贴检修表链接，或填写 App Token' }]}
            extra="直接粘贴飞书多维表格里「维修记录」数据表的网址，粘贴后点一下空白处可自动识别"
          >
            <Input placeholder="https://xxx.feishu.cn/base/…?table=tbl…" onBlur={handleLinkBlur} />
          </Form.Item>
          <Form.Item
            name="table_id" label="数据表 Table ID"
            rules={[{ required: true, message: '请填写数据表 Table ID' }]}
            extra="粘贴上方链接后自动填写；也可以直接粘贴数据表链接"
          >
            <Input placeholder="tblxxxxxxxx" onBlur={handleTableIdBlur} />
          </Form.Item>
        </Form>
      </Space>
    </Drawer>
  )
}
