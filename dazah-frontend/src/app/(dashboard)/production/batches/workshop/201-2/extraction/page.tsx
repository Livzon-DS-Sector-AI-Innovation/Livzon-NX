'use client'
import { useEffect, useState, useCallback, useMemo } from 'react'
import type { ReactNode } from 'react'
import { Table, Button, Space, Input, Modal, Form, InputNumber, DatePicker, Card, Typography, App, Row, Col, Select } from 'antd'
import type { TableColumnsType } from 'antd'
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
  { key: 'extraction', label: '提取', path: '/production/batches/workshop/201-2/extraction', active: true },
  { key: 'refinement', label: 'MC二次精制', path: '/production/batches/workshop/201-2/mc-refinement' },
  { key: 'blending', label: '混粉杂质计算', path: '/production/batches/workshop/201-2/blending' },
  { key: 'qc', label: '混粉入库', path: '/production/batches/workshop/201-2/qc-inspection' },
  { key: 'ba', label: '丁酯盘点', path: '/production/batches/workshop/201-2/butyl-acetate' },
  { key: 'traceability', label: '全链路追溯', path: '/production/batches/workshop/201-2/traceability' },
]

async function api(path: string, opts?: RequestInit) {
  const r = await fetch(`${API}${BASE}${path}`, { headers: { 'Content-Type': 'application/json' }, ...opts })
  return r.json()
}

interface ExtractionInput {
  id?: string
  crude_batch_no?: string | null
  crude_weight?: number | null
  crude_moisture?: number | null
  crude_content?: number | null
  converted_qty?: number | null
}

interface ExtractionRecord {
  id: string
  extract_date?: string | null
  batch_no?: string
  filter_potency?: number | null
  filter_volume?: number | null
  filter_product_qty?: number | null
  carbon_usage?: number | null
  wet_weight?: number | null
  wet_content?: number | null
  dry_loss?: number | null
  dry_weight?: number | null
  total_converted_qty?: number | null
  total_crude_weight?: number | null
  yield_rate?: number | null
  inputs?: ExtractionInput[]
}

interface ExtractionRow extends ExtractionRecord {
  input: ExtractionInput
  _key: string
  _rowCount: number
  _isFirst: boolean
}

function CellInput({ value, onSave, color }: { value: number | null | undefined; onSave: (v: number | null) => void; color?: string }) {
  const [editing, setEditing] = useState(false)
  if (!editing) return <div style={{ width: '100%', height: 20, cursor: 'text', color: color || undefined, fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setEditing(true)}>{value != null ? value : ''}</div>
  return <InputNumber size="small" autoFocus style={{ width: '100%', color: color || undefined }} defaultValue={value ?? undefined}
    onBlur={e => { setEditing(false); const raw = e.currentTarget.value; if (raw === '' || raw === '-') { onSave(null); return } const n = Number(raw); if (!isNaN(n)) onSave(n) }}
    onPressEnter={(e) => { setEditing(false); const raw = e.currentTarget.value; if (raw === '' || raw === '-') { onSave(null); return } const n = Number(raw); if (!isNaN(n)) onSave(n) }} />
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
  return <Input size="small" autoFocus style={{ width: '100%', fontSize: 10, height: 20, padding: '0 2px' }} defaultValue={value ?? ''} onBlur={e => { setEditing(false); onSave(e.currentTarget.value || null) }} />
}

export default function ExtractionPage() {
  const router = useRouter(); const { message, modal } = App.useApp()
  const [form] = Form.useForm()
  const [records, setRecords] = useState<ExtractionRecord[]>([]); const [loading, setLoading] = useState(false); const [saving, setSaving] = useState(false)
  const [month, setMonth] = useState<number>(dayjs().month() + 1)
  const [createVisible, setCreateVisible] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    const params = 'workshop=201-2' + (month > 0 ? `&month=${month}` : '')
    try { const r = await api(`/extraction-records/full-list?${params}`); if (r.code === 200) setRecords(r.data) } catch { message.error('加载失败') } finally { setLoading(false) }
  }, [message, month])
  useEffect(() => { load() }, [load]) // eslint-disable-line react-hooks/set-state-in-effect

  const saveRecord = async (id: string, field: string, value: number | string | null, record: ExtractionRecord) => {
    setSaving(true); const d: Record<string, unknown> = { [field]: value }
    if (field === 'filter_potency' || field === 'filter_volume') {
      const p = field === 'filter_potency' ? value : record.filter_potency
      const v = field === 'filter_volume' ? value : record.filter_volume
      d.filter_product_qty = p != null && v != null ? Math.round(Number(p) * Number(v) / 10) / 100 : null
    }
    if (field === 'wet_weight' || field === 'wet_content' || field === 'dry_loss') {
      const ww = field === 'wet_weight' ? value : record.wet_weight; const wc = field === 'wet_content' ? value : record.wet_content; const dl = field === 'dry_loss' ? value : record.dry_loss
      d.dry_weight = ww != null && wc != null && dl != null ? Math.round(Number(ww) * Number(wc) / 100 * (100 - Number(dl))) / 100 : null
    }
    if (field === 'dry_weight' || field === 'total_converted_qty') {
      const dw = field === 'dry_weight' ? value : record.dry_weight; const tc = field === 'total_converted_qty' ? value : record.total_converted_qty
      d.yield_rate = dw != null && tc != null && Number(tc) > 0 ? Math.round(Number(dw) / Number(tc) * 10000) / 100 : null
    }
    await api(`/extraction-records/${id}`, { method: 'PUT', body: JSON.stringify(d) }); setSaving(false); load()
  }

  const saveInput = async (input: ExtractionInput, field: string, value: number | string | null, _extractionBatch: string | undefined) => { // eslint-disable-line @typescript-eslint/no-unused-vars
    setSaving(true); const d: Record<string, unknown> = { [field]: value }
    if (field === 'crude_weight' || field === 'crude_moisture' || field === 'crude_content') {
      const w = (field === 'crude_weight' ? value : input.crude_weight) || 0; const m = (field === 'crude_moisture' ? value : input.crude_moisture) || 0; const c = (field === 'crude_content' ? value : input.crude_content) || 0
      d.converted_qty = Math.round(Number(w) * (1 - Number(m) / 100) * Number(c)) / 100
    }
    if (input.id) await api(`/extraction-inputs/${input.id}`, { method: 'PUT', body: JSON.stringify(d) }); setSaving(false); load()
  }

  const addInputRow = async (extractionBatch: string | undefined, currentCount: number) => {
    setSaving(true); await api('/extraction-inputs', { method: 'POST', body: JSON.stringify({ extraction_batch: extractionBatch, seq_no: currentCount + 1, crude_batch_no: '', crude_weight: 0, crude_moisture: 0, crude_content: 0 }) })
    setSaving(false); load()
  }

  const handleCreate = async () => {
    try {
      const vals = await form.validateFields(); vals.workshop = '201-2'
      if (vals.extract_date) vals.extract_date = dayjs(vals.extract_date).format('YYYY-MM-DD')
      const r = await api('/extraction-records', { method: 'POST', body: JSON.stringify(vals) })
      if (r.code === 200) { message.success('创建成功'); setCreateVisible(false); form.resetFields(); load() }
      else message.error(r.message || '创建失败')
    } catch { message.error('请检查表单') }
  }

  const flattenData = () => {
    const rows: ExtractionRow[] = []
    for (const rec of records) {
      const inputs = rec.inputs || []; const c = Math.max(inputs.length, 1)
      for (let i = 0; i < c; i++) rows.push({ ...rec, input: inputs[i] || {}, _key: `${rec.id}-${i}`, _rowCount: c, _isFirst: i === 0 })
    }
    return rows
  }

  const M = (content: ReactNode, r: ExtractionRow): ReactNode => (r._isFirst ? content : null)
  const onCell = (r: ExtractionRow) => { const rowSpan = r._isFirst ? r._rowCount : 0; return { rowSpan, style: rowSpan > 1 ? { verticalAlign: 'middle' } : undefined } }

  const columns: TableColumnsType<ExtractionRow> = [
    { title: '萃取\n生产日期', dataIndex: 'extract_date', width: 85, fixed: 'left', render: (_, r) => M(<DateCellInput value={r.extract_date} onSave={v => saveRecord(r.id, 'extract_date', v, r)} />, r), onCell },
    { title: '萃取\n批号', dataIndex: 'batch_no', width: 100, fixed: 'left', render: (_, r) => M(<Text strong style={{ fontSize: 11 }}>{r.batch_no}</Text>, r), onCell },
    { title: <><Text strong>粗品</Text><br />批号</>, key: 'inp_batch', width: 100, render: (_, r) => <TextCellInput value={r.input?.crude_batch_no} onSave={v => saveInput(r.input, 'crude_batch_no', v, r.batch_no)} /> },
    { title: <>水分<br />(%)</>, key: 'inp_m', width: 58, render: (_, r) => <CellInput value={r.input?.crude_moisture} onSave={v => saveInput(r.input, 'crude_moisture', v, r.batch_no)} /> },
    { title: <>含量<br />(%)</>, key: 'inp_c', width: 58, render: (_, r) => <CellInput value={r.input?.crude_content} onSave={v => saveInput(r.input, 'crude_content', v, r.batch_no)} /> },
    { title: '粗品\n重量', key: 'inp_w', width: 65, render: (_, r) => <CellInput value={r.input?.crude_weight} onSave={v => saveInput(r.input, 'crude_weight', v, r.batch_no)} /> },
    { title: <Text style={{ fontSize: 10 }}>折合产品重量(kg)</Text>, key: 'inp_cv', width: 90, render: (_, r) => <CellInput value={r.input?.converted_qty} onSave={v => saveInput(r.input, 'converted_qty', v, r.batch_no)} /> },
    { title: '折纯\n总量', dataIndex: 'total_converted_qty', width: 65, render: (_, r) => M(<CellInput value={r.total_converted_qty} onSave={v => saveRecord(r.id, 'total_converted_qty', v, r)} />, r), onCell },
    { title: <>滤液<br />效价(mg/L)</>, dataIndex: 'filter_potency', width: 90, render: (_, r) => M(<CellInput value={r.filter_potency} onSave={v => saveRecord(r.id, 'filter_potency', v, r)} />, r), onCell },
    { title: <>滤液<br />体积(m³)</>, dataIndex: 'filter_volume', width: 68, render: (_, r) => M(<CellInput value={r.filter_volume} onSave={v => saveRecord(r.id, 'filter_volume', v, r)} />, r), onCell },
    { title: <>滤液<br />产品量(kg)</>, dataIndex: 'filter_product_qty', width: 90, render: (_, r) => M(<CellInput value={r.filter_product_qty} color="#1677ff" onSave={v => saveRecord(r.id, 'filter_product_qty', v, r)} />, r), onCell },
    { title: <>用碳量<br />(kg)</>, dataIndex: 'carbon_usage', width: 68, render: (_, r) => M(<CellInput value={r.carbon_usage} onSave={v => saveRecord(r.id, 'carbon_usage', v, r)} />, r), onCell },
    { title: <>湿粉<br />毛重(kg)</>, dataIndex: 'wet_weight', width: 75, render: (_, r) => M(<CellInput value={r.wet_weight} onSave={v => saveRecord(r.id, 'wet_weight', v, r)} />, r), onCell },
    { title: '湿粉\n含量', dataIndex: 'wet_content', width: 55, render: (_, r) => M(<CellInput value={r.wet_content} onSave={v => saveRecord(r.id, 'wet_content', v, r)} />, r), onCell },
    { title: '干燥\n失重', dataIndex: 'dry_loss', width: 55, render: (_, r) => M(<CellInput value={r.dry_loss} onSave={v => saveRecord(r.id, 'dry_loss', v, r)} />, r), onCell },
    { title: '折干\n产量(kg)', dataIndex: 'dry_weight', width: 75, render: (_, r) => M(<CellInput value={r.dry_weight} color="#1677ff" onSave={v => saveRecord(r.id, 'dry_weight', v, r)} />, r), onCell },
    { title: '单步\n收率', dataIndex: 'yield_rate', width: 60, render: (_, r) => M(<CellInput value={r.yield_rate} color={r.yield_rate != null ? (r.yield_rate >= 85 ? '#52c41a' : '#f5222d') : undefined} onSave={v => saveRecord(r.id, 'yield_rate', v, r)} />, r), onCell },
    { title: '操作', key: 'act', width: 50, fixed: 'right', render: (_, r) => M(<Button type="link" size="small" danger onClick={() => modal.confirm({ title: `删除 ${r.batch_no}?`, onOk: async () => { await api(`/extraction-records/${r.id}`, { method: 'DELETE' }); load() } })} style={{ fontSize: 10 }}>删除</Button>, r), onCell },
  ]

  const batchInputCounts = []
  for (const rec of records) batchInputCounts.push({ batchNo: rec.batch_no, recordId: rec.id, count: (rec.inputs || []).length })

  return (
    <div className="p-6">
      <style>{`
        .extraction-ledger-table .ant-table-thead > tr > th { white-space: normal !important; word-break: break-all; line-height: 1.15; padding: 2px 1px !important; font-size: 10px; text-align: center !important; vertical-align: middle !important; background: #fafafa; }
        .extraction-ledger-table .ant-table-tbody > tr > td { white-space: normal !important; word-break: break-all; padding: 1px 2px !important; font-size: 10px; text-align: center !important; line-height: 1.2; }
        .extraction-ledger-table .ant-input-number { font-size: 10px; width: 100%; } .extraction-ledger-table .ant-input-number input { font-size: 10px; padding: 0 2px; text-align: center; height: 20px; }
        .extraction-ledger-table .ant-input-number .ant-input-number-handler-wrap { display: none; } .extraction-ledger-table .ant-picker { width: 100%; } .extraction-ledger-table .ant-picker input { font-size: 10px; padding: 0 2px; text-align: center; height: 20px; }
      `}</style>

      <Card size="small" className="mb-4">
        <Space wrap>{STAGES.map(s => <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>{s.label}</Button>)}</Space>
      </Card>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <Title level={4} style={{ margin: 0 }}><Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/201-2')}>返回车间</Button>提取工段 — 粗品 → 湿粉（失焦自动保存）</Title>
        <Space size={8}>
          <Select size="small" style={{ width: 80 }} value={month} onChange={v => setMonth(v)}
            options={[{ value: 0, label: '全部' }, ...[1,2,3,4,5,6,7,8,9,10,11,12].map(m => ({ value: m, label: `${m}月` }))]} />
          <MCSheetsSyncButton />
          <MCTraceButton initialModule="extraction" />
        </Space>
      </div>

      <Dashboard title="提取工段仪表盘" data={records} dateField="extract_date" month={month}
        cards={[
          { title: '总粗品投入量', value: (_, f) => f.reduce((a, b) => a + (b.total_crude_weight || 0), 0), suffix: 'kg', precision: 0 },
          { title: '总折干产量', value: (_, f) => f.reduce((a, b) => a + (b.dry_weight || 0), 0), suffix: 'kg', precision: 0 },
          { title: '总滤液产品量', value: (_, f) => f.reduce((a, b) => a + (b.filter_product_qty || 0), 0), suffix: 'kg', precision: 0 },
          { title: '批数', value: (_, f) => f.length, suffix: '批', precision: 0 },
          { title: '平均收率', value: (_, f) => { let s = 0, n = 0; f.forEach(d => { if (d.yield_rate != null) { s += d.yield_rate; n++ } }); return n > 0 ? Math.round(s / n * 100) / 100 : null }, suffix: '%', precision: 1, color: (v) => v >= 85 ? '#52c41a' : '#f5222d' },
        ]}
        charts={[
          { key: 'yield', title: '收率趋势', unit: '%', color: '#1890ff', markLine: 85, label: '收率趋势', field: 'yield_rate' },
          { key: 'dryWeight', title: '折干产量趋势(kg)', unit: 'kg', color: '#52c41a', label: '折干产量趋势', field: 'dry_weight' },
          { key: 'filterPotency', title: '滤液效价趋势(mg/L)', unit: 'mg/L', color: '#fa8c16', label: '滤液效价趋势', field: 'filter_potency' },
          { key: 'wetContent', title: '湿粉含量趋势(%)', unit: '%', color: '#13c2c2', label: '湿粉含量趋势', field: 'wet_content' },
          { key: 'convertedQty', title: '折纯总量趋势(kg)', unit: 'kg', color: '#722ed1', label: '折纯总量趋势', field: 'total_converted_qty' },
        ]}
      />

      <Card extra={<Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateVisible(true) }}>新建提取记录</Button>}>
        <Table size="small" rowKey="_key" loading={loading} className="extraction-ledger-table" dataSource={flattenData()} scroll={{ x: 1800 }} columns={columns} pagination={false} />
        <div style={{ padding: '8px 0', display: 'flex', flexWrap: 'wrap', gap: 8, borderTop: '1px solid #f0f0f0', marginTop: 8 }}>
          {batchInputCounts.map(bic => <Button key={bic.recordId} size="small" type="dashed" loading={saving} onClick={() => addInputRow(bic.batchNo, bic.count)}>+ 粗品投入 ({bic.batchNo})</Button>)}
          {batchInputCounts.length === 0 && <Text type="secondary">暂无提取记录</Text>}
        </div>
      </Card>

      <Modal title="新建提取记录" open={createVisible} onOk={handleCreate} onCancel={() => setCreateVisible(false)} width={800} okText="确认" cancelText="取消" destroyOnHidden>
        <Form form={form} layout="vertical" style={{ maxHeight: '70vh', overflow: 'auto' }}>
          <Row gutter={16}><Col span={8}><Form.Item name="batch_no" label="提取批号" rules={[{ required: true }]}><Input placeholder="MC-260129" /></Form.Item></Col>
            <Col span={8}><Form.Item name="extract_date" label="生产日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col></Row>
          <Text strong>萃取滤液</Text>
          <Row gutter={16}><Col span={8}><Form.Item name="filter_potency" label="滤液效价(mg/L)"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="filter_volume" label="滤液体积(m³)"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="carbon_usage" label="用碳量(kg)"><InputNumber style={{ width: '100%' }} /></Form.Item></Col></Row>
          <Text strong>湿粉产出</Text>
          <Row gutter={16}><Col span={6}><Form.Item name="wet_weight" label="湿粉毛重(kg)"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={6}><Form.Item name="wet_content" label="含量(%)"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={6}><Form.Item name="dry_loss" label="干燥失重(%)"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={6}><Form.Item name="dry_weight" label="折干产量(kg)"><InputNumber style={{ width: '100%' }} /></Form.Item></Col></Row>
          <Form.Item name="remarks" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
