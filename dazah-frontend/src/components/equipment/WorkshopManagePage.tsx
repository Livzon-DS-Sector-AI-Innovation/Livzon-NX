'use client'

// 设备车间管理页：新增/改名/启停车间。车间清单是数据库注册表
// （equipment.workshops），保存后工作台车间块、各功能视图与飞书配置页
// 清单自动生效；停用仅隐藏入口，业务数据按 workshop_code 保留。

import { useCallback, useEffect, useState } from 'react'
import type { HTMLAttributes } from 'react'
import {
  App, Button, Card, Form, Input, Modal, Popconfirm, Space,
  Table, Tag, Typography,
} from 'antd'
import {
  CheckCircleOutlined, EditOutlined, PlusOutlined, StopOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import {
  createEquipmentWorkshop,
  fetchAllEquipmentWorkshops,
  updateEquipmentWorkshop,
} from '@/lib/api/equipment-workshops'
import {
  invalidateEquipmentWorkshops,
  loadEquipmentWorkshops,
} from '@/lib/equipment-workshop-registry'
import type { WorkshopAdminSummary } from '@/types/equipment-workshops'

const { Text, Paragraph } = Typography

export function WorkshopManagePage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [rows, setRows] = useState<WorkshopAdminSummary[]>([])
  const [reloadKey, setReloadKey] = useState(0)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<WorkshopAdminSummary | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [toggling, setToggling] = useState<string | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      setRows(await fetchAllEquipmentWorkshops())
    } catch (error) {
      setLoadError((error as Error).message || '加载车间清单失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  const openModal = useCallback((row: WorkshopAdminSummary | null) => {
    setEditing(row)
    setModalOpen(true)
    if (row) {
      form.setFieldsValue({ code: row.code, name: row.name })
    } else {
      form.resetFields()
    }
  }, [form])

  const submit = useCallback(async () => {
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      if (editing) {
        await updateEquipmentWorkshop(editing.code, {
          name: values.name.trim(),
        })
        message.success('车间已更新')
      } else {
        await createEquipmentWorkshop({
          code: values.code.trim(),
          name: values.name.trim(),
        })
        message.success('车间已新增，各功能页与飞书配置即刻生效')
      }
      setModalOpen(false)
      // 让工作台车间块等入口拿到最新清单
      invalidateEquipmentWorkshops()
      void loadEquipmentWorkshops(true)
      setReloadKey((k) => k + 1)
    } catch (error) {
      message.error((error as Error).message || '保存车间失败')
    } finally {
      setSubmitting(false)
    }
  }, [form, editing, message])

  const toggle = useCallback(async (row: WorkshopAdminSummary) => {
    setToggling(row.code)
    try {
      await updateEquipmentWorkshop(row.code, { is_enabled: !row.is_enabled })
      message.success(row.is_enabled ? `车间 ${row.name} 已停用` : `车间 ${row.name} 已启用`)
      invalidateEquipmentWorkshops()
      void loadEquipmentWorkshops(true)
      setReloadKey((k) => k + 1)
    } catch (error) {
      message.error((error as Error).message || '操作失败')
    } finally {
      setToggling(null)
    }
  }, [message])

  const columns: ColumnsType<WorkshopAdminSummary> = [
    {
      title: '车间代码', dataIndex: 'code', width: 140,
      render: (code: string) => <Text code style={{ fontSize: 13 }}>{code}</Text>,
    },
    {
      title: '车间名称', dataIndex: 'name', width: 180, ellipsis: true,
      render: (name: string) => <Text strong>{name}</Text>,
    },
    {
      title: '状态', dataIndex: 'is_enabled', width: 100,
      render: (enabled: boolean) => enabled ? (
        <Tag color="green" icon={<CheckCircleOutlined />}>启用</Tag>
      ) : (
        <Tag>停用</Tag>
      ),
    },
    {
      title: '登记时间', dataIndex: 'created_at', width: 160,
      render: (value: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {dayjs(value).format('YYYY-MM-DD HH:mm')}
        </Text>
      ),
    },
    {
      title: '操作', width: 200, fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <Button
            size="small" icon={<EditOutlined />}
            aria-label={`改名车间 ${row.name}`}
            onClick={() => openModal(row)}
          >
            改名
          </Button>
          <Popconfirm
            title={row.is_enabled ? `停用 ${row.name}？` : `启用 ${row.name}？`}
            description={
              row.is_enabled
                ? '停用后各处隐藏该车间入口，数据保留，可随时再启用'
                : '启用后各功能页与飞书配置恢复显示该车间'
            }
            okText={row.is_enabled ? '停用' : '启用'}
            okButtonProps={row.is_enabled ? { danger: true } : undefined}
            onConfirm={() => void toggle(row)}
          >
            <Button
              size="small"
              danger={row.is_enabled}
              icon={row.is_enabled ? <StopOutlined /> : <CheckCircleOutlined />}
              aria-label={`${row.is_enabled ? '停用' : '启用'}车间 ${row.name}`}
              loading={toggling === row.code}
            >
              {row.is_enabled ? '停用' : '启用'}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: '20px 24px 32px' }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 22, fontWeight: 600, color: '#1a1a1a', margin: 0, marginBottom: 4 }}>
          车间管理
        </h2>
        <p style={{ fontSize: 14, color: '#787671', margin: 0 }}>
          新增车间后，设备管理各功能页与飞书配置自动生效；停用仅隐藏入口，业务数据保留
        </p>
      </div>

      {loadError && (
        <Paragraph type="danger" style={{ marginBottom: 16 }}>
          加载车间清单失败：{loadError}
          <Button size="small" style={{ marginLeft: 12 }} onClick={() => setReloadKey((k) => k + 1)}>
            重试
          </Button>
        </Paragraph>
      )}

      <Card size="small">
        <div style={{ marginBottom: 12 }}>
          <Button
            type="primary" icon={<PlusOutlined />}
            aria-label="新增车间"
            onClick={() => openModal(null)}
          >
            新增车间
          </Button>
        </div>
        <Table<WorkshopAdminSummary>
          rowKey="code"
          size="small"
          columns={columns}
          dataSource={rows}
          loading={loading}
          pagination={false}
          tableLayout="fixed"
          onRow={(row) => ({ 'data-testid': `workshop-row:${row.code}` } as HTMLAttributes<HTMLElement>)}
        />
        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0, marginTop: 8 }}>
          车间代码创建后不可修改（业务数据按代码关联）；代码为 2~10 位小写字母/数字，可带 -序号（如 204 / 204-1 / dlz）。
        </Paragraph>
      </Card>

      <Modal
        title={editing ? `改名车间 · ${editing.code}` : '新增车间'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => void submit()}
        confirmLoading={submitting}
        okText={editing ? '保存' : '新增'}
        cancelText="取消"
      >
        <Form form={form} layout="vertical" requiredMark={false}>
          <Form.Item
            name="code"
            label="车间代码"
            normalize={(value: unknown) =>
              typeof value === 'string' ? value.toLowerCase() : value
            }
            rules={[
              { required: true, message: '请输入车间代码' },
              {
                pattern: /^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$/,
                message: '2~10 位小写字母/数字，可带 -序号（如 204 / 204-1 / dlz）',
              },
            ]}
            extra={editing ? '代码创建后不可修改' : '全系统数据按此代码关联，创建后不可修改；如 动力站 → dlz'}
          >
            <Input placeholder="204 / 204-1 / dlz" maxLength={10} disabled={Boolean(editing)} autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="name"
            label="车间名称"
            rules={[{ required: true, message: '请输入车间名称' }]}
          >
            <Input placeholder="如：204一车间" maxLength={50} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
