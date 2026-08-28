'use client'

import { useCallback, useMemo, useState } from 'react'
import { App, Button, Card, Collapse, Form, Input, Space, Table, Tag } from 'antd'
import { EditOutlined, LinkOutlined, SaveOutlined } from '@ant-design/icons'
import type { WarehousePageFeishuConfig } from '@/types/warehouse'
import { fetchWarehousePageFeishuConfigs } from '@/lib/api/client/warehouse'
import { updateWarehousePageFeishuConfigAction } from '@/actions/warehouse'

interface WarehouseFeishuConfigPageProps {
  initialConfigs: WarehousePageFeishuConfig[]
}

// 数据源 Base 配置（与后端 feishu_material_pages.py 保持一致）
const BASE_CONFIGS = [
  { name: '原辅料', appToken: 'IpMdbEFSlaZRoJstpFLcbTzPn2e', tagColor: 'blue' },
  { name: '成品', appToken: 'S9KobSXEIaU9K4sgohycpiLqnhg', tagColor: 'green' },
  { name: '五金', appToken: 'DPjgbn78nao1lWsU7a3c3JUdnSb', tagColor: 'purple' },
] as const

const APP_TOKEN_TO_BASE = Object.fromEntries(
  BASE_CONFIGS.map((c) => [c.appToken, c.name]),
) as Record<string, string>

function buildFeishuTableUrl(config: WarehousePageFeishuConfig): string {
  let url = `https://j0eukrlohu.feishu.cn/base/${config.app_token}?table=${config.table_id}`
  if (config.view_id) {
    url += `&view=${config.view_id}`
  }
  return url
}

/** 解析飞书多维表格 URL，提取 app_token / table_id / view_id */
function parseFeishuBitableUrl(url: string): { app_token: string; table_id: string; view_id?: string } | null {
  try {
    const parsed = new URL(url.trim())
    const baseMatch = parsed.pathname.match(/\/base\/([^/]+)/)
    if (!baseMatch) return null
    const app_token = baseMatch[1]
    const table_id = parsed.searchParams.get('table')
    if (!table_id) return null
    const view_id = parsed.searchParams.get('view') || undefined
    return { app_token, table_id, view_id }
  } catch {
    return null
  }
}

export function WarehouseFeishuConfigPage({ initialConfigs }: WarehouseFeishuConfigPageProps) {
  const { message, modal } = App.useApp()
  const [configs, setConfigs] = useState<WarehousePageFeishuConfig[]>(initialConfigs)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [batchLoading, setBatchLoading] = useState(false)
  // 每个分组的 URL 输入值（key = 分组名）
  const [groupUrlInputs, setGroupUrlInputs] = useState<Record<string, string>>({})

  const handleEdit = (record: WarehousePageFeishuConfig) => {
    form.setFieldsValue(record)
    setEditingKey(record.page_key)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      const pageKey = editingKey ?? (values as WarehousePageFeishuConfig).page_key
      // table_name 不在编辑表单内，保存时从当前记录补全（后端 schema 必填）
      const current = configs.find((config) => config.page_key === pageKey)
      const config = {
        app_token: values.app_token as string,
        table_id: values.table_id as string,
        table_name: (current?.table_name ?? (values as WarehousePageFeishuConfig).table_name ?? '') as string,
        view_id: (values.view_id as string | undefined) || undefined,
      }
      await updateWarehousePageFeishuConfigAction(pageKey, config)
      message.success('配置已更新，立即生效')
      setEditingKey(null)
      await refreshConfigs()
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      message.error(`更新失败：${detail}`)
    } finally {
      setLoading(false)
    }
  }

  const handleCancel = () => {
    setEditingKey(null)
    form.resetFields()
  }

  // 刷新配置列表
  const refreshConfigs = async () => {
    try {
      const updated = await fetchWarehousePageFeishuConfigs()
      setConfigs(updated)
    } catch {
      // ignore
    }
  }

  // 按 Base 分组（保持 BASE_CONFIGS 顺序）
  const groupedConfigs = useMemo(() => {
    const groups: Record<string, WarehousePageFeishuConfig[]> = {}
    for (const config of configs) {
      const base = APP_TOKEN_TO_BASE[config.app_token] ?? '未知'
      if (!groups[base]) groups[base] = []
      groups[base].push(config)
    }
    const ordered: string[] = BASE_CONFIGS.map((c) => c.name).filter((base) => groups[base])
    for (const base of Object.keys(groups)) {
      if (!ordered.includes(base)) ordered.push(base)
    }
    return ordered.map((base) => ({ base, items: groups[base] }))
  }, [configs])

  /** 批量更新某分组下所有记录的飞书配置 */
  const handleBatchUpdate = useCallback(
    async (baseName: string) => {
      const url = groupUrlInputs[baseName]?.trim()
      if (!url) {
        message.warning('请先粘贴多维表格网址')
        return
      }
      const parsed = parseFeishuBitableUrl(url)
      if (!parsed) {
        message.error('无法识别该网址，请检查格式')
        return
      }

      const group = groupedConfigs.find((g) => g.base === baseName)
      if (!group || group.items.length === 0) return

      // 确认弹窗
      modal.confirm({
        title: '批量更新确认',
        content: (
          <div>
            <p>
              将把「{baseName}」分组下 <b>{group.items.length}</b> 条记录的配置更新为：
            </p>
            <p className="mt-1 text-[13px]">
              app_token：<code>{parsed.app_token}</code>
            </p>
            <p className="text-[13px]">
              table_id：<code>{parsed.table_id}</code>
            </p>
            {parsed.view_id && (
              <p className="text-[13px]">
                view_id：<code>{parsed.view_id}</code>
              </p>
            )}
          </div>
        ),
        okText: '确认更新',
        cancelText: '取消',
        onOk: async () => {
          setBatchLoading(true)
          const results = await Promise.allSettled(
            group.items.map((item) =>
              updateWarehousePageFeishuConfigAction(item.page_key, {
                app_token: parsed.app_token,
                table_id: parsed.table_id,
                table_name: item.table_name,
                view_id: parsed.view_id,
              }),
            ),
          )
          const successCount = results.filter((r) => r.status === 'fulfilled').length
          const failCount = results.filter((r) => r.status === 'rejected').length
          await refreshConfigs()
          // 清空该分组输入框
          setGroupUrlInputs((prev) => {
            const next = { ...prev }
            delete next[baseName]
            return next
          })
          if (failCount === 0) {
            message.success(`已更新 ${successCount} 条配置`)
          } else {
            message.warning(`更新完成：成功 ${successCount} 条，失败 ${failCount} 条`)
          }
          setBatchLoading(false)
        },
      })
    },
    [groupUrlInputs, groupedConfigs, message, modal],
  )

  const renderColumns = (record: WarehousePageFeishuConfig) => {
    const columns = [
      {
        title: '页面标识',
        dataIndex: 'page_key',
        key: 'page_key',
        width: 210,
      },
      {
        title: '多维表格名称',
        dataIndex: 'table_name',
        key: 'table_name',
        ellipsis: true,
      },
      {
        title: 'app_token',
        dataIndex: 'app_token',
        key: 'app_token',
        width: 180,
        ellipsis: true,
        render: (text: string, row: WarehousePageFeishuConfig) =>
          editingKey === row.page_key ? (
            <Form.Item name="app_token" rules={[{ required: true, message: '请输入 app_token' }]}>
              <Input size="small" />
            </Form.Item>
          ) : (
            text
          ),
      },
      {
        title: 'table_id',
        dataIndex: 'table_id',
        key: 'table_id',
        width: 160,
        ellipsis: true,
        render: (text: string, row: WarehousePageFeishuConfig) =>
          editingKey === row.page_key ? (
            <Form.Item name="table_id" rules={[{ required: true, message: '请输入 table_id' }]}>
              <Input size="small" />
            </Form.Item>
          ) : (
            text
          ),
      },
      {
        title: '视图 ID',
        dataIndex: 'view_id',
        key: 'view_id',
        width: 120,
        render: (text: string | null, row: WarehousePageFeishuConfig) =>
          editingKey === row.page_key ? (
            <Form.Item name="view_id">
              <Input size="small" placeholder="可选" />
            </Form.Item>
          ) : (
            text || '-'
          ),
      },
      {
        title: '多维表格链接',
        key: 'link',
        width: 120,
        render: (_: unknown, row: WarehousePageFeishuConfig) => (
          <Button
            type="link"
            size="small"
            icon={<LinkOutlined />}
            href={buildFeishuTableUrl(row)}
            target="_blank"
            rel="noreferrer"
          >
            打开表格
          </Button>
        ),
      },
      {
        title: '操作',
        key: 'action',
        width: 110,
        render: (_: unknown, row: WarehousePageFeishuConfig) =>
          editingKey === row.page_key ? (
            <Space>
              <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={loading} size="small">
                保存
              </Button>
              <Button onClick={handleCancel} size="small">
                取消
              </Button>
            </Space>
          ) : (
            <Button icon={<EditOutlined />} onClick={() => handleEdit(row)} size="small">
              编辑
            </Button>
          ),
      },
    ]
    return columns
  }

  // 渲染分组标题栏（含 URL 输入框 + 批量更新按钮）
  const renderGroupLabel = (base: string, itemCount: number) => {
    const urlValue = groupUrlInputs[base] ?? ''
    const parsed = urlValue ? parseFeishuBitableUrl(urlValue) : null
    return (
      <Space size={12} wrap align="center">
        <Tag color={BASE_CONFIGS.find((c) => c.name === base)?.tagColor ?? 'default'}>{base}</Tag>
        <span className="text-[13px]">共 {itemCount} 页</span>
        <Input
          size="small"
          style={{ width: 420 }}
          placeholder="粘贴多维表格网址，自动填充 app_token 和 table_id"
          value={urlValue}
          onChange={(e) =>
            setGroupUrlInputs((prev) => ({ ...prev, [base]: e.target.value }))
          }
          onPressEnter={() => handleBatchUpdate(base)}
          disabled={batchLoading}
        />
        {parsed && (
          <span className="text-[12px] text-green-600">
            ✓ {parsed.app_token} / {parsed.table_id}
          </span>
        )}
        <Button
          size="small"
          type="primary"
          onClick={() => handleBatchUpdate(base)}
          loading={batchLoading}
          disabled={!urlValue.trim()}
        >
          批量更新
        </Button>
      </Space>
    )
  }

  return (
    <div className="p-6">
      <h1 className="mb-2 text-2xl font-semibold">仓储页面飞书配置</h1>
      <p className="mb-4 text-[13px] text-[var(--color-steel)]">
        页面数据实时读取对应多维表格子表；修改配置后立即生效，更换表格无需改代码。
      </p>
      <Card>
        <Form form={form} component={false}>
          <Collapse
            defaultActiveKey={BASE_CONFIGS.map((c) => c.name)}
            items={groupedConfigs.map(({ base, items }) => ({
              key: base,
              label: renderGroupLabel(base, items.length),
              children: (
                <Table
                  columns={renderColumns(items[0])}
                  dataSource={items}
                  rowKey="page_key"
                  pagination={false}
                  size="small"
                  scroll={{ x: 'max-content' }}
                />
              ),
            }))}
          />
        </Form>
      </Card>
    </div>
  )
}

export default WarehouseFeishuConfigPage
