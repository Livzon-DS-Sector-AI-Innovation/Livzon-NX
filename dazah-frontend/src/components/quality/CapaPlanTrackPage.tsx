'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { App, Button, Checkbox, Form, Input, Modal, Popconfirm, Select, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { SyncOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createCapaPlanTrack as createCapaPlanTrackAction, deleteCapaPlanTrack as deleteCapaPlanTrackAction, updateCapaPlanTrack as updateCapaPlanTrackAction } from '@/actions/quality-capa'
import { syncCapaPlanTracksFromFeishu } from '@/actions/quality-capa'
import { fetchCapaPlanTracks, fetchCapas } from '@/lib/api/client/quality'

import { fetchFeishuDepartmentContactsAction } from '@/actions/quality'
import type { CapaPlanTrackItem, CreateCapaPlanTrackRequest } from '@/types/quality'

const columns: ColumnsType<CapaPlanTrackItem> = [
  { title: 'CAPA编号', dataIndex: 'capa_code', key: 'capa_code', width: 170 },
  { title: '计划内容', dataIndex: 'plan_content', key: 'plan_content' },
  { title: '责任人', dataIndex: 'owner_name', key: 'owner_name', width: 120 },
  { title: '责任人确认', dataIndex: 'owner_confirmed', key: 'owner_confirmed', width: 100, render: (value: boolean) => (value ? '是' : '否') },
  { title: '部门负责人', dataIndex: 'department_head', key: 'department_head', width: 120 },
  { title: '负责人确认', dataIndex: 'department_head_confirmed', key: 'department_head_confirmed', width: 100, render: (value: boolean) => (value ? '是' : '否') },
  { title: '进度', dataIndex: 'progress', key: 'progress', width: 120 },
  { title: '提醒状态', dataIndex: 'reminder_status', key: 'reminder_status', width: 120 },
  { title: '完成时间', dataIndex: 'due_date', key: 'due_date', width: 140 },
]

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export function CapaPlanTrackPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [open, setOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<CapaPlanTrackItem | null>(null)
  const [form] = Form.useForm<CreateCapaPlanTrackRequest>()

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-capa-plan', 'list'],
    queryFn: async () => {
      const [tracks, capas] = await Promise.all([
        fetchCapaPlanTracks({ page: 1, page_size: 50 }),
        fetchCapas({ page: 1, page_size: 50 }),
      ])
      return { items: tracks.items, capaOptions: capas.items }
    },
  })

  const { data: contactData } = useQuery({
    queryKey: ['quality-contacts', 'department'],
    queryFn: () => fetchFeishuDepartmentContactsAction(1, 100),
    staleTime: 5 * 60 * 1000,
  })
  const contactOptions = ((contactData as { contacts?: { name?: string; department?: string; contact?: string }[] } | null)?.contacts ?? []).map((c) => ({
    label: `${c.department ?? ''} - ${c.contact ?? ''} (${c.name ?? ''})`,
    value: c.name ?? '',
    department: c.department ?? '',
  }))

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载CAPA计划跟踪失败'))
    }
  }, [error, message])

  const items = data?.items ?? []
  const capaOptions = data?.capaOptions ?? []

  const openCreate = useCallback(() => {
    setEditingRecord(null)
    form.resetFields()
    form.setFieldsValue({ owner_confirmed: false, department_head_confirmed: false, reminder_status: 'pending' })
    setOpen(true)
  }, [form])

  const openEdit = useCallback((record: CapaPlanTrackItem) => {
    setEditingRecord(record)
    form.setFieldsValue({
      capa_id: record.capa_id,
      plan_content: record.plan_content,
      due_date: record.due_date,
      owner_name: record.owner_name,
      owner_confirmed: record.owner_confirmed,
      department_head: record.department_head,
      department_head_confirmed: record.department_head_confirmed,
      progress: record.progress,
      reminder_status: record.reminder_status,
    })
    setOpen(true)
  }, [form])

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields()
    try {
      setSaving(true)
      if (editingRecord) {
        await updateCapaPlanTrackAction(editingRecord.id, values)
        message.success('CAPA计划跟踪已更新')
      } else {
        await createCapaPlanTrackAction(values)
        message.success('CAPA计划跟踪已创建')
      }
      setOpen(false)
      queryClient.invalidateQueries({ queryKey: ['quality-capa-plan'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存CAPA计划跟踪失败'))
    } finally {
      setSaving(false)
    }
  }, [editingRecord, form, queryClient, message])

  const handleDelete = useCallback(async (recordId: string) => {
    try {
      await deleteCapaPlanTrackAction(recordId)
      message.success('CAPA计划跟踪已删除')
      queryClient.invalidateQueries({ queryKey: ['quality-capa-plan'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除CAPA计划跟踪失败'))
    }
  }, [queryClient, message])

  const handlePullFromFeishu = async () => {
    setPulling(true)
    try {
      const result = await syncCapaPlanTracksFromFeishu()
      message.success(`从飞书拉取完成：成功 ${result.synced ?? 0} 条，失败 ${result.failed ?? 0} 条`)
      queryClient.invalidateQueries({ queryKey: ['quality-capa-plan'] })
    } catch (err) {
      message.error(getErrorMessage(err, '从飞书拉取失败'))
    } finally {
      setPulling(false)
    }
  }

  return (
    <div>
      <div className="mb-4">
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / CAPA管理 / 计划跟踪</p>
        <Typography.Title level={3} style={{ margin: 0 }}>CAPA计划跟踪</Typography.Title>
      </div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Button type="primary" onClick={openCreate}>新增计划跟踪</Button>
        <Button icon={<SyncOutlined />} loading={pulling} onClick={() => void handlePullFromFeishu()}>拉取飞书</Button>
        <Link href="/quality/capas/ledger"><Button>查看CAPA台账</Button></Link>
        <Link href="/quality/capas/new"><Button>新建CAPA</Button></Link>
      </Space>
      <Table<CapaPlanTrackItem>
        rowKey="id"
        loading={loading}
        columns={[
          ...columns,
          {
            title: '操作',
            key: 'action',
            width: 150,
            render: (_, record) => (
              <Space>
                <Button type="link" onClick={() => openEdit(record)}>编辑</Button>
                <Popconfirm title="确认删除？" onConfirm={() => void handleDelete(record.id)}>
                  <Button type="link" danger>删除</Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
        dataSource={items}
        pagination={false}
        scroll={{ x: 1200 }}
      />
      <Modal
        title={editingRecord ? '编辑CAPA计划跟踪' : '新增CAPA计划跟踪'}
        open={open}
        onOk={() => void handleSubmit()}
        onCancel={() => setOpen(false)}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="capa_id" label="CAPA记录" rules={[{ required: true, message: '请选择CAPA记录' }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={capaOptions.map((item) => ({
                value: item.id,
                label: `${item.capa_code} / ${item.title ?? '-'}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="plan_content" label="计划内容" rules={[{ required: true, message: '请输入计划内容' }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="due_date" label="完成时间"><Input placeholder="2026-07-15" /></Form.Item>
          <Form.Item name="owner_name" label="责任人">
            <Select
              showSearch
              allowClear
              placeholder="选择或输入责任人"
              options={contactOptions}
              filterOption={(input, option) =>
                String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
              onChange={(value: string) => {
                const contact = contactOptions.find((c) => c.value === value)
                if (contact?.department) {
                  form.setFieldsValue({ department_head: contact.department })
                }
              }}
            />
          </Form.Item>
          <Form.Item name="owner_confirmed" valuePropName="checked"><Checkbox>责任人已确认</Checkbox></Form.Item>
          <Form.Item name="department_head" label="部门负责人">
            <Select
              showSearch
              allowClear
              placeholder="选择或输入部门负责人"
              options={contactOptions}
              filterOption={(input, option) =>
                String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>
          <Form.Item name="department_head_confirmed" valuePropName="checked"><Checkbox>部门负责人已确认</Checkbox></Form.Item>
          <Form.Item name="progress" label="进度">
            <Select allowClear options={[
              { value: 'pending', label: '待开始' },
              { value: 'in_progress', label: '进行中' },
              { value: 'completed', label: '已完成' },
            ]} />
          </Form.Item>
          <Form.Item name="reminder_status" label="提醒状态">
            <Select options={[
              { value: 'pending', label: '待提醒' },
              { value: 'reminded', label: '已提醒' },
              { value: 'confirmed', label: '已确认' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
