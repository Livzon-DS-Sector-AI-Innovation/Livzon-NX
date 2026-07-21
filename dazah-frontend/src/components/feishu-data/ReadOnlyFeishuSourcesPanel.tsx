'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Button, Card, Form, Input, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd'
import { DeleteOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons'

type SourceRoot = {
  id: string
  name: string
  source_type: 'wiki' | 'base'
  source_url: string
  discovery_status: string
  discovery_error?: string | null
  last_discovered_at?: string | null
}

type Resource = {
  id: string
  source_root_id: string
  title: string
  table_id: string
  source_path?: Array<{ title?: string }>
  sync_status: string
  sync_error?: string | null
  last_complete_sync_at?: string | null
}

type PageOption = { label: string; value: string }

type Props = {
  moduleCode: 'production' | 'quality'
  pageOptions: PageOption[]
  configId?: string | null
}

async function request<T>(moduleCode: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/${moduleCode}${path}`, {
    ...init,
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  const body = await response.json().catch(() => null)
  if (!response.ok || !body) throw new Error(body?.message || '飞书只读数据源操作失败')
  return body.data as T
}

function statusTag(status: string) {
  if (status === 'success') return <Tag color="success">成功</Tag>
  if (status === 'running') return <Tag color="processing">执行中</Tag>
  if (status === 'failed') return <Tag color="error">失败</Tag>
  return <Tag>待执行</Tag>
}

export function ReadOnlyFeishuSourcesPanel({ moduleCode, pageOptions, configId }: Props) {
  const { message } = App.useApp()
  const [form] = Form.useForm<{ name: string; source_type: 'wiki' | 'base'; source_url: string }>()
  const [roots, setRoots] = useState<SourceRoot[]>([])
  const [resources, setResources] = useState<Resource[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState<Record<string, boolean>>({})
  const [pageKey, setPageKey] = useState(pageOptions[0]?.value)
  const [selectedResources, setSelectedResources] = useState<string[]>([])

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const configSearch = configId ? `?config_id=${encodeURIComponent(configId)}` : ''
      const [nextRoots, nextResources] = await Promise.all([
        request<SourceRoot[]>(moduleCode, `/feishu-read/roots${configSearch}`),
        request<Resource[]>(moduleCode, '/feishu-read/resources'),
      ])
      setRoots(nextRoots)
      setResources(nextResources)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载只读数据源失败')
    } finally {
      setLoading(false)
    }
  }, [configId, message, moduleCode])

  const loadBinding = useCallback(async () => {
    if (!pageKey) return
    try {
      const data = await request<{ bindings: Array<{ table_pk: string }> }>(
        moduleCode,
        `/page-data/${encodeURIComponent(pageKey)}`,
      )
      setSelectedResources(data.bindings.map((item) => item.table_pk))
    } catch {
      setSelectedResources([])
    }
  }, [moduleCode, pageKey])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])
  useEffect(() => {
    const timer = window.setTimeout(() => void loadBinding(), 0)
    return () => window.clearTimeout(timer)
  }, [loadBinding])

  const run = async (key: string, operation: () => Promise<unknown>, success: string) => {
    try {
      setBusy((current) => ({ ...current, [key]: true }))
      await operation()
      message.success(success)
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败')
    } finally {
      setBusy((current) => ({ ...current, [key]: false }))
    }
  }

  const resourceOptions = useMemo(
    () => resources.map((item) => ({ label: `${item.title}（${item.table_id}）`, value: item.id })),
    [resources],
  )

  return (
    <Card
      title="只读数据源与页面映射"
      extra={<Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新本地目录</Button>}
    >
      <Typography.Paragraph type="secondary">
        此区域只读取飞书并写入模块本地镜像，不调用任何飞书写接口；原业务双向同步配置保持独立。
      </Typography.Paragraph>

      <Form
        form={form}
        layout="inline"
        initialValues={{ source_type: 'wiki' }}
        onFinish={(values) => void run('create', () => request(moduleCode, '/feishu-read/roots', {
          method: 'POST',
          body: JSON.stringify({ ...values, config_id: configId || undefined }),
        }).then(() => form.resetFields()), '入口已添加')}
      >
        <Form.Item name="name" rules={[{ required: true, message: '请输入入口名称' }]}>
          <Input placeholder="入口名称" style={{ width: 180 }} />
        </Form.Item>
        <Form.Item name="source_type" rules={[{ required: true }]}>
          <Select style={{ width: 120 }} options={[{ label: 'Wiki', value: 'wiki' }, { label: '多维表格', value: 'base' }]} />
        </Form.Item>
        <Form.Item name="source_url" rules={[{ required: true, message: '请输入 Wiki/Base 链接或 Token' }]}>
          <Input placeholder="Wiki/Base 链接或 Token" style={{ width: 360 }} />
        </Form.Item>
        <Form.Item><Button type="primary" htmlType="submit" loading={busy.create}>添加入口</Button></Form.Item>
      </Form>

      <Table<SourceRoot>
        rowKey="id"
        loading={loading}
        pagination={false}
        style={{ marginTop: 16 }}
        dataSource={roots}
        columns={[
          { title: '入口', dataIndex: 'name' },
          { title: '类型', dataIndex: 'source_type', width: 100, render: (value) => value === 'wiki' ? 'Wiki' : '多维表格' },
          { title: '发现状态', dataIndex: 'discovery_status', width: 110, render: statusTag },
          { title: '错误', dataIndex: 'discovery_error', ellipsis: true, render: (value) => value || '-' },
          {
            title: '操作', width: 190,
            render: (_, item) => <Space>
              <Button size="small" icon={<ReloadOutlined />} loading={busy[`discover:${item.id}`]} onClick={() => void run(`discover:${item.id}`, () => request(moduleCode, `/feishu-read/roots/${item.id}/discover`, { method: 'POST' }), '资源发现完成')}>重新发现</Button>
              <Popconfirm title="解绑并停用该入口？本地完整镜像不会立即删除。" onConfirm={() => void run(`delete:${item.id}`, () => request(moduleCode, `/feishu-read/roots/${item.id}`, { method: 'DELETE' }), '入口已停用')}>
                <Button size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </Space>,
          },
        ]}
      />

      <Table<Resource>
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 8 }}
        style={{ marginTop: 20 }}
        dataSource={resources}
        columns={[
          { title: '数据表', dataIndex: 'title' },
          { title: 'Table ID', dataIndex: 'table_id', width: 190 },
          { title: '同步状态', dataIndex: 'sync_status', width: 110, render: statusTag },
          { title: '最近完整同步', dataIndex: 'last_complete_sync_at', width: 180, render: (value) => value ? new Date(value).toLocaleString('zh-CN') : '-' },
          { title: '操作', width: 120, render: (_, item) => <Button size="small" icon={<SyncOutlined />} loading={busy[`sync:${item.id}`]} onClick={() => void run(`sync:${item.id}`, () => request(moduleCode, `/feishu-read/resources/${item.id}/sync`, { method: 'POST' }), '完整镜像同步成功')}>同步</Button> },
        ]}
      />

      <Space wrap style={{ marginTop: 20 }}>
        <Typography.Text strong>页面映射</Typography.Text>
        <Select value={pageKey} onChange={setPageKey} options={pageOptions} style={{ width: 220 }} />
        <Select mode="multiple" value={selectedResources} onChange={setSelectedResources} options={resourceOptions} placeholder="点击选择一个或多个数据表" style={{ minWidth: 420 }} />
        <Button
          type="primary"
          disabled={!pageKey}
          loading={busy.binding}
          onClick={() => void run('binding', () => request(moduleCode, `/feishu-read/page-bindings/${encodeURIComponent(pageKey!)}`, {
            method: 'PUT',
            body: JSON.stringify({ bindings: selectedResources.map((resourceId, index) => ({
              resource_id: resourceId,
              tab_name: resources.find((item) => item.id === resourceId)?.title || `数据表 ${index + 1}`,
              sort_order: index,
              is_default: index === 0,
              is_enabled: true,
              visible_field_ids: [],
            })) }),
          }), '页面映射已发布')}
        >发布映射</Button>
      </Space>
    </Card>
  )
}
