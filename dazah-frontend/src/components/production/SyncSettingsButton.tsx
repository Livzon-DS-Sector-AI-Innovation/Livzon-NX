'use client'

import {useState, useEffect, useCallback, useMemo} from 'react'
import { Button, Modal, Form, Input, AutoComplete, Typography, App, Alert, Space, Tag } from 'antd'
import { LinkOutlined, SyncOutlined, PlayCircleOutlined, ClockCircleOutlined } from '@ant-design/icons'
import {
  useProductionPermissions,
  type ProductionPageKey,
} from './useProductionPermissions'

const { Text } = Typography
const API = (p: string) => `/api/v1/production${p}`
const STORAGE_KEY = 'feishu_saved_apps'

// ── 飞书链接解析 ──

/** 链接解析结果 */
interface ParsedUrl {
  token: string      // 电子表格 token 或 bitable app_token
  sheetId: string    // 子表 sheet_id 或 table_id
  type: 'spreadsheet' | 'bitable' | 'unknown'
  url: string        // 原始链接
}

/**
 * 从飞书链接中提取 token 和 sheet/table ID
 *
 * 电子表格（两种格式）:
 *   https://xxx.feishu.cn/wiki/TOKEN?sheet=SHEET_ID
 *   https://xxx.feishu.cn/sheets/TOKEN?sheet=SHEET_ID
 * 多维表格:
 *   https://xxx.feishu.cn/base/TOKEN?table=TABLE_ID
 */
function parseFeishuUrl(raw: string): ParsedUrl | null {
  const url = raw.trim()
  if (!url) return null

  try {
    const u = new URL(url)

    // 多维表格: /base/TOKEN?table=xxx
    const baseMatch = u.pathname.match(/\/base\/([A-Za-z0-9_-]+)/)
    if (baseMatch) {
      const tableId = u.searchParams.get('table') || ''
      return { token: baseMatch[1], sheetId: tableId, type: 'bitable', url }
    }

    // 电子表格: /wiki/TOKEN?sheet=xxx 或 /sheets/TOKEN?sheet=xxx
    const sheetMatch = u.pathname.match(/\/(?:wiki|sheets)\/([A-Za-z0-9_-]+)/)
    if (sheetMatch) {
      const sheetId = u.searchParams.get('sheet') || ''
      return { token: sheetMatch[1], sheetId, type: 'spreadsheet', url }
    }

    return null
  } catch {
    return null
  }
}

interface SavedApp {
  id: string
  name: string
  app_id: string
  app_secret: string
}

function loadApps(): SavedApp[] {
  if (typeof window === 'undefined') return []
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { return [] }
}

function saveApps(apps: SavedApp[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(apps))
}

async function authFetch(url: string, options?: RequestInit, pageContextHeaders?: HeadersInit) {
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers, ...pageContextHeaders },
  })
  return res.json()
}

interface Props {
  productName: string
  syncTarget?: string
  onSync?: () => void
  autoSync?: boolean
  /** When supplied, the sync/config controls follow the reviewed page grant. */
  pageKey?: ProductionPageKey
  /** 数据表 ID 选填（留空自动同步多维表格中第一个数据表） */
  tableIdOptional?: boolean
}

export default function SyncSettingsButton({ productName, syncTarget = 'seed_culture', onSync, autoSync = false, pageKey, tableIdOptional = false }: Props) {
  const { message } = App.useApp()
  const permissions = useProductionPermissions(pageKey || 'production:overview')
  const canSync = !pageKey || permissions.canSync
  const [visible, setVisible] = useState(false)
  const [form] = Form.useForm()
  const [, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<any>(null)
  const [configId, setConfigId] = useState<string | null>(null)
  const [lastSync, setLastSync] = useState<string>('')
  const [apps, setApps] = useState<SavedApp[]>([])
  const [parsedUrl, setParsedUrl] = useState<ParsedUrl | null>(null)
  // 同步配置接口被多页面共享：显式携带页面上下文，
  // 不依赖 Referer 推断（生产网关可能剥离该头）
  const pageContextHeaders = useMemo(
    () => (pageKey ? { 'X-Dazah-Page-Key': pageKey } : undefined),
    [pageKey],
  )

  const open = async () => {
    if (!canSync) return
    const saved = loadApps()
    setApps(saved)
    setVisible(true); setTestResult(null); setParsedUrl(null); form.resetFields()
    setLoading(true)
    try {
      const res = await authFetch(API('/feishu-configs'), undefined, pageContextHeaders)
      if (res.code === 200) {
        const cfg = res.data.find((c: { product_name: string; sync_target: string; id: string; updated_at?: string }) => c.product_name === productName && c.sync_target === syncTarget)
        if (cfg) {
          setConfigId(cfg.id); setLastSync(cfg.updated_at)
          form.setFieldsValue({
            feishu_url: undefined,
            app_name: undefined,
            app_id: cfg.app_id,
            bitable_app_token: cfg.bitable_app_token,
            table_id: cfg.table_id,
          })
        }
      }
    } catch {} finally { setLoading(false) }
  }

  /** 粘贴/输入飞书链接，自动提取 token 和子表 ID */
  const handleUrlChange = (raw: string) => {
    if (!raw) { setParsedUrl(null); return }
    const parsed = parseFeishuUrl(raw)
    if (parsed) {
      setParsedUrl(parsed)
      form.setFieldsValue({
        bitable_app_token: parsed.token,
        table_id: parsed.sheetId,
      })
    } else {
      setParsedUrl(null)
    }
  }

  const handleAppSelect = (name: string) => {
    if (!name) {
      form.setFieldsValue({ app_id: undefined, app_secret: undefined })
      return
    }
    const app = apps.find(a => a.name === name)
    if (app) {
      form.setFieldsValue({ app_id: app.app_id, app_secret: app.app_secret })
    }
  }

  const handleSave = async () => {
    if (!canSync) return
    const vals = await form.validateFields()
    setSaving(true)
    try {
      const appName = vals.app_name
      if (appName && !apps.find(a => a.name === appName)) {
        const updated = [...apps, { id: Date.now().toString(), name: appName, app_id: vals.app_id, app_secret: vals.app_secret || '' }]
        saveApps(updated)
        setApps(updated)
      }

      const res = await authFetch(API('/feishu-configs'), {
        method: 'PUT', body: JSON.stringify({
          name: `${productName} - 飞书配置`, product_name: productName,
          app_id: vals.app_id, app_secret: vals.app_secret || '',
          bitable_app_token: vals.bitable_app_token, table_id: vals.table_id,
          sync_target: syncTarget, is_active: true,
        }),
      }, pageContextHeaders)
      if (res.code === 200) { message.success('保存成功'); setConfigId(res.data.id); setLastSync(res.data.updated_at) }
      else message.error(res.message || '保存失败')
    } catch { message.error('保存失败') } finally { setSaving(false) }
  }

  const handleTest = async () => {
    if (!canSync) return
    const vals = await form.validateFields()
    setTesting(true); setTestResult(null)
    try {
      const res = await authFetch(API('/feishu-configs/test'), {
        method: 'POST', body: JSON.stringify({
          app_id: vals.app_id, app_secret: vals.app_secret || '',
          bitable_app_token: vals.bitable_app_token, table_id: vals.table_id,
          product_name: '', name: '', sync_target: '',
        }),
      }, pageContextHeaders)
      setTestResult(res.data)
    } catch { message.error('测试失败') } finally { setTesting(false) }
  }

  const handleSync = useCallback(async () => {
    if (!canSync || !configId) return
    setSyncing(true)
    try {
      const res = await authFetch(API(`/feishu/tables/${configId}/sync`), { method: 'POST' }, pageContextHeaders)
      if (res.code === 200) {
        setLastSync(new Date().toISOString())
        onSync?.()
      }
    } catch { /* ignore */ } finally { setSyncing(false) }
  }, [canSync, configId, onSync, pageContextHeaders])

  // auto-sync every 5s when enabled
  const [autoSyncOn, setAutoSyncOn] = useState(autoSync)
  useEffect(() => {
    if (!autoSyncOn || !configId) return
    const timer = setInterval(() => { handleSync().catch(() => {}) }, 5000)
    return () => clearInterval(timer)
  }, [autoSyncOn, configId, handleSync])

  const typeLabel = parsedUrl
    ? parsedUrl.type === 'spreadsheet' ? '电子表格' : '多维表格'
    : null
  const typeColor = parsedUrl
    ? parsedUrl.type === 'spreadsheet' ? 'green' : 'blue'
    : undefined

  return (
    <>
      <Space size={4}>
        {canSync && <Button size="small" icon={<SyncOutlined spin={autoSyncOn} />} onClick={open} title="同步设置" />}
        {canSync && configId && (
          <Button size="small"
            type={autoSyncOn ? 'primary' : 'default'}
            icon={<ClockCircleOutlined />}
            title={autoSyncOn ? '自动同步中 (5s)' : '开启自动同步'}
            danger={autoSyncOn}
            onClick={() => setAutoSyncOn(!autoSyncOn)}
          />
        )}
      </Space>
      <Modal title={`${productName} · 飞书同步设置`} open={visible && canSync} onCancel={() => setVisible(false)} width={520}
        footer={[
          <Button key="test" icon={<PlayCircleOutlined />} loading={testing} onClick={handleTest}>测试连接</Button>,
          <Button key="sync" icon={<SyncOutlined />} loading={syncing} onClick={handleSync}>同步</Button>,
          <Button key="cancel" onClick={() => setVisible(false)}>取消</Button>,
          <Button key="save" type="primary" loading={saving} onClick={handleSave}>保存</Button>,
        ]}>
        <Form form={form} layout="vertical">
          {/* ── 飞书链接快捷输入 ── */}
          <Form.Item name="feishu_url" label="飞书链接（粘贴自动识别）">
            <Input
              placeholder="粘贴飞书表格链接，自动提取 Token 和子表 ID"
              prefix={<LinkOutlined />}
              allowClear
              onChange={e => handleUrlChange(e.target.value)}
              onPaste={e => {
                // 延迟执行，等粘贴内容写入后再解析
                setTimeout(() => {
                  const val = (e.target as HTMLInputElement).value
                  handleUrlChange(val)
                }, 0)
              }}
            />
          </Form.Item>
          {parsedUrl && (
            <div style={{ marginBottom: 16, marginTop: -8 }}>
              <Tag color={typeColor}>📊 {typeLabel}</Tag>
              <Text type="secondary" style={{ fontSize: 12 }}>
                Token: {parsedUrl.token.slice(0, 12)}... | 子表: {parsedUrl.sheetId}
              </Text>
            </div>
          )}

          <Form.Item name="app_name" label="飞书应用">
            <AutoComplete
              allowClear
              placeholder="输入名称或点开选历史"
              onChange={handleAppSelect}
              onClear={() => form.setFieldsValue({ app_id: undefined, app_secret: undefined })}
              options={apps.map(a => ({ value: a.name, label: `${a.name} (${a.app_id.slice(-6)})` }))}
            />
          </Form.Item>
          <Form.Item name="app_id" label="App ID" rules={[{ required: true, message: '请输入 App ID' }]}>
            <Input placeholder="选应用自动填入，或手动输入" />
          </Form.Item>
          <Form.Item name="app_secret" label="App Secret" rules={[{ required: true, message: '请输入 App Secret' }]}>
            <Input.Password placeholder="选应用自动填入，或手动输入" />
          </Form.Item>
          <Form.Item name="bitable_app_token" label="多维表格 Token"
            rules={[{ required: true, message: '请输入' }]}
            help={parsedUrl?.type === 'spreadsheet' ? '电子表格模式下即为表格 Token' : undefined}>
            <Input placeholder="从飞书 URL 获取，或粘贴链接自动填入" />
          </Form.Item>
          <Form.Item name="table_id" label="数据表 ID"
            rules={tableIdOptional ? [] : [{ required: true, message: '请输入' }]}
            help={
              tableIdOptional
                ? '留空自动同步多维表格中的第一个数据表'
                : parsedUrl?.type === 'spreadsheet'
                  ? '电子表格模式下即为子表 sheet_id'
                  : undefined
            }>
            <Input
              placeholder={
                tableIdOptional
                  ? '留空自动取第一个数据表，或粘贴链接自动填入'
                  : 'tblxxxxxxxxxxxx，或粘贴链接自动填入'
              }
            />
          </Form.Item>
        </Form>
        {lastSync && <Text type="secondary" style={{ fontSize: 12 }}>上次同步：{new Date(lastSync).toLocaleString()}</Text>}
        {testResult && (
          <Alert className="mt-2" type={testResult.ok ? 'success' : 'error'}
            title={testResult.ok ? '连接测试通过' : '连接测试失败'}
            description={testResult.steps?.map((s: any, i: number) => <div key={i}>{s.status === 'ok' ? '✅' : '❌'} {s.name}: {s.message}</div>)} />
        )}
      </Modal>
    </>
  )
}
