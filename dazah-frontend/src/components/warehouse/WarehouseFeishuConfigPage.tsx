'use client'

import { useCallback, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Collapse, Form, Input, Space, Table, Tag } from 'antd'
import { EditOutlined, LinkOutlined, SaveOutlined } from '@ant-design/icons'
import type { WarehousePageFeishuConfig } from '@/types/warehouse'
import { fetchWarehousePageFeishuConfigs } from '@/lib/api/client/warehouse'
import { updateWarehousePageFeishuConfigAction } from '@/actions/warehouse'
import { parseFeishuBitableUrl } from '@/lib/feishu-url'
import { usePagePermissions } from '@/hooks/usePagePermissions'

interface WarehouseFeishuConfigPageProps {
  initialConfigs: WarehousePageFeishuConfig[]
}

const GROUP_TAG_COLORS = ['blue', 'cyan', 'green', 'purple', 'geekblue', 'orange']

// 分组展示名：注册表不再携带 Base 标识，按 app_token 动态分组，
// 标签展示 token 末 6 位（展示用途，不参与任何调用）
function groupLabelFor(appToken: string): string {
  return `Base ${appToken.slice(-6)}`.trim()
}

function buildFeishuTableUrl(config: WarehousePageFeishuConfig): string {
  let url = `https://www.feishu.cn/base/${config.app_token}?table=${config.table_id}`
  if (config.view_id) {
    url += `&view=${config.view_id}`
  }
  return url
}

/** 组装 PUT payload：显式携带表单链接字段，避免批量/单行保存互相覆盖 */
function buildConfigPayload(
  values: Record<string, unknown>,
  current?: WarehousePageFeishuConfig
): Omit<WarehousePageFeishuConfig, 'page_key'> {
  return {
    app_token: values.app_token as string,
    table_id: values.table_id as string,
    table_name:
      (current?.table_name ?? (values.table_name as string | undefined) ?? '') as string,
    view_id: (values.view_id as string | undefined) || undefined,
    feishu_inbound_form_url:
      (values.feishu_inbound_form_url as string | undefined) ||
      current?.feishu_inbound_form_url ||
      undefined,
    feishu_outbound_form_url:
      (values.feishu_outbound_form_url as string | undefined) ||
      current?.feishu_outbound_form_url ||
      undefined,
  }
}

export function WarehouseFeishuConfigPage({ initialConfigs }: WarehouseFeishuConfigPageProps) {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const { canSync } = usePagePermissions('warehouse:warehouse-settings')
  const [configs, setConfigs] = useState<WarehousePageFeishuConfig[]>(initialConfigs)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [batchLoading, setBatchLoading] = useState(false)
  // 每个分组的 URL 输入值（key = 分组名）
  const [groupUrlInputs, setGroupUrlInputs] = useState<Record<string, string>>({})

  const handleEdit = (record: WarehousePageFeishuConfig) => {
    if (!canSync) return
    form.setFieldsValue(record)
    setEditingKey(record.page_key)
  }

  const handleSave = async () => {
    if (!canSync) return
    try {
      const values = await form.validateFields()
      setLoading(true)
      const pageKey = editingKey ?? (values as WarehousePageFeishuConfig).page_key
      // table_name 不在编辑表单内，保存时从当前记录补全（后端 schema 必填）
      const current = configs.find((config) => config.page_key === pageKey)
      await updateWarehousePageFeishuConfigAction(
        pageKey,
        buildConfigPayload(values, current)
      )
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

  // 刷新配置列表，并让依赖表单链接的其他页面（台账登记按钮/首页快捷卡）同步
  const refreshConfigs = async () => {
    try {
      const updated = await fetchWarehousePageFeishuConfigs()
      setConfigs(updated)
    } catch {
      // ignore
    }
    queryClient.invalidateQueries({ queryKey: ['warehouse-page-form-links'] })
    queryClient.invalidateQueries({ queryKey: ['warehouse-home-quick-form-links'] })
  }

  // 按 app_token 动态分组（不依赖写死的 Base 清单，换 Base 后照常分组）
  const groupedConfigs = useMemo(() => {
    const groups: Record<string, WarehousePageFeishuConfig[]> = {}
    for (const config of configs) {
      const base = groupLabelFor(config.app_token)
      if (!groups[base]) groups[base] = []
      groups[base].push(config)
    }
    return Object.keys(groups).map((base) => ({ base, items: groups[base] }))
  }, [configs])

  const groupColor = useCallback((base: string) => {
    const names = groupedConfigs.map((g) => g.base)
    const index = names.indexOf(base)
    return GROUP_TAG_COLORS[index % GROUP_TAG_COLORS.length] ?? 'default'
  }, [groupedConfigs])

  /** 批量更新某分组下所有记录的飞书配置 */
  const handleBatchUpdate = useCallback(
    async (baseName: string) => {
      if (!canSync) return
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
      if (!parsed.table_id) {
        message.warning(
          '已识别 App Token，但网址未含子表信息：批量更新会把整组页面指向同一张子表，请粘贴具体子表链接（含 ?table= 参数）',
        )
        return
      }
      const appToken = parsed.app_token
      const tableId = parsed.table_id
      const viewId = parsed.view_id

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
              app_token：<code>{appToken}</code>
            </p>
            <p className="text-[13px]">
              table_id：<code>{tableId}</code>
            </p>
            {viewId && (
              <p className="text-[13px]">
                view_id：<code>{viewId}</code>
              </p>
            )}
            <p className="text-[12px] text-[var(--color-steel)]">
              各页面已配置的表单链接将保留不变
            </p>
          </div>
        ),
        okText: '确认更新',
        cancelText: '取消',
        onOk: async () => {
          setBatchLoading(true)
          const results = await Promise.allSettled(
            group.items.map((item) =>
              updateWarehousePageFeishuConfigAction(item.page_key, {
                app_token: appToken,
                table_id: tableId,
                table_name: item.table_name,
                view_id: viewId,
                // 批量换绑只改数据源，保留各页面已配置的表单链接
                feishu_inbound_form_url: item.feishu_inbound_form_url,
                feishu_outbound_form_url: item.feishu_outbound_form_url,
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
    [canSync, groupUrlInputs, groupedConfigs, message, modal],
  )

  const renderColumns = () => {
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
        title: '入库表单链接',
        dataIndex: 'feishu_inbound_form_url',
        key: 'feishu_inbound_form_url',
        width: 170,
        ellipsis: true,
        render: (text: string | null, row: WarehousePageFeishuConfig) =>
          editingKey === row.page_key ? (
            <Form.Item name="feishu_inbound_form_url">
              <Input size="small" placeholder="粘贴飞书共享表单链接，留空隐藏入库按钮" />
            </Form.Item>
          ) : (
            text || '-'
          ),
      },
      {
        title: '出库表单链接',
        dataIndex: 'feishu_outbound_form_url',
        key: 'feishu_outbound_form_url',
        width: 170,
        ellipsis: true,
        render: (text: string | null, row: WarehousePageFeishuConfig) =>
          editingKey === row.page_key ? (
            <Form.Item name="feishu_outbound_form_url">
              <Input size="small" placeholder="粘贴飞书共享表单链接，留空隐藏出库按钮" />
            </Form.Item>
          ) : (
            text || '-'
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
              <Button disabled={!canSync} type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={loading} size="small">
                保存
              </Button>
              <Button onClick={handleCancel} size="small">
                取消
              </Button>
            </Space>
          ) : (
            <Button disabled={!canSync} title={!canSync ? '需要同步配置权限' : undefined} icon={<EditOutlined />} onClick={() => handleEdit(row)} size="small">
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
        <Tag color={groupColor(base)}>{base}</Tag>
        <span className="text-[13px]">共 {itemCount} 页</span>
        <Input
          size="small"
          style={{ width: 420 }}
          placeholder="粘贴子表链接（含 ?table= 参数），批量填充本组 app_token 和 table_id"
          value={urlValue}
          onChange={(e) =>
            setGroupUrlInputs((prev) => ({ ...prev, [base]: e.target.value }))
          }
          onPressEnter={() => handleBatchUpdate(base)}
          disabled={!canSync || batchLoading}
        />
        {parsed && (
          <span className="text-[12px] text-green-600">
            ✓ {parsed.app_token}
            {parsed.table_id ? ` / ${parsed.table_id}` : '（未识别到子表，请粘贴子表链接）'}
          </span>
        )}
        <Button
          size="small"
          type="primary"
          onClick={() => handleBatchUpdate(base)}
          loading={batchLoading}
          disabled={!canSync || !urlValue.trim()}
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
        入库/出库表单链接控制台账页与首页的「登记/新增」按钮，留空即隐藏入口。
      </p>
      <Card>
        <Form form={form} component={false}>
          <Collapse
            defaultActiveKey={groupedConfigs.map(({ base }) => base)}
            items={groupedConfigs.map(({ base, items }) => ({
              key: base,
              label: renderGroupLabel(base, items.length),
              children: (
                <Table
                  columns={renderColumns()}
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
