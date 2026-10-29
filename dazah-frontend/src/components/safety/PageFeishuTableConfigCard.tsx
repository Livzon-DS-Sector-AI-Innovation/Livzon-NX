'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'

import { ApiOutlined, LinkOutlined, SaveOutlined, SyncOutlined } from '@ant-design/icons'
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
  syncSafetyPageFeishuConfig,
  testSafetyPageFeishuConfig,
} from '@/actions/safety'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { SAFETY_PAGE_TABLE_KEYS } from '@/lib/safety-page-tables'
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

function renderSyncTag(status: string | null | undefined) {
  if (status === 'success') return <Tag color="success">镜像已同步</Tag>
  if (status === 'failed') return <Tag color="error">镜像同步失败</Tag>
  return <Tag>镜像未同步</Tag>
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
  const [subTableIds, setSubTableIds] = useState<string[]>(
    (item.sub_tables ?? []).map((table) => table.table_id)
  )
  const [aliasesText, setAliasesText] = useState(
    formatWorkshopAliasText(item.workshop_aliases ?? {})
  )
  // 超储计算列（危化品统计表页专用：存量/上限/品名列）
  const supportsOverLimit = item.page_key === SAFETY_PAGE_TABLE_KEYS.hazchemMsds
  const [overLimitQuantity, setOverLimitQuantity] = useState(
    item.over_limit_quantity_field ?? undefined
  )
  const [overLimitLimit, setOverLimitLimit] = useState(
    item.over_limit_limit_field ?? undefined
  )
  const [overLimitName, setOverLimitName] = useState(
    item.over_limit_name_field ?? undefined
  )
  const [enabled, setEnabled] = useState(item.is_enabled)
  const [mirrored, setMirrored] = useState(item.is_mirrored)
  const [linkInput, setLinkInput] = useState('')
  const [tables, setTables] = useState<ResolvedFeishuTable[]>([])
  const [fieldOptions, setFieldOptions] = useState<string[]>([])
  const [resolving, setResolving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)

  // 页签子表选项目录：解析链接返回的子表清单；绑定未换 Base 时并入已保存页签，
  // 让用户不重新解析链接也能取消/保留现有页签。
  const bindingChanged = (appToken.trim() || '') !== (item.app_token ?? '')
  const tableCatalog = useMemo(() => {
    const catalog = new Map<string, string>()
    for (const table of tables) catalog.set(table.table_id, table.table_name)
    if (!bindingChanged) {
      for (const table of item.sub_tables ?? []) {
        if (!catalog.has(table.table_id)) catalog.set(table.table_id, table.tab_name)
      }
    }
    return catalog
  }, [tables, item.sub_tables, bindingChanged])
  const selectedSubTables = useMemo(
    () =>
      subTableIds
        .filter((id) => id !== tableId.trim() && tableCatalog.has(id))
        .map((id) => {
          const existing = (item.sub_tables ?? []).find((table) => table.table_id === id)
          return {
            table_id: id,
            tab_name: tableCatalog.get(id) ?? existing?.tab_name ?? id,
            hidden_field_names: existing?.hidden_field_names ?? [],
          }
        }),
    [subTableIds, tableId, tableCatalog, item.sub_tables]
  )

  const handleResolve = useCallback(async () => {
    if (!linkInput.trim()) {
      message.warning('请先粘贴多维表格链接')
      return
    }
    setResolving(true)
    const res = await resolveSafetyPageFeishuUrl(linkInput.trim())
    setResolving(false)
    if (res.code === 200 && res.data) {
      // 换绑了另一个多维表格时，旧 Base 的页签子表不再有意义，清空重选
      if ((res.data.app_token ?? '') !== appToken) setSubTableIds([])
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
  }, [appToken, linkInput, message])

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

  const handleSync = useCallback(async () => {
    setSyncing(true)
    const res = await syncSafetyPageFeishuConfig(item.page_key)
    setSyncing(false)
    if (res.code === 200 && res.data) {
      message.success(
        `镜像同步完成（${res.data.last_sync_record_count ?? 0} 条记录）`
      )
      onSaved(res.data)
    } else {
      message.error(res.message || '镜像同步失败')
    }
  }, [item.page_key, message, onSaved])

  const handleSave = useCallback(async () => {
    if (!appToken.trim() || !tableId.trim()) {
      message.warning('请填写 App Token 与 Table ID')
      return
    }
    if (
      supportsOverLimit &&
      Boolean(overLimitQuantity ?? overLimitLimit) &&
      !(overLimitQuantity && overLimitLimit)
    ) {
      message.warning('超储计算的「存量列」与「上限列」需同时选择或同时清空')
      return
    }
    setSaving(true)
    const res = await saveSafetyPageFeishuConfig(item.page_key, {
      app_token: appToken.trim(),
      table_id: tableId.trim(),
      view_id: viewId.trim() || null,
      hidden_field_names: hiddenFields,
      sub_tables: selectedSubTables,
      workshop_aliases: parseWorkshopAliasText(aliasesText),
      is_enabled: enabled,
      is_mirrored: mirrored,
      ...(supportsOverLimit
        ? {
            over_limit_quantity_field: overLimitQuantity ?? null,
            over_limit_limit_field: overLimitLimit ?? null,
            over_limit_name_field: overLimitName ?? null,
          }
        : {}),
    })
    setSaving(false)
    if (res.code === 200 && res.data) {
      message.success('页面数据表绑定已保存')
      onSaved(res.data)
    } else {
      message.error(res.message || '保存失败')
    }
  }, [
    aliasesText,
    appToken,
    enabled,
    hiddenFields,
    item.page_key,
    message,
    mirrored,
    onSaved,
    overLimitLimit,
    overLimitName,
    overLimitQuantity,
    selectedSubTables,
    supportsOverLimit,
    tableId,
    viewId,
  ])

  return (
    <Card
      title={`${item.page_name}（${item.route_path}）`}
      extra={
        <Space>
          <Button
            icon={<SyncOutlined />}
            onClick={() => void handleSync()}
            loading={syncing}
          >
            立即同步
          </Button>
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
              主数据表
            </Button>
            <Select
              style={{ width: '100%' }}
              placeholder="选择主数据表（页面第一个页签）"
              value={tables.some((table) => table.table_id === tableId) ? tableId : undefined}
              options={tables.map((table) => ({
                value: table.table_id,
                label: `${table.table_name}（${table.table_id}）`,
              }))}
              onChange={(value) => {
                setTableId(value)
                // 主表换到某张子表后，它不能再同时作为页签子表
                setSubTableIds((prev) => prev.filter((id) => id !== value))
              }}
            />
          </Space.Compact>
        ) : null}
        <Space.Compact block>
          <Button disabled style={{ cursor: 'default', width: 140 }}>
            页签子表
          </Button>
          <Select
            mode="multiple"
            allowClear
            style={{ width: '100%' }}
            placeholder={
              tableCatalog.size
                ? '勾选需要作为页签展示的其余子表（主数据表始终是第一个页签）'
                : '先粘贴多维表格链接点「解析」获取子表清单，再勾选页签子表'
            }
            value={subTableIds.filter((id) => id !== tableId)}
            options={[...tableCatalog.entries()]
              .filter(([id]) => id !== tableId)
              .map(([id, name]) => ({ value: id, label: `${name}（${id}）` }))}
            onChange={(value) => setSubTableIds(value)}
          />
        </Space.Compact>
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
            placeholder="视图 view_id（页面列按该视图对齐，粘贴链接时自动带出）"
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
        {supportsOverLimit ? (
          <>
            <Space.Compact block>
              <Button disabled style={{ cursor: 'default', width: 140 }}>
                超储计算-存量列
              </Button>
              <Select
                style={{ width: '100%' }}
                allowClear
                showSearch
                placeholder={
                  fieldOptions.length
                    ? '选择统计表中「当前存量」列（与上限列同时配置生效）'
                    : '先点「测试绑定」获取字段清单'
                }
                value={overLimitQuantity}
                options={fieldOptions.map((name) => ({ value: name, label: name }))}
                onChange={(value) => setOverLimitQuantity(value)}
              />
            </Space.Compact>
            <Space.Compact block>
              <Button disabled style={{ cursor: 'default', width: 140 }}>
                超储计算-上限列
              </Button>
              <Select
                style={{ width: '100%' }}
                allowClear
                showSearch
                placeholder={
                  fieldOptions.length
                    ? '选择统计表中「存量上限」列（与存量列同时配置生效）'
                    : '先点「测试绑定」获取字段清单'
                }
                value={overLimitLimit}
                options={fieldOptions.map((name) => ({ value: name, label: name }))}
                onChange={(value) => setOverLimitLimit(value)}
              />
            </Space.Compact>
            <Space.Compact block>
              <Button disabled style={{ cursor: 'default', width: 140 }}>
                超储计算-品名列
              </Button>
              <Select
                style={{ width: '100%' }}
                allowClear
                showSearch
                placeholder="可选；缺省取表格第一个文本列"
                value={overLimitName}
                options={fieldOptions.map((name) => ({ value: name, label: name }))}
                onChange={(value) => setOverLimitName(value)}
              />
            </Space.Compact>
            <Typography.Text type="secondary">
              配置存量/上限列后，页面与安全总览的超储预警改从这张统计表计算；
              列值支持带单位文本（如 500kg）。不配置则回退本地库存口径。
            </Typography.Text>
          </>
        ) : null}
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
        <Space size={12} wrap>
          <Typography.Text>本地镜像数据源（全量同步，页面查询更快更完整）</Typography.Text>
          <Switch
            aria-label="启用本地镜像数据源"
            checked={mirrored}
            onChange={setMirrored}
          />
          {renderSyncTag(item.last_sync_status)}
          <Typography.Text type="secondary">
            最近同步：{formatDateTime(item.last_synced_at)}
            {item.last_sync_record_count != null
              ? `（${item.last_sync_record_count} 条）`
              : ''}
            ；每 15 分钟自动同步，页面编辑即时写回飞书并更新镜像。
          </Typography.Text>
        </Space>
        {item.last_sync_error ? (
          <PlatformNotice type="warning" title={item.last_sync_error} />
        ) : null}
        {item.last_test_error ? (
          <PlatformNotice type="warning" title={item.last_test_error} />
        ) : null}
        <Typography.Text type="secondary">
          列与数据来自飞书实时表结构，页面不写死字段；在页面上的修改会直接写回该多维表格。
          页签子表在这里勾选配置，换绑或增删子表无需改代码；每 15 分钟自动同步全部页签。
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
