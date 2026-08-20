'use client'
import {useEffect, useState, useCallback,} from 'react'
import { Table, Button, Space, Modal, Form, Input, InputNumber, DatePicker, Card, Typography, App, Row, Col, Select } from 'antd'
import { PlusOutlined, ArrowLeftOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import dayjs from 'dayjs'
import Dashboard from '@/components/production/Dashboard'
import MCSheetsSyncButton from '@/components/production/MCSheetsSyncButton'
import MCTraceButton from '@/components/production/MCTraceButton'

const { Title, Text } = Typography
const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
const BASE = '/api/v1/production/mc'

const STAGES = [
  { key: 'crude', label: '粗提', path: '/production/batches/workshop/201-2/crude-extraction' },
  { key: 'extraction', label: '提取', path: '/production/batches/workshop/201-2/extraction' },
  { key: 'refinement', label: 'MC二次精制', path: '/production/batches/workshop/201-2/mc-refinement' },
  { key: 'blending', label: '混粉杂质计算', path: '/production/batches/workshop/201-2/blending' },
  { key: 'qc', label: '混粉入库', path: '/production/batches/workshop/201-2/qc-inspection', active: true },
  { key: 'ba', label: '丁酯盘点', path: '/production/batches/workshop/201-2/butyl-acetate' },
  { key: 'traceability', label: '全链路追溯', path: '/production/batches/workshop/201-2/traceability' },
]

async function api(path: string, opts?: RequestInit) {
  const r = await fetch(`${API}${BASE}${path}`, { headers: { 'Content-Type': 'application/json' }, ...opts })
  return r.json()
}

function CellInput({ value, onSave }: { value: number | null | undefined; onSave: (v: number | null) => void }) {
  const [editing, setEditing] = useState(false)
  if (!editing) return <div style={{ width: '100%', height: 20, cursor: 'text', fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setEditing(true)}>{value != null ? value : ''}</div>
  return <InputNumber size="small" autoFocus style={{ width: '100%' }} defaultValue={value ?? undefined}
    onBlur={e => { setEditing(false); const raw = e.target.value; if (raw === '' || raw === '-') { onSave(null); return } const n = Number(raw); if (!isNaN(n)) onSave(n) }}
    onPressEnter={(e: any) => { setEditing(false); const raw = e.target.value; if (raw === '' || raw === '-') { onSave(null); return } const n = Number(raw); if (!isNaN(n)) onSave(n) }} />
}

function DateCellInput({ value, onSave }: { value: string | null | undefined; onSave: (v: string | null) => void }) {
  const [editing, setEditing] = useState(false)
  if (!editing) return <div style={{ width: '100%', height: 20, cursor: 'text', fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setEditing(true)}>{value ?? ''}</div>
  return <DatePicker size="small" autoFocus open style={{ width: '100%', fontSize: 10 }} defaultValue={value ? dayjs(value) : undefined} format="YYYY.MM.DD"
    onChange={d => { setEditing(false); onSave(d ? d.format('YYYY-MM-DD') : null) }}
    onOpenChange={open => { if (!open) setEditing(false) }} />
}

function TextCellInput({ value, onSave }: { value: string | null | undefined; onSave: (v: string | null) => void }) {
  const [editing, setEditing] = useState(false)
  if (!editing) return <div style={{ width: '100%', height: 20, cursor: 'text', fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setEditing(true)}>{value ?? ''}</div>
  return <Input size="small" autoFocus style={{ width: '100%', fontSize: 10, height: 20, padding: '0 2px' }} defaultValue={value ?? ''} onBlur={e => { setEditing(false); onSave(e.target.value || null) }} />
}

export default function QcInspectionPage() {
  const router = useRouter(); const { message, modal } = App.useApp()
  const [form] = Form.useForm()
  const [records, setRecords] = useState<any[]>([]); const [loading, setLoading] = useState(false); const [saving, setSaving] = useState(false)
  const [month, setMonth] = useState<number>(dayjs().month() + 1)
  const [createVisible, setCreateVisible] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    const params = month > 0 ? `?month=${month}` : ''
    try { const r = await api(`/qc-inspections/full-list${params}`); if (r.code === 200) setRecords(r.data) } catch { message.error('加载失败') } finally { setLoading(false) }
  }, [message, month])
  useEffect(() => { load() }, [load]) // eslint-disable-line react-hooks/set-state-in-effect

  const saveRecord = async (id: string, field: string, value: any) => {
    setSaving(true); await api(`/qc-inspections/${id}`, { method: 'PUT', body: JSON.stringify({ [field]: value }) }); setSaving(false); load()
  }

  const saveInput = async (input: any, field: string, value: any) => {
    setSaving(true); await api(`/qc-inputs/${input.id}`, { method: 'PUT', body: JSON.stringify({ [field]: value }) }); setSaving(false); load()
  }

  const addInputRow = async (qcBatch: string) => {
    setSaving(true); await api('/qc-inputs', { method: 'POST', body: JSON.stringify({ qc_batch: qcBatch, input_batch: '', dry_weight: 0 }) }); setSaving(false); load()
  }

  const handleCreate = async () => {
    try { const vals = await form.validateFields(); if (vals.input_date) vals.input_date = dayjs(vals.input_date).format('YYYY-MM-DD'); const r = await api('/qc-inspections', { method: 'POST', body: JSON.stringify(vals) }); if (r.code === 200) { message.success('创建成功'); setCreateVisible(false); form.resetFields(); load() } else message.error(r.message || '创建失败') }
    catch { message.error('请检查表单') }
  }

  const flattenData = () => {
    const rows: any[] = []
    for (const rec of records) { const inputs = rec.inputs || []; const c = Math.max(inputs.length, 1); for (let i = 0; i < c; i++) rows.push({ ...rec, input: inputs[i] || {}, _key: `${rec.id}-${i}`, _rowCount: c, _isFirst: i === 0 }) }
    return rows
  }

  const M = (content: any, r: any) => (r._isFirst ? content : null)
  const onCell = (r: any) => { const rowSpan = r._isFirst ? r._rowCount : 0; return { rowSpan, style: rowSpan > 1 ? { verticalAlign: 'middle' } : undefined } as any }

  const columns: any[] = [
    { title: '日期', dataIndex: 'input_date', width: 72, fixed: 'left', render: (_: any, r: any) => M(<DateCellInput value={r.input_date} onSave={v => saveRecord(r.id, 'input_date', v)} />, r), onCell },
    { title: '成品\n后台批号', dataIndex: 'batch_no', width: 100, fixed: 'left', render: (_: any, r: any) => M(<Text strong style={{ fontSize: 10 }}>{r.batch_no}</Text>, r), onCell },
    { title: '单批\n批号', key: 'inp_batch', width: 110, render: (_: any, r: any) => <TextCellInput value={r.input?.input_batch} onSave={v => saveInput(r.input, 'input_batch', v)} /> },
    { title: '干粉', key: 'inp_dry', width: 55, render: (_: any, r: any) => <CellInput value={r.input?.dry_weight} onSave={v => saveInput(r.input, 'dry_weight', v)} /> },
    { title: '规格', dataIndex: 'pack_spec', width: 75, render: (_: any, r: any) => M(<TextCellInput value={r.pack_spec} onSave={v => saveRecord(r.id, 'pack_spec', v)} />, r), onCell },
    { title: '入库\n重量(kg)', dataIndex: 'warehouse_weight', width: 75, render: (_: any, r: any) => M(<CellInput value={r.warehouse_weight} onSave={v => saveRecord(r.id, 'warehouse_weight', v)} />, r), onCell },
    { title: '桶数', dataIndex: 'barrel_count', width: 55, render: (_: any, r: any) => M(<TextCellInput value={r.barrel_count} onSave={v => saveRecord(r.id, 'barrel_count', v)} />, r), onCell },
    { title: '请检标准', dataIndex: 'inspection_std', width: 130, render: (_: any, r: any) => M(<TextCellInput value={r.inspection_std} onSave={v => saveRecord(r.id, 'inspection_std', v)} />, r), onCell },
    { title: '前台批号', dataIndex: 'front_batch_no', width: 110, render: (_: any, r: any) => M(<TextCellInput value={r.front_batch_no} onSave={v => saveRecord(r.id, 'front_batch_no', v)} />, r), onCell },
    { title: '累计\n重量(kg)', dataIndex: 'cumulative_weight', width: 75, render: (_: any, r: any) => M(<CellInput value={r.cumulative_weight} onSave={v => saveRecord(r.id, 'cumulative_weight', v)} />, r), onCell },
    { title: '操作', key: 'act', width: 50, fixed: 'right', render: (_: any, r: any) => M(<Button type="link" size="small" danger onClick={() => modal.confirm({ title: `删除 ${r.batch_no}?`, onOk: async () => { await api(`/qc-inspections/${r.id}`, { method: 'DELETE' }); load() } })} style={{ fontSize: 10 }}>删除</Button>, r), onCell },
  ]

  const batchInputCounts = []
  for (const rec of records) batchInputCounts.push({ batchNo: rec.batch_no, recordId: rec.id, count: (rec.inputs || []).length })

  return (
    <div className="p-6">
      <style>{`
        .qc-ledger-table .ant-table-thead > tr > th { white-space: normal !important; word-break: break-all; line-height: 1.15; padding: 2px 1px !important; font-size: 9px; text-align: center !important; vertical-align: middle !important; background: #fafafa; }
        .qc-ledger-table .ant-table-tbody > tr > td { white-space: normal !important; word-break: break-all; padding: 1px 2px !important; font-size: 10px; text-align: center !important; line-height: 1.2; }
        .qc-ledger-table .ant-input-number { font-size: 10px; width: 100%; } .qc-ledger-table .ant-input-number input { font-size: 10px; padding: 0 2px; text-align: center; height: 20px; }
        .qc-ledger-table .ant-input-number .ant-input-number-handler-wrap { display: none; } .qc-ledger-table .ant-picker { width: 100%; } .qc-ledger-table .ant-picker input { font-size: 10px; padding: 0 2px; text-align: center; height: 20px; }
      `}</style>

      <Card size="small" className="mb-4">
        <Space wrap>{STAGES.map(s => <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>{s.label}</Button>)}</Space>
      </Card>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <Title level={4} style={{ margin: 0 }}><Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/201-2')}>返回车间</Button>混粉入库 — QC台账（失焦自动保存）</Title>
        <Space size={8}>
          <Select size="small" style={{ width: 80 }} value={month} onChange={v => setMonth(v)}
            options={[{ value: 0, label: '全部' }, ...[1,2,3,4,5,6,7,8,9,10,11,12].map(m => ({ value: m, label: `${m}月` }))]} />
          <MCSheetsSyncButton />
          <MCTraceButton initialModule="qc" />
        </Space>
      </div>

      <Dashboard title="混粉入库仪表盘" data={records} dateField="created_at" month={month}
        cards={[
          { title: '累计入库重量', value: (_, f) => { let v = null; for (const d of f) if (d.cumulative_weight != null) v = d.cumulative_weight; return v }, suffix: 'kg', precision: 0 },
          { title: '本月入库重量', value: (_, f) => f.reduce((a, b) => a + (b.warehouse_weight || 0), 0), suffix: 'kg', precision: 0 },
          { title: '批数', value: (_, f) => f.length, suffix: '批', precision: 0 },
        ]}
        charts={[
          { key: 'warehouse_weight', title: '入库重量趋势(kg)', unit: 'kg', color: '#1890ff', label: '入库重量趋势', field: 'warehouse_weight' },
          { key: 'cumulative_weight', title: '累计重量趋势(kg)', unit: 'kg', color: '#52c41a', label: '累计重量趋势', field: 'cumulative_weight' },
        ]}
      />

      <Card extra={<Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateVisible(true) }}>新建入库单</Button>}>
        <Table size="small" rowKey="_key" loading={loading} className="qc-ledger-table" dataSource={flattenData()} scroll={{ x: 1200 }} columns={columns} pagination={false} />
        <div style={{ padding: '8px 0', display: 'flex', flexWrap: 'wrap', gap: 8, borderTop: '1px solid #f0f0f0', marginTop: 8 }}>
          {batchInputCounts.map(bic => <Button key={bic.recordId} size="small" type="dashed" loading={saving} onClick={() => addInputRow(bic.batchNo)}>+ 投入 ({bic.batchNo})</Button>)}
          {batchInputCounts.length === 0 && <Text type="secondary">暂无入库记录</Text>}
        </div>
      </Card>

      <Modal title="新建入库单" open={createVisible} onOk={handleCreate} onCancel={() => setCreateVisible(false)} width={600} okText="确认" cancelText="取消" destroyOnHidden>
        <Form form={form} layout="vertical">
          <Row gutter={16}><Col span={8}><Form.Item name="batch_no" label="成品后台批号" rules={[{ required: true }]}><Input placeholder="MC-260101" /></Form.Item></Col>
            <Col span={8}><Form.Item name="input_date" label="入库日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col></Row>
          <Row gutter={16}><Col span={8}><Form.Item name="pack_spec" label="规格"><Input placeholder="20KG/桶" /></Form.Item></Col>
            <Col span={8}><Form.Item name="warehouse_weight" label="入库重量(kg)"><InputNumber style={{ width: '100%' }} /></Form.Item></Col></Row>
          <Row gutter={16}><Col span={8}><Form.Item name="inspection_std" label="请检标准"><Input placeholder="1G/Y30/S/25" /></Form.Item></Col>
            <Col span={8}><Form.Item name="front_batch_no" label="前台批号"><Input /></Form.Item></Col></Row>
        </Form>
      </Modal>
    </div>
  )
}
