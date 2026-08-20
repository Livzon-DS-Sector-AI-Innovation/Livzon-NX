'use client'

import { useEffect, useState } from 'react'
import { Table, Button, Space, Input, Select, Modal, Form, DatePicker, Card, Typography, App, Descriptions, Row, Col, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { PlusOutlined, SearchOutlined, EditOutlined, DeleteOutlined, AlertOutlined } from '@ant-design/icons'
import { getNCEs, createNCE, updateNCE, deleteNCE } from '@/actions/nce'
import type { NCERecord, NCECreate } from '@/types/nce'
import { EVENT_TYPES, WORKSHOP_OPTIONS } from '@/types/nce'
import dayjs from 'dayjs'

const { Title, Text } = Typography
const { TextArea } = Input

export default function DeviationPage() {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [records, setRecords] = useState<NCERecord[]>([])
  const [modalVisible, setModalVisible] = useState(false)
  const [editing, setEditing] = useState<NCERecord | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [workshopFilter, setWorkshopFilter] = useState<string | undefined>()
  const [typeFilter, setTypeFilter] = useState<string | undefined>()
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null)
  const [detailVisible, setDetailVisible] = useState(false)
  const [detailRecord, setDetailRecord] = useState<NCERecord | null>(null)
  const [affectedBatches, setAffectedBatches] = useState<any[]>([])

  const load = async () => {
    setLoading(true)
    try {
      const p: Record<string, unknown> = { page: 1, page_size: 200 }
      if (workshopFilter) p.workshop = workshopFilter
      if (typeFilter) p.event_type = typeFilter
      if (dateRange) { p.date_from = dateRange[0].format('YYYY-MM-DD'); p.date_to = dateRange[1].format('YYYY-MM-DD') }
      const res = await getNCEs(p)
      if (res.code === 200) setRecords(res.data)
      else message.error('加载失败')
    } catch { message.error('加载失败') }
    finally { setLoading(false) }
  }

   
   
   
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps

  const openForm = (r?: NCERecord) => {
    setEditing(r || null)
    if (r) editForm.setFieldsValue({ ...r, event_time: dayjs(r.event_time), restore_time: r.restore_time ? dayjs(r.restore_time) : null })
    else form.resetFields()
    setModalVisible(true)
  }

  const handleDelete = (id: string) => {
    modal.confirm({
      title: '确认删除', onOk: async () => {
        const res = await deleteNCE(id)
        if (res.code === 200) { message.success('已删除'); load() }
        else message.error(res.message || '删除失败')
      },
    })
  }

  const handleSubmit = async () => {
    try {
      const vals = editing ? await editForm.validateFields() : await form.validateFields()
      const et = vals.event_time; const rt = vals.restore_time
      let impact = ''
      if (et && rt) {
        const diff = dayjs(rt).diff(dayjs(et), 'minute')
        const h = Math.floor(diff / 60); const m = diff % 60
        impact = diff >= 0 ? `${h > 0 ? h + 'h' : ''}${m}min` : ''
      }
      const data: Record<string, unknown> = {
        event_time: et?.toISOString?.() || et,
        restore_time: rt?.toISOString?.() || rt || null,
        impact_duration: impact || null,
        event_type: vals.event_type,
        workshop: vals.workshop,
        description: vals.description || null,
        impact_scope: vals.impact_scope || null,
        action_taken: vals.action_taken || null,
        remarks: vals.remarks || null,
      }
      if (editing) {
        const res = await updateNCE(editing.id, data)
        if (res.code === 200) { message.success('已更新'); setModalVisible(false); load() }
        else message.error(res.message || '更新失败')
      } else {
        const res = await createNCE(data as unknown as NCECreate)
        if (res.code === 200) { message.success('已创建'); setModalVisible(false); form.resetFields(); load() }
        else message.error(res.message || '创建失败')
      }
    } catch { message.error('请检查表单') }
  }

  const columns: ColumnsType<NCERecord> = [
    { title: '发生时间', dataIndex: 'event_time', width: 150, render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm') },
    { title: '事件类型', dataIndex: 'event_type', width: 110, render: (v: string) => <Tag>{v}</Tag> },
    { title: '车间', dataIndex: 'workshop', width: 100 },
    { title: '事件描述', dataIndex: 'description', width: 200, ellipsis: true, render: (v: string | null) => v || '-' },
    { title: '影响范围', dataIndex: 'impact_scope', width: 160, ellipsis: true, render: (v: string | null) => v || '-' },
    { title: '处理措施', dataIndex: 'action_taken', width: 160, ellipsis: true, render: (v: string | null) => v || '-' },
    { title: '影响时间', dataIndex: 'impact_duration', width: 90, render: (v: string | null) => v || '-' },
    {
      title: '操作', key: 'action', width: 160, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Button type="link" size="small" onClick={async () => {
            setDetailRecord(r); setDetailVisible(true); setAffectedBatches([])
            try { const res = await fetch(`http://localhost:8000/api/v1/production/non-conforming-events/${r.id}/affected-batches`); const j = await res.json(); if (j.code === 200) setAffectedBatches(j.data) } catch {}
          }}>详情</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openForm(r)}>编辑</Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r.id)}>删除</Button>
        </Space>
      ),
    },
  ]

  return (
    <div className="p-6">
      <Title level={4}><AlertOutlined className="mr-2" />非密事件与运行偏差</Title>
      <Text type="secondary">记录设备微调、公用工程波动等非密事件及处理措施</Text>

      <Card className="mt-4" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openForm()}>新建事件</Button>}>
        <Row gutter={16} className="mb-4">
          <Col span={5}><Select placeholder="车间" allowClear value={workshopFilter} onChange={v => { setWorkshopFilter(v); setPage(1) }} style={{ width: '100%' }} options={WORKSHOP_OPTIONS.map(w => ({ value: w, label: w }))} showSearch /></Col>
          <Col span={4}><Select placeholder="事件类型" allowClear value={typeFilter} onChange={v => { setTypeFilter(v); setPage(1) }} style={{ width: '100%' }} options={EVENT_TYPES.map(t => ({ value: t, label: t }))} /></Col>
          <Col span={6}><DatePicker.RangePicker style={{ width: '100%' }} value={dateRange} onChange={v => setDateRange(v as [dayjs.Dayjs, dayjs.Dayjs] | null)} placeholder={['开始日期', '结束日期']} /></Col>
          <Col><Button type="primary" icon={<SearchOutlined />} onClick={() => { setPage(1); load() }}>查询</Button></Col>
        </Row>
        <Table columns={columns} dataSource={records.slice((page - 1) * pageSize, page * pageSize)} rowKey="id" loading={loading} scroll={{ x: 1000 }}
          pagination={{ current: page, pageSize, total: records.length, showSizeChanger: true, showTotal: t => `共 ${t} 条`, onChange: (p, ps) => { setPage(p); setPageSize(ps) } }} />
      </Card>

      <Modal title={editing ? '编辑事件' : '新建事件'} open={modalVisible} onOk={handleSubmit} onCancel={() => setModalVisible(false)} width={720} okText="确认" cancelText="取消" destroyOnHidden>
        <Form form={editing ? editForm : form} layout="vertical">
          <Row gutter={16}>
            <Col span={8}><Form.Item name="event_time" label="发生时间" rules={[{ required: true }]}><DatePicker showTime style={{ width: '100%' }} format="YYYY-MM-DD HH:mm" /></Form.Item></Col>
            <Col span={8}><Form.Item name="restore_time" label="恢复正常时间"><DatePicker showTime style={{ width: '100%' }} format="YYYY-MM-DD HH:mm" /></Form.Item></Col>
            <Col span={8}><Form.Item label="影响时间（提交时自动计算）"><Input disabled placeholder="自动计算" /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}><Form.Item name="event_type" label="事件类型" rules={[{ required: true }]}><Select options={EVENT_TYPES.map(t => ({ value: t, label: t }))} /></Form.Item></Col>
            <Col span={8}><Form.Item name="workshop" label="车间" rules={[{ required: true }]}><Select options={WORKSHOP_OPTIONS.map(w => ({ value: w, label: w }))} showSearch /></Form.Item></Col>
          </Row>
          <Form.Item name="description" label="事件描述"><TextArea rows={2} placeholder="事件的具体情况" /></Form.Item>
          <Form.Item name="impact_scope" label="影响范围"><TextArea rows={2} placeholder="对生产、质量、安全等方面的影响" /></Form.Item>
          <Form.Item name="action_taken" label="处理措施"><TextArea rows={2} placeholder="采取的处理措施及结果" /></Form.Item>
          <Form.Item name="remarks" label="备注"><TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <Modal title="事件详情" open={detailVisible} onCancel={() => setDetailVisible(false)} footer={null} width={640}>
        {detailRecord && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="发生时间">{dayjs(detailRecord.event_time).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
            <Descriptions.Item label="恢复正常时间">{detailRecord.restore_time ? dayjs(detailRecord.restore_time).format('YYYY-MM-DD HH:mm') : '-'}</Descriptions.Item>
            <Descriptions.Item label="影响时间">{detailRecord.impact_duration || '-'}</Descriptions.Item>
            <Descriptions.Item label="事件类型"><Tag>{detailRecord.event_type}</Tag></Descriptions.Item>
            <Descriptions.Item label="车间">{detailRecord.workshop}</Descriptions.Item>
            <Descriptions.Item label="事件描述" span={2}><div style={{ whiteSpace: 'pre-wrap' }}>{detailRecord.description || '-'}</div></Descriptions.Item>
            <Descriptions.Item label="影响范围" span={2}><div style={{ whiteSpace: 'pre-wrap' }}>{detailRecord.impact_scope || '-'}</div></Descriptions.Item>
            <Descriptions.Item label="处理措施" span={2}><div style={{ whiteSpace: 'pre-wrap' }}>{detailRecord.action_taken || '-'}</div></Descriptions.Item>
            <Descriptions.Item label="备注" span={2}>{detailRecord.remarks || '-'}</Descriptions.Item>
          </Descriptions>
        )}
        {affectedBatches.length > 0 && (
          <div className="mt-4">
            <Text strong>受影响批次（{affectedBatches.length}）：</Text>
            <Card size="small" className="mt-2">
              {affectedBatches.map((b: any) => (
                <div key={b.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '4px 0', borderBottom: '1px solid #f0f0f0' }}>
                  <Tag color="blue">{b.fermenter}</Tag><Text strong>{b.batch_no}</Text>
                  <Text type="secondary">{b.product_name}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>进罐: {b.entry_date?.slice(0, 10)}</Text>
                  <Tag color="processing">运行中</Tag>
                </div>
              ))}
            </Card>
          </div>
        )}
      </Modal>
    </div>
  )
}
