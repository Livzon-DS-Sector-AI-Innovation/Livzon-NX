'use client'

import { useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import { App, Button, Card, DatePicker, Form, Input, Modal, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { CheckOutlined, EditOutlined, PlusOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'

import { closeNonConformingEvent, confirmShiftHandover, createNonConformingEvent, createShiftHandover, createShiftLog, getNonConformingEvents, getShiftHandovers, getShiftLogs, updateNonConformingEvent, updateShiftHandover, updateShiftLog } from '@/actions/production'
import type { components } from '@/types/generated/schema'

type Event = components['schemas']['NonConformingEventResponse']
type EventCreate = components['schemas']['NonConformingEventCreate']
type EventUpdate = components['schemas']['NonConformingEventUpdate']
type ShiftLog = components['schemas']['ShiftLogResponse']
type ShiftLogCreate = components['schemas']['ShiftLogCreate']
type ShiftLogUpdate = components['schemas']['ShiftLogUpdate']
type Handover = components['schemas']['ShiftHandoverResponse']
type HandoverCreate = components['schemas']['ShiftHandoverCreate']
type HandoverUpdate = components['schemas']['ShiftHandoverUpdate']
type Kind = 'event' | 'log' | 'handover'

interface Props { initialEvents: Event[]; initialLogs: ShiftLog[]; initialHandovers: Handover[] }
interface FormValues {
  workshop: string; shift?: 'morning' | 'afternoon' | 'night'; occurred_at: Dayjs
  event_type?: string; position?: string; handover_from?: string; handover_to?: string
  summary?: string; equipment_status?: string; pending_tasks?: string; remarks?: string
}

const shifts = [{ value: 'morning', label: '早班' }, { value: 'afternoon', label: '中班' }, { value: 'night', label: '晚班' }]
const shiftLabel = Object.fromEntries(shifts.map(item => [item.value, item.label]))

export function ShiftOperationsClient({ initialEvents, initialLogs, initialHandovers }: Props) {
  const { message } = App.useApp()
  const [events, setEvents] = useState(initialEvents)
  const [logs, setLogs] = useState(initialLogs)
  const [handovers, setHandovers] = useState(initialHandovers)
  const [kind, setKind] = useState<Kind | null>(null)
  const [editing, setEditing] = useState<Event | ShiftLog | Handover | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<FormValues>()

  const reload = async () => {
    const [eventResult, logResult, handoverResult] = await Promise.all([getNonConformingEvents(), getShiftLogs(), getShiftHandovers()])
    if (eventResult.code === 200) setEvents(eventResult.data || [])
    if (logResult.code === 200) setLogs(logResult.data || [])
    if (handoverResult.code === 200) setHandovers(handoverResult.data || [])
  }

  const open = (nextKind: Kind) => {
    setEditing(null)
    setKind(nextKind)
    form.resetFields()
    form.setFieldsValue({ workshop: '203', shift: 'morning', occurred_at: dayjs() })
  }

  const openEdit = (nextKind: Kind, row: Event | ShiftLog | Handover) => {
    setKind(nextKind)
    setEditing(row)
    if (nextKind === 'event') {
      const event = row as Event
      form.setFieldsValue({ workshop: event.workshop, occurred_at: dayjs(event.event_time), event_type: event.event_type, summary: event.description || undefined, pending_tasks: event.action_taken || undefined, remarks: event.remarks || undefined })
    } else if (nextKind === 'log') {
      const log = row as ShiftLog
      form.setFieldsValue({ workshop: log.workshop, occurred_at: dayjs(log.log_date), shift: log.shift as FormValues['shift'], handover_from: log.handover_from, handover_to: log.handover_to, summary: log.production_summary || undefined, equipment_status: log.equipment_status || undefined, pending_tasks: log.pending_tasks || undefined, remarks: log.remarks || undefined })
    } else {
      const handover = row as Handover
      form.setFieldsValue({ workshop: handover.workshop, occurred_at: dayjs(handover.handover_time), shift: handover.shift as FormValues['shift'], position: handover.position, handover_from: handover.handover_from, handover_to: handover.handover_to, summary: handover.production_status || undefined, equipment_status: handover.equipment_status || undefined, remarks: handover.remarks || undefined })
    }
  }

  const submit = async () => {
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      let response
      if (kind === 'event') {
        const payload = {
        event_time: values.occurred_at.toISOString(), event_type: values.event_type!,
        workshop: values.workshop, description: values.summary, action_taken: values.pending_tasks,
        status: 'open', related_batch_nos: [], remarks: values.remarks,
        }
        response = editing
          ? await updateNonConformingEvent(editing.id, payload satisfies EventUpdate)
          : await createNonConformingEvent(payload satisfies EventCreate)
      } else if (kind === 'log') {
        const payload = {
        log_date: values.occurred_at.format('YYYY-MM-DD'), shift: values.shift!,
        workshop: values.workshop, handover_from: values.handover_from!, handover_to: values.handover_to!,
        production_summary: values.summary, equipment_status: values.equipment_status,
        pending_tasks: values.pending_tasks, remarks: values.remarks,
        }
        response = editing
          ? await updateShiftLog(editing.id, payload satisfies ShiftLogUpdate)
          : await createShiftLog(payload satisfies ShiftLogCreate)
      } else {
        const payload = {
        position: values.position!, workshop: values.workshop, shift: values.shift!,
        handover_time: values.occurred_at.toISOString(), handover_from: values.handover_from!,
        handover_to: values.handover_to!, production_status: values.summary,
        equipment_status: values.equipment_status, remarks: values.remarks,
        }
        response = editing
          ? await updateShiftHandover(editing.id, payload satisfies HandoverUpdate)
          : await createShiftHandover(payload satisfies HandoverCreate)
      }
      if (response.code !== 200) throw new Error(response.message)
      message.success('记录已保存')
      setKind(null); setEditing(null); form.resetFields(); await reload()
    } catch (error) { message.error(error instanceof Error ? error.message : '保存失败') }
    finally { setSubmitting(false) }
  }

  const closeEvent = async (id: string) => {
    const result = await closeNonConformingEvent(id)
    if (result.code === 200) message.success('事件已关闭')
    else message.error(result.message)
    await reload()
  }
  const confirmHandover = async (id: string) => {
    const result = await confirmShiftHandover(id)
    if (result.code === 200) message.success('接班已确认')
    else message.error(result.message)
    await reload()
  }

  const eventColumns: ColumnsType<Event> = [
    { title: '发生时间', dataIndex: 'event_time', render: value => dayjs(value).format('YYYY-MM-DD HH:mm') },
    { title: '车间', dataIndex: 'workshop' }, { title: '类型', dataIndex: 'event_type' },
    { title: '事件描述', dataIndex: 'description', ellipsis: true },
    { title: '影响时长', dataIndex: 'impact_duration', render: value => value || '-' },
    { title: '状态', dataIndex: 'status', render: value => <Tag color={value === 'closed' ? 'success' : 'warning'}>{value}</Tag> },
    { title: '操作', render: (_, row) => <Space><Button type="link" icon={<EditOutlined />} onClick={() => openEdit('event', row)}>编辑</Button>{row.status !== 'closed' && <Button type="link" icon={<StopOutlined />} onClick={() => closeEvent(row.id)}>关闭</Button>}</Space> },
  ]
  const logColumns: ColumnsType<ShiftLog> = [
    { title: '日期', dataIndex: 'log_date' }, { title: '车间', dataIndex: 'workshop' },
    { title: '班次', dataIndex: 'shift', render: value => shiftLabel[value] || value },
    { title: '交班人', dataIndex: 'handover_from' }, { title: '接班人', dataIndex: 'handover_to' },
    { title: '生产摘要', dataIndex: 'production_summary', ellipsis: true },
    { title: '待办', dataIndex: 'pending_tasks', ellipsis: true },
    { title: '操作', render: (_, row) => <Button type="link" icon={<EditOutlined />} onClick={() => openEdit('log', row)}>编辑</Button> },
  ]
  const handoverColumns: ColumnsType<Handover> = [
    { title: '交接时间', dataIndex: 'handover_time', render: value => dayjs(value).format('YYYY-MM-DD HH:mm') },
    { title: '车间/岗位', render: (_, row) => `${row.workshop} / ${row.position}` },
    { title: '班次', dataIndex: 'shift', render: value => shiftLabel[value] || value },
    { title: '交班 → 接班', render: (_, row) => `${row.handover_from} → ${row.handover_to}` },
    { title: '状态', dataIndex: 'status', render: value => <Tag color={value === 'confirmed' ? 'success' : 'processing'}>{value}</Tag> },
    { title: '操作', render: (_, row) => row.status !== 'confirmed' && <Space><Button type="link" icon={<EditOutlined />} onClick={() => openEdit('handover', row)}>编辑</Button><Button type="link" icon={<CheckOutlined />} onClick={() => confirmHandover(row.id)}>确认接班</Button></Space> },
  ]

  const addButton = (buttonKind: Kind, label: string) => <Button type="primary" icon={<PlusOutlined />} onClick={() => open(buttonKind)} style={{ marginBottom: 16 }}>{label}</Button>
  return <Space orientation="vertical" size={16} style={{ width: '100%' }}>
    <Space style={{ width: '100%', justifyContent: 'space-between' }}><div><Typography.Title level={3} style={{ margin: 0 }}>生产日志与交接</Typography.Title><Typography.Text type="secondary">非保密事件、班次运行摘要和接班确认统一留痕</Typography.Text></div><Button icon={<ReloadOutlined />} onClick={reload}>刷新</Button></Space>
    <Card><Tabs items={[
      { key: 'events', label: `非保密事件 (${events.length})`, children: <>{addButton('event', '登记事件')}<Table rowKey="id" dataSource={events} columns={eventColumns} scroll={{ x: 900 }} /></> },
      { key: 'logs', label: `班次日志 (${logs.length})`, children: <>{addButton('log', '新增班次日志')}<Table rowKey="id" dataSource={logs} columns={logColumns} scroll={{ x: 900 }} /></> },
      { key: 'handovers', label: `交接确认 (${handovers.length})`, children: <>{addButton('handover', '发起交接')}<Table rowKey="id" dataSource={handovers} columns={handoverColumns} scroll={{ x: 900 }} /></> },
      { key: 'summary', label: '运行摘要', children: <Space size={16} wrap><Card size="small"><Typography.Text type="secondary">未关闭事件</Typography.Text><Typography.Title level={2}>{events.filter(item => item.status !== 'closed').length}</Typography.Title></Card><Card size="small"><Typography.Text type="secondary">班次日志</Typography.Text><Typography.Title level={2}>{logs.length}</Typography.Title></Card><Card size="small"><Typography.Text type="secondary">待确认交接</Typography.Text><Typography.Title level={2}>{handovers.filter(item => item.status !== 'confirmed').length}</Typography.Title></Card></Space> },
    ]} /></Card>
    <Modal open={kind !== null} title={`${editing ? '编辑' : '新增'}${kind === 'event' ? '非保密事件' : kind === 'log' ? '班次日志' : '班组交接'}`} onCancel={() => { setKind(null); setEditing(null) }} onOk={submit} confirmLoading={submitting} width={680} destroyOnHidden>
      <Form form={form} layout="vertical">
        <Space.Compact block><Form.Item name="workshop" label="车间" rules={[{ required: true }]} style={{ width: '50%' }}><Input /></Form.Item><Form.Item name="occurred_at" label={kind === 'event' ? '发生时间' : kind === 'log' ? '日志日期' : '交接时间'} rules={[{ required: true }]} style={{ width: '50%' }}><DatePicker showTime={kind !== 'log'} style={{ width: '100%' }} /></Form.Item></Space.Compact>
        {kind === 'event' ? <Form.Item name="event_type" label="事件类型" rules={[{ required: true }]}><Select options={[{ value: 'equipment', label: '设备' }, { value: 'process', label: '工艺' }, { value: 'quality', label: '质量' }, { value: 'safety', label: '安全' }, { value: 'other', label: '其他' }]} /></Form.Item> : <><Space.Compact block><Form.Item name="shift" label="班次" rules={[{ required: true }]} style={{ width: '50%' }}><Select options={shifts} /></Form.Item>{kind === 'handover' && <Form.Item name="position" label="岗位" rules={[{ required: true }]} style={{ width: '50%' }}><Input /></Form.Item>}</Space.Compact><Space.Compact block><Form.Item name="handover_from" label="交班人" rules={[{ required: true }]} style={{ width: '50%' }}><Input /></Form.Item><Form.Item name="handover_to" label="接班人" rules={[{ required: true }]} style={{ width: '50%' }}><Input /></Form.Item></Space.Compact></>}
        <Form.Item name="summary" label={kind === 'event' ? '事件描述' : '生产运行情况'}><Input.TextArea rows={3} /></Form.Item>
        {kind !== 'event' && <Form.Item name="equipment_status" label="设备运行情况"><Input.TextArea rows={2} /></Form.Item>}
        <Form.Item name="pending_tasks" label={kind === 'event' ? '处理措施' : '待办事项'}><Input.TextArea rows={2} /></Form.Item>
        <Form.Item name="remarks" label="备注"><Input.TextArea rows={2} /></Form.Item>
      </Form>
    </Modal>
  </Space>
}
