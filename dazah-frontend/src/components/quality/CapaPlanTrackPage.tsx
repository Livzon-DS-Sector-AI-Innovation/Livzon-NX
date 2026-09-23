'use client'

import { alignFeishuColumns, feishuColumnLayouts } from './feishuColumnLayout'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { App, Button, Checkbox, Descriptions, Drawer, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { SyncOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createCapaPlanTrack as createCapaPlanTrackAction, deleteCapaPlanTrack as deleteCapaPlanTrackAction, updateCapaPlanTrack as updateCapaPlanTrackAction } from '@/actions/quality-capa'
import { syncCapaPlanTracksFromFeishu } from '@/actions/quality-capa'
import { fetchCapaPlanTracks, fetchCapas } from '@/lib/api/client/quality'

import { fetchQualityPersonDirectory } from '@/lib/api/client/quality'
import { PersonCell } from './PersonCell'
import { qualityTokens } from './themeTokens'
import { progressMeta, reminderMeta, PROGRESS_OPTIONS, REMINDER_OPTIONS } from './capaPlanTrackLabels'
import { ConfirmFlag } from './ConfirmFlag'
import type { CapaPlanTrackItem, CreateCapaPlanTrackRequest } from '@/types/quality'

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export function CapaPlanTrackPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const searchParams = useSearchParams()
  const [capaCodeFilter, setCapaCodeFilter] = useState(searchParams.get('capa_code') ?? '')
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [open, setOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<CapaPlanTrackItem | null>(null)
  const [detailRecord, setDetailRecord] = useState<CapaPlanTrackItem | null>(null)
  const [form] = Form.useForm<CreateCapaPlanTrackRequest>()
  const selectedDepartment = Form.useWatch('department', form)

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-capa-plan', 'list', { capa_code: capaCodeFilter }],
    queryFn: async () => {
      const [tracks, capas] = await Promise.all([
        fetchCapaPlanTracks({ page: 1, page_size: 50, capa_code: capaCodeFilter || undefined }),
        fetchCapas({ page: 1, page_size: 50 }),
      ])
      return { items: tracks.items, capaOptions: capas.items }
    },
  })

  const { data: contacts = [] } = useQuery({
    queryKey: ['quality-person-directory'],
    queryFn: fetchQualityPersonDirectory,
    staleTime: 5 * 60 * 1000,
  })

  const avatarByName = useMemo(() => {
    const map: Record<string, string> = {}
    for (const contact of contacts) {
      if (contact.name && contact.avatar_url) map[contact.name] = contact.avatar_url
    }
    return map
  }, [contacts])

  const contactOptions = contacts.map((contact) => ({
    label: [contact.department, contact.name].filter(Boolean).join(' - '),
    value: contact.name ?? '',
    department: contact.department ?? '',
  }))

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载CAPA计划跟踪失败'))
    }
  }, [error, message])

  const items = data?.items ?? []
  const capaOptions = data?.capaOptions ?? []
  const departmentOptions = Array.from(new Set([
    ...contacts.map(item => item.department), ...items.map(item => item.department),
  ].filter((value): value is string => Boolean(value)))).map(value => ({ label: value, value }))

  const renderPersons = useCallback((value: string | null | undefined) => {
    if (!value) return <span style={{ color: qualityTokens.textMuted }}>-</span>
    const names = value
      .split(/[、，,]/)
      .map((name) => name.trim())
      .filter(Boolean)
    if (names.length === 0) return <span style={{ color: qualityTokens.textMuted }}>-</span>
    return (
      <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 2 }}>
        {names.map((name) => (
          <PersonCell key={name} name={name} avatarUrl={avatarByName[name] || null} />
        ))}
      </span>
    )
  }, [avatarByName])

  const columns = useMemo<ColumnsType<CapaPlanTrackItem>>(() => [
    { title: '关联CAPA编号', key: 'linked_capa_code', width: 170, render: (_, record) => <Link href={`/quality/capas/${record.capa_id}`}>{record.linked_capa_code || record.capa_code}</Link> },
    { title: 'CAPA编号', dataIndex: 'capa_code', key: 'capa_code', width: 170 },
    {
      title: '计划内容',
      dataIndex: 'plan_content',
      key: 'plan_content',
      width: 460,
      render: (value: string | null) => (
        <div style={{ whiteSpace: 'pre-line', wordBreak: 'break-word' }}>{value || '-'}</div>
      ),
    },
    {
      title: '责任人',
      dataIndex: 'owner_name',
      key: 'owner_name',
      width: 140,
      render: (value: string | null | undefined) => renderPersons(value),
    },
    { title: '部门', dataIndex: 'department', key: 'department', width: 140, render: (value: string | null) => value || '-' },
    {
      title: '部门负责人',
      dataIndex: 'department_head',
      key: 'department_head',
      width: 140,
      render: (value: string | null | undefined) => renderPersons(value),
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 110,
      render: (value: string | null | undefined) => {
        const { label, color } = progressMeta(value)
        return <Tag color={color}>{label}</Tag>
      },
    },
    {
      title: '提醒状态',
      dataIndex: 'reminder_status',
      key: 'reminder_status',
      width: 110,
      render: (value: string | null | undefined) => {
        const { label, color } = reminderMeta(value)
        return <Tag color={color}>{label}</Tag>
      },
    },
    { title: '预计完成时间', dataIndex: 'due_date', key: 'due_date', width: 130 },
  ], [renderPersons])

  const openCreate = useCallback(() => {
    setEditingRecord(null)
    form.resetFields()
    form.setFieldsValue({ reminder_status: 'pending' })
    setOpen(true)
  }, [form])

  const openEdit = useCallback((record: CapaPlanTrackItem) => {
    setEditingRecord(record)
    form.setFieldsValue({
      capa_id: record.capa_id,
      plan_content: record.plan_content,
      due_date: record.due_date,
      owner_name: record.owner_name,
      department: record.department,
      progress: record.progress,
      reminder_status: record.reminder_status,
    })
    setOpen(true)
  }, [form])

  const handleSubmit = useCallback(async () => {
    try {
      const values = await form.validateFields()
      delete values.department_head
      delete values.owner_confirmed
      delete values.department_head_confirmed
      setSaving(true)
      if (editingRecord) {
        const result = await updateCapaPlanTrackAction(editingRecord.id, values)
        if (result && typeof result === 'object' && 'feishu_sync_status' in result && result.feishu_sync_status === 'failed') {
          message.warning('计划已保存，但飞书同步失败，请在详情中查看同步状态后重试')
        } else {
          message.success('CAPA计划跟踪已更新')
        }
      } else {
        const result = await createCapaPlanTrackAction(values)
        if (result && typeof result === 'object' && 'feishu_sync_status' in result && result.feishu_sync_status === 'failed') {
          message.warning('计划已创建，但飞书同步失败，请在详情中查看同步状态后重试')
        } else {
          message.success('CAPA计划跟踪已创建')
        }
      }
      setOpen(false)
      queryClient.invalidateQueries({ queryKey: ['quality-capa-plan'] })
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
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
      </Space>
      {capaCodeFilter ? (
        <Tag closable onClose={() => setCapaCodeFilter('')} style={{ marginBottom: 16 }}>
          CAPA编号：{capaCodeFilter}
        </Tag>
      ) : null}
      <Table<CapaPlanTrackItem>
        rowKey="id"
        loading={loading}
        columns={[
          ...alignFeishuColumns(columns, feishuColumnLayouts.capaPlan, { due_date: '预计完成时间', department_head_confirmed: '部门负责人确认' }),
          {
            title: '操作',
            key: 'action',
            width: 200,
            render: (_, record) => (
              <Space>
                <Button type="link" onClick={() => setDetailRecord(record)}>详情</Button>
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
        scroll={{ x: columns.reduce((sum, column) => sum + Number(column.width || 160), 180) }}
      />
      <Drawer title="CAPA计划跟踪详情" open={Boolean(detailRecord)} onClose={() => setDetailRecord(null)} size="large">
        {detailRecord && <Descriptions column={1} bordered items={[
          { key: 'capa_code', label: 'CAPA编号', children: detailRecord.capa_code },
          { key: 'plan_content', label: '计划内容', children: <div style={{ whiteSpace: 'pre-line' }}>{detailRecord.plan_content}</div> },
          { key: 'due_date', label: '预计完成时间', children: detailRecord.due_date || '-' },
          { key: 'owner_name', label: '责任人', children: renderPersons(detailRecord.owner_name) },
          { key: 'owner_confirmed', label: '责任人确认', children: <ConfirmFlag confirmed={detailRecord.owner_confirmed} /> },
          { key: 'department_head', label: '部门负责人', children: renderPersons(detailRecord.department_head) },
          { key: 'department', label: '部门', children: detailRecord.department || '-' },
          { key: 'department_head_confirmed', label: '部门负责人确认', children: <ConfirmFlag confirmed={detailRecord.department_head_confirmed} /> },
          { key: 'progress', label: '进度', children: progressMeta(detailRecord.progress).label },
          { key: 'reminder_status', label: '提醒状态', children: reminderMeta(detailRecord.reminder_status).label },
          { key: 'linked_capa', label: '关联CAPA编号', children: <Link href={`/quality/capas/${detailRecord.capa_id}`}>{detailRecord.linked_capa_code || detailRecord.capa_code}</Link> },
          { key: 'sync', label: '飞书同步状态', children: detailRecord.feishu_sync_status === 'failed' ? '同步失败' : detailRecord.feishu_sync_status === 'synced' ? '已同步' : '待同步' },
          { key: 'error', label: '同步说明', children: detailRecord.feishu_last_sync_error || '-' },
        ]} />}
      </Drawer>
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
          <Form.Item name="due_date" label="预计完成时间"><Input placeholder="2026-07-15" /></Form.Item>
          <Form.Item name="owner_name" label="责任人">
            <Select
              showSearch
              allowClear
              placeholder="选择或输入责任人"
              options={contactOptions}
              filterOption={(input, option) =>
                String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }

            />
          </Form.Item>
          <Form.Item><Checkbox checked={editingRecord?.owner_confirmed ?? false} disabled>责任人已确认（自动同步）</Checkbox></Form.Item>
          <Form.Item name="department" label="部门">
            <Select showSearch allowClear optionFilterProp="label" placeholder="选择部门" options={departmentOptions} />
          </Form.Item>
          <Form.Item label="部门负责人">
            <Input aria-label="部门负责人" readOnly value={(selectedDepartment || '') === (editingRecord?.department || '') ? editingRecord?.department_head || '' : ''} placeholder="由飞书按部门自动生成" />
          </Form.Item>
          <Form.Item><Checkbox checked={editingRecord?.department_head_confirmed ?? false} disabled>部门负责人已确认（自动同步）</Checkbox></Form.Item>
          <Form.Item name="progress" label="进度">
            <Select allowClear options={PROGRESS_OPTIONS} />
          </Form.Item>
          <Form.Item name="reminder_status" label="提醒状态">
            <Select options={REMINDER_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
