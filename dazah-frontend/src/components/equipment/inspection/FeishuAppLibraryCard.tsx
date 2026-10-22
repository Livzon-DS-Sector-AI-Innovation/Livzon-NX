'use client'

// 飞书自建应用库管理卡：独立存放自建应用凭据（名称 + App ID + Secret 加密）。
// 巡检配置抽屉的「凭据来源」下拉引用这里的记录；Secret 永不回显明文。

import { useCallback, useEffect, useState } from 'react'
import {
  App, Button, Card, Form, Input, Modal, Popconfirm, Space, Table, Tag, Typography,
} from 'antd'
import {
  ApiOutlined, CopyOutlined, DeleteOutlined, EditOutlined, PlusOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import {
  createFeishuApp,
  deleteFeishuApp,
  fetchFeishuApps,
  updateFeishuApp,
} from '@/lib/api/inspection-feishu'
import type { FeishuAppItem } from '@/types/inspection-feishu'

const { Text, Paragraph } = Typography

type AppFormValues = {
  name: string
  app_id: string
  app_secret?: string
}

export function FeishuAppLibraryCard({ onChanged }: { onChanged?: () => void }) {
  const { message } = App.useApp()
  const [form] = Form.useForm<AppFormValues>()
  const [apps, setApps] = useState<FeishuAppItem[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [editing, setEditing] = useState<FeishuAppItem | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      setApps(await fetchFeishuApps())
    } catch (error) {
      setLoadError((error as Error).message || '加载自建应用失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load() // eslint-disable-line react-hooks/set-state-in-effect -- 初始加载，与飞书配置页既有模式一致
  }, [load])

  const openCreate = useCallback(() => {
    setEditing(null)
    form.resetFields()
    setModalOpen(true)
  }, [form])

  const openEdit = useCallback(
    (app: FeishuAppItem) => {
      setEditing(app)
      form.setFieldsValue({ name: app.name, app_id: app.app_id, app_secret: '' })
      setModalOpen(true)
    },
    [form],
  )

  const copy = useCallback(
    async (text: string, label: string) => {
      try {
        await navigator.clipboard.writeText(text)
        message.success(`已复制${label}`)
      } catch {
        message.error('复制失败，请手动选择复制')
      }
    },
    [message],
  )

  const handleSave = useCallback(async () => {
    let values: AppFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    setSaving(true)
    try {
      if (editing) {
        await updateFeishuApp(editing.id, {
          name: values.name.trim(),
          app_id: values.app_id.trim(),
          // 编辑时留空保持已保存 Secret
          app_secret: values.app_secret?.trim() || null,
        })
        message.success('自建应用已更新')
      } else {
        await createFeishuApp({
          name: values.name.trim(),
          app_id: values.app_id.trim(),
          app_secret: values.app_secret ?? '',
        })
        message.success('自建应用已创建')
      }
      setModalOpen(false)
      await load()
      onChanged?.()
    } catch (error) {
      message.error((error as Error).message || '保存自建应用失败')
    } finally {
      setSaving(false)
    }
  }, [editing, form, load, message, onChanged])

  const handleRemove = useCallback(
    async (app: FeishuAppItem) => {
      setRemoving(app.id)
      try {
        await deleteFeishuApp(app.id)
        message.success(`已删除自建应用「${app.name}」`)
        await load()
        onChanged?.()
      } catch (error) {
        message.error((error as Error).message || '删除失败')
      } finally {
        setRemoving(null)
      }
    },
    [load, message, onChanged],
  )

  const columns: ColumnsType<FeishuAppItem> = [
    {
      title: '应用名称', dataIndex: 'name', width: 180,
      render: (name: string) => <Text strong>{name}</Text>,
    },
    {
      title: 'App ID', dataIndex: 'app_id', width: 200,
      render: (appId: string) => (
        <Space size={4}>
          <Text code style={{ fontSize: 12 }}>{appId}</Text>
          <Button
            type="text" size="small" icon={<CopyOutlined />}
            aria-label={`复制应用 App ID ${appId}`}
            onClick={() => void copy(appId, 'App ID')}
          />
        </Space>
      ),
    },
    {
      title: 'App Secret', width: 110,
      render: (_, app) => app.app_secret_configured
        ? <Tag color="green">已配置</Tag>
        : <Tag color="red">未配置</Tag>,
    },
    {
      title: '引用车间', width: 200,
      render: (_, app) => (app.referenced_workshops ?? []).length > 0
        ? (
          <Space size={4} wrap>
            {(app.referenced_workshops ?? []).map((code) => <Tag key={code}>{code}</Tag>)}
          </Space>
        )
        : <Text type="secondary" style={{ fontSize: 12 }}>未引用</Text>,
    },
    {
      title: '更新时间', dataIndex: 'updated_at', width: 110,
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {dayjs(v).format('MM-DD HH:mm')}
        </Text>
      ),
    },
    {
      title: '操作', width: 130, fixed: 'right',
      render: (_, app) => (
        <Space size={4}>
          <Button
            size="small" icon={<EditOutlined />}
            onClick={() => openEdit(app)}
          >
            编辑
          </Button>
          <Popconfirm
            title={`删除自建应用「${app.name}」？`}
            description="仍被巡检配置引用的应用无法删除"
            okText="删除"
            okButtonProps={{ danger: true }}
            onConfirm={() => void handleRemove(app)}
          >
            <Button
              size="small" danger icon={<DeleteOutlined />}
              loading={removing === app.id}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card
      size="small"
      style={{ marginBottom: 16 }}
      title={<Space size={8}><ApiOutlined />自建应用库</Space>}
      extra={(
        <Button size="small" icon={<PlusOutlined />} onClick={openCreate}>
          新建应用
        </Button>
      )}
      data-testid="feishu-app-library"
    >
      {loadError && (
        <Paragraph type="danger" style={{ fontSize: 13 }}>
          加载自建应用失败：{loadError}
        </Paragraph>
      )}
      <Table<FeishuAppItem>
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={apps}
        loading={loading}
        pagination={false}
        locale={{ emptyText: '尚未创建自建应用；点右上角「新建应用」录入后，各车间配置可直接选用' }}
      />
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0, marginTop: 8 }}>
        Secret 加密保存、永不回显明文；引用应用库的巡检配置在 Secret 更新后即时生效。
      </Paragraph>

      <Modal
        title={editing ? `编辑自建应用 · ${editing.name}` : '新建自建应用'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => void handleSave()}
        okText={editing ? '保存' : '创建'}
        cancelText="取消"
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" requiredMark={false}>
          <Form.Item
            name="name" label="应用名称"
            rules={[{ required: true, message: '请输入应用名称（便于辨认）' }]}
          >
            <Input placeholder="如：设备巡检同步应用" autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="app_id" label="App ID"
            rules={[{ required: true, message: '请输入飞书应用 App ID' }]}
          >
            <Input placeholder="cli_xxxxxxxx" autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="app_secret" label="App Secret"
            extra={editing ? '已加密保存，留空保持不变' : undefined}
            rules={editing ? [] : [{ required: true, message: '请输入飞书应用 App Secret' }]}
          >
            <Input.Password
              placeholder={editing ? '留空保持当前 Secret 不变' : '请输入飞书应用 App Secret'}
              autoComplete="new-password"
            />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
