'use client'

import { useCallback, useEffect, useState } from 'react'

import { ApiOutlined, LinkOutlined, SaveOutlined } from '@ant-design/icons'
import { App, Button, Card, Input, Select, Space, Switch, Tag, Typography } from 'antd'

/** 把「别名=规范车间名」多行文本解析为映射（容错中文等号/缺失等号）。 */
export function parseWorkshopAliasText(text: string): Record<string, string> {
  const aliases: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const normalized = line.trim()
    if (!normalized) continue
    const separator = normalized.includes('=') ? '=' : '＝'
    const [alias, canonical] = normalized.split(separator)
    if (alias?.trim() && canonical?.trim()) {
      aliases[alias.trim()] = canonical.trim()
    }
  }
  return aliases
}

export function formatWorkshopAliasText(aliases: Record<string, string>): string {
  return Object.entries(aliases ?? {})
    .map(([alias, canonical]) => `${alias}=${canonical}`)
    .join('\n')
}

import {
  getSafetyPageFeishuConfigs,
  resolveSafetyPageFeishuUrl,
  saveSafetyPageFeishuConfig,
  testSafetyPageFeishuConfig,
} from '@/actions/safety'
import PlatformNotice from '@/components/shared/PlatformNotice'
import type { components } from '@/types/generated/schema'

type PageFeishuConfigItem = components['schemas']['PageFeishuConfigItem']
type ResolvedFeishuTable = components['schemas']['ResolvedFeishuTable']

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '未测试'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '未测试'
  return parsed.toLocaleString('zh-CN', { hour12: false })
}

function renderTestTag(status: string | null | undefined) {
  if (status === 'success') return <Tag color="success">绑定正常</Tag>
  if (status === 'failed') return <Tag color="error">绑定失败</Tag>
  return <Tag>未测试</Tag>
}

function PageTableConfigItem({
  item,
  onSaved,
}: {
  item: PageFeishuConfigItem
  onSaved: (next: PageFeishuConfigItem) => void
}) {
  const { message } = App.useApp()
  const [appToken, setAppToken] = useState(item.app_token ?? '')
  const [tableId, setTableId] = useState(item.table_id ?? '')
  const [viewId, setViewId] = useState(item.view_id ?? '')
  const [hiddenFields, setHiddenFields] = useState<string[]>(item.hidden_field_names ?? [])
  const [aliasesText, setAliasesText] = useState(
    formatWorkshopAliasText(item.workshop_aliases ?? {})
  )
  const [enabled, setEnabled] = useState(item.is_enabled)
  const [linkInput, setLinkInput] = useState('')
  const [tables, setTables] = useState<ResolvedFeishuTable[]>([])
  const [fieldOptions, setFieldOptions] = useState<string[]>([])
  const [resolving, setResolving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleResolve = useCallback(async () => {
    if (!linkInput.trim()) {
      message.warning('请先粘贴多维表格链接')
      return
    }
    setResolving(true)
    const res = await resolveSafetyPageFeishuUrl(linkInput.trim())
    setResolving(false)
    if (res.code === 200 && res.data) {
      setAppToken(res.data.app_token)
      setTables(res.data.tables ?? [])
      if (res.data.table_id) setTableId(res.data.table_id)
      if (res.data.view_id) setViewId(res.data.view_id)
      message.success(
        res.data.tables?.length
          ? `已解析，找到 ${res.data.tables.length} 个子表，请确认 Table ID`
          : '已解析链接，未列出子表（可在飞书文档中把应用添加为协作者后重试）'
      )
    } else {
      message.error(res.message || '解析链接失败')
    }
  }, [linkInput, message])

  const handleTest = useCallback(async () => {
    setTesting(true)
    const res = await testSafetyPageFeishuConfig(item.page_key)
    setTesting(false)
    if (res.code === 200 && res.data) {
      if (res.data.success) {
        message.success(res.data.message || '绑定正常')
      } else {
        message.error(res.data.message || '绑定测试失败')
      }
      setFieldOptions((res.data.fields ?? []).map((field) => field.name))
      const refreshed = await getSafetyPageFeishuConfigs()
      const next = refreshed.data?.items.find((row) => row.page_key === item.page_key)
      if (next) onSaved(next)
    } else {
      message.error(res.message || '测试失败')
    }
  }, [item.page_key, message, onSaved])

  const handleSave = useCallback(async () => {
    if (!appToken.trim() || !tableId.trim()) {
      message.warning('请填写 App Token 与 Table ID')
      return
    }
    setSaving(true)
    const res = await saveSafetyPageFeishuConfig(item.page_key, {
      app_token: appToken.trim(),
      table_id: tableId.trim(),
      view_id: viewId.trim() || null,
      hidden_field_names: hiddenFields,
      workshop_aliases: parseWorkshopAliasText(aliasesText),
      is_enabled: enabled,
    })
    setSaving(false)
    if (res.code === 200 && res.data) {
      message.success('页面数据表绑定已保存')
      onSaved(res.data)
    } else {
      message.error(res.message || '保存失败')
    }
  }, [aliasesText, appToken, enabled, hiddenFields, item.page_key, message, onSaved, tableId, viewId])

  return (
    <Card
      title={`${item.page_name}（${item.route_path}）`}
      extra={
        <Space>
          <Button
            icon={<ApiOutlined />}
            onClick={() => void handleTest()}
            loading={testing}
          >
            测试绑定
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={() => void handleSave()}
            loading={saving}
          >
            保存
          </Button>
        </Space>
      }
    >
      <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
        <Space.Compact block>
          <Button disabled style={{ cursor: 'default', width: 140 }}>
            多维表格链接
          </Button>
          <Input
            value={linkInput}
            placeholder="粘贴多维表格链接（/base/ 或 /wiki/），自动解析 app_token 与 table_id"
            onChange={(event) => setLinkInput(event.target.value)}
            onPressEnter={() => void handleResolve()}
          />
          <Button icon={<LinkOutlined />} onClick={() => void handleResolve()} loading={resolving}>
            解析
          </Button>
        </Space.Compact>
        {tables.length ? (
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              子表
            </Button>
            <Select
              style={{ width: '100%' }}
              placeholder="选择该链接下的子表"
              value={tables.some((table) => table.table_id === tableId) ? tableId : undefined}
              options={tables.map((table) => ({
                value: table.table_id,
                label: `${table.table_name}（${table.table_id}）`,
              }))}
              onChange={(value) => setTableId(value)}
            />
          </Space.Compact>
        ) : null}
        <Space.Compact block>
          <Button disabled style={{ cursor: 'default', width: 140 }}>
            App Token
          </Button>
          <Input
            value={appToken}
            placeholder="多维表格 app_token（链接中 /base/ 后一段）"
            onChange={(event) => setAppToken(event.target.value)}
          />
        </Space.Compact>
        <Space.Compact block>
          <Button disabled style={{ cursor: 'default', width: 140 }}>
            Table ID
          </Button>
          <Input
            value={tableId}
            placeholder="数据表 table_id（链接中 table= 参数，tbl 开头）"
            onChange={(event) => setTableId(event.target.value)}
          />
        </Space.Compact>
        <Space.Compact block>
          <Button disabled style={{ cursor: 'default', width: 140 }}>
            View ID
          </Button>
          <Input
            value={viewId}
            placeholder="视图 view_id（仅记录，页面展示该表全部记录）"
            onChange={(event) => setViewId(event.target.value)}
          />
        </Space.Compact>
        <Space.Compact block>
          <Button disabled style={{ cursor: 'default', width: 140 }}>
            隐藏字段
          </Button>
          <Select
            mode="multiple"
            allowClear
            style={{ width: '100%' }}
            placeholder={
              fieldOptions.length
                ? '选择页面不展示的字段（先「测试绑定」获取字段清单）'
                : '先点「测试绑定」获取字段清单'
            }
            value={hiddenFields}
            options={fieldOptions.map((name) => ({ value: name, label: name }))}
            onChange={(value) => setHiddenFields(value)}
          />
        </Space.Compact>
        <Space.Compact block>
          <Button disabled style={{ cursor: 'default', width: 140 }}>
            车间别名归一
          </Button>
          <Input.TextArea
            value={aliasesText}
            autoSize={{ minRows: 3, maxRows: 10 }}
            placeholder={'每行一条：别名=规范车间名\n例如：DR提炼=201二车间（DR）'}
            onChange={(event) => setAliasesText(event.target.value)}
          />
        </Space.Compact>
        <Space size={12} wrap>
          <Typography.Text>启用该页面的表格镜像</Typography.Text>
          <Switch
            aria-label="启用页面表格镜像"
            checked={enabled}
            onChange={setEnabled}
          />
          {renderTestTag(item.last_test_status)}
          <Typography.Text type="secondary">
            最近测试：{formatDateTime(item.last_tested_at)}
            {item.last_test_field_count
              ? `（字段 ${item.last_test_field_count} 个 / 记录 ${item.last_test_record_count ?? 0} 条）`
              : ''}
          </Typography.Text>
        </Space>
        {item.last_test_error ? (
          <PlatformNotice type="warning" title={item.last_test_error} />
        ) : null}
        <Typography.Text type="secondary">
          列与数据来自飞书实时表结构，页面不写死字段；在页面上的修改会直接写回该多维表格。
          需先把安全模块飞书应用添加为该多维表格的协作者。
        </Typography.Text>
      </Space>
    </Card>
  )
}

export default function PageFeishuTableConfigCard() {
  const [items, setItems] = useState<PageFeishuConfigItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void (async () => {
      const res = await getSafetyPageFeishuConfigs()
      if (res.code === 200 && res.data) setItems(res.data.items ?? [])
      setLoading(false)
    })()
  }, [])

  if (loading) return null
  if (!items.length) {
    return (
      <PlatformNotice
        type="info"
        title="暂无可配置的镜像页"
        description="后端未登记支持飞书多维表格镜像的页面。"
      />
    )
  }

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      {items.map((item) => (
        <PageTableConfigItem
          key={item.page_key}
          item={item}
          onSaved={(next) =>
            setItems((prev) =>
              prev.map((row) => (row.page_key === next.page_key ? next : row))
            )
          }
        />
      ))}
    </Space>
  )
}
