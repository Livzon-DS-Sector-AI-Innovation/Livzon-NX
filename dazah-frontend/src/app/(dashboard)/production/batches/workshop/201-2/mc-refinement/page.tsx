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
  { key: 'refinement', label: 'MC二次精制', path: '/production/batches/workshop/201-2/mc-refinement', active: true },
  { key: 'blending', label: '混粉杂质计算', path: '/production/batches/workshop/201-2/blending' },
  { key: 'qc', label: '混粉入库', path: '/production/batches/workshop/201-2/qc-inspection' },
  { key: 'ba', label: '丁酯盘点', path: '/production/batches/workshop/201-2/butyl-acetate' },
  { key: 'traceability', label: '全链路追溯', path: '/production/batches/workshop/201-2/traceability' },
]

async function api(path: string, opts?: RequestInit) {
  const r = await fetch(`${API}${BASE}${path}`, { headers: { 'Content-Type': 'application/json' }, ...opts })
  return r.json()
}

function CellInput({ value, onSave, color }: { value: number | null | undefined; onSave: (v: number | null) => void; color?: string }) {
  const [editing, setEditing] = useState(false)
  if (!editing) return <div style={{ width: '100%', height: 20, cursor: 'text', color: color || undefined, fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setEditing(true)}>{value != null ? value : ''}</div>
  return <InputNumber size="small" autoFocus style={{ width: '100%', color: color || undefined }} defaultValue={value ?? undefined}
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

export default function McRefinementPage() {
  const router = useRouter(); const { message, modal } = App.useApp()
  const [form] = Form.useForm()
  const [records, setRecords] = useState<any[]>([]); const [loading, setLoading] = useState(false); const [saving, setSaving] = useState(false)
  const [month, setMonth] = useState<number>(dayjs().month() + 1)
  const [createVisible, setCreateVisible] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    const params = 'workshop=201-2' + (month > 0 ? `&month=${month}` : '')
    try { const r = await api(`/refinement-records/full-list?${params}`); if (r.code === 200) setRecords(r.data) } catch { message.error('加载失败') } finally { setLoading(false) }
  }, [message, month])
  useEffect(() => { load() }, [load]) // eslint-disable-line react-hooks/set-state-in-effect

  const saveRecord = async (id: string, field: string, value: any, record: any) => {
    setSaving(true); const d: any = { [field]: value }
    if (field === 'dry_weight') d.single_step_yield = value != null && record.total_pure_qty != null && record.total_pure_qty > 0 ? Math.round(value / record.total_pure_qty * 10000) / 100 : null
    await api(`/refinement-records/${id}`, { method: 'PUT', body: JSON.stringify(d) }); setSaving(false); load()
  }

  const saveInput = async (input: any, field: string, value: any, refinementBatch: string) => {
    setSaving(true); const d: any = { [field]: value }
    if (field === 'input_weight' || field === 'moisture' || field === 'content') {
      const w = (field === 'input_weight' ? value : input.input_weight) || 0; const m = (field === 'moisture' ? value : input.moisture) || 0; const c = (field === 'content' ? value : input.content) || 0
      d.pure_qty = Math.round(w * (1 - m / 100) * c) / 100
    }
    if (input.id) await api(`/refinement-inputs/${input.id}`, { method: 'PUT', body: JSON.stringify(d) }); setSaving(false); load()
  }

  const addInputRow = async (refinementBatch: string) => {
    setSaving(true); await api('/refinement-inputs', { method: 'POST', body: JSON.stringify({ refinement_batch: refinementBatch, wet_batch_no: '', input_weight: 0, moisture: 0, content: 0 }) })
    setSaving(false); load()
  }

  const handleCreate = async () => {
    try {
      const vals = await form.validateFields(); vals.workshop = '201-2'
      if (vals.input_date) vals.input_date = dayjs(vals.input_date).format('YYYY-MM-DD')
      const r = await api('/refinement-records', { method: 'POST', body: JSON.stringify(vals) })
      if (r.code === 200) { message.success('创建成功'); setCreateVisible(false); form.resetFields(); load() }
      else message.error(r.message || '创建失败')
    } catch { message.error('请检查表单') }
  }

  const flattenData = () => {
    const rows: any[] = []
    for (const rec of records) { const inputs = rec.inputs || []; const c = Math.max(inputs.length, 1); for (let i = 0; i < c; i++) rows.push({ ...rec, input: inputs[i] || {}, _key: `${rec.id}-${i}`, _rowCount: c, _isFirst: i === 0 }) }
    return rows
  }

  const M = (content: any, r: any) => (r._isFirst ? content : null)
  const onCell = (r: any) => { const rowSpan = r._isFirst ? r._rowCount : 0; return { rowSpan, style: rowSpan > 1 ? { verticalAlign: 'middle' } : undefined } as any }

  const columns: any[] = [
    { title: '投料\n日期', dataIndex: 'input_date', width: 72, fixed: 'left', render: (_: any, r: any) => M(<DateCellInput value={r.input_date} onSave={v => saveRecord(r.id, 'input_date', v, r)} />, r), onCell },
    { title: '二次结晶\n批号', dataIndex: 'batch_no', width: 105, fixed: 'left', render: (_: any, r: any) => M(<Text strong style={{ fontSize: 10 }}>{r.batch_no}</Text>, r), onCell },
    { title: '一次精品\n批号', key: 'wet_batch', width: 80, render: (_: any, r: any) => <TextCellInput value={r.input?.wet_batch_no} onSave={v => saveInput(r.input, 'wet_batch_no', v, r.batch_no)} /> },
    { title: '重量\n(kg)', key: 'inp_w', width: 58, render: (_: any, r: any) => <CellInput value={r.input?.input_weight} onSave={v => saveInput(r.input, 'input_weight', v, r.batch_no)} /> },
    { title: '总重\n(kg)', dataIndex: 'total_input_weight', width: 58, render: (_: any, r: any) => M(<CellInput value={r.total_input_weight} onSave={v => saveRecord(r.id, 'total_input_weight', v, r)} />, r), onCell },
    { title: '一次\n湿粉水分', key: 'inp_m', width: 55, render: (_: any, r: any) => <CellInput value={r.input?.moisture} onSave={v => saveInput(r.input, 'moisture', v, r.batch_no)} /> },
    { title: '一次\n湿粉含量', key: 'inp_c', width: 55, render: (_: any, r: any) => <CellInput value={r.input?.content} onSave={v => saveInput(r.input, 'content', v, r.batch_no)} /> },
    { title: '折纯量', key: 'inp_pure', width: 58, render: (_: any, r: any) => <CellInput value={r.input?.pure_qty} color="#1677ff" onSave={v => saveInput(r.input, 'pure_qty', v, r.batch_no)} /> },
    { title: '折干产品\n总量(kg)', dataIndex: 'dry_product_total', width: 80, render: (_: any, r: any) => M(<CellInput value={r.dry_product_total} color="#1677ff" onSave={v => saveRecord(r.id, 'dry_product_total', v, r)} />, r), onCell },
    { title: '累计折\n干产品量', dataIndex: 'cumulative_dry_product', width: 70, render: (_: any, r: any) => M(<CellInput value={r.cumulative_dry_product} onSave={v => saveRecord(r.id, 'cumulative_dry_product', v, r)} />, r), onCell },
    { title: '溶解\n用罐', dataIndex: 'dissolution_tank', width: 68, render: (_: any, r: any) => M(<TextCellInput value={r.dissolution_tank} onSave={v => saveRecord(r.id, 'dissolution_tank', v, r)} />, r), onCell },
    { title: '丁酯量\n(m³)', dataIndex: 'butyl_acetate_volume', width: 58, render: (_: any, r: any) => M(<CellInput value={r.butyl_acetate_volume} onSave={v => saveRecord(r.id, 'butyl_acetate_volume', v, r)} />, r), onCell },
    { title: '结晶\n用罐', dataIndex: 'crystallization_tank', width: 68, render: (_: any, r: any) => M(<TextCellInput value={r.crystallization_tank} onSave={v => saveRecord(r.id, 'crystallization_tank', v, r)} />, r), onCell },
    { title: '湿粉重\n量(kg)', dataIndex: 'wet_weight', width: 65, render: (_: any, r: any) => M(<CellInput value={r.wet_weight} onSave={v => saveRecord(r.id, 'wet_weight', v, r)} />, r), onCell },
    { title: '干粉重\n量(kg)', dataIndex: 'dry_weight', width: 65, render: (_: any, r: any) => M(<CellInput value={r.dry_weight} onSave={v => saveRecord(r.id, 'dry_weight', v, r)} />, r), onCell },
    { title: '累计干\n粉重量', dataIndex: 'cumulative_dry_weight', width: 65, render: (_: any, r: any) => M(<CellInput value={r.cumulative_dry_weight} onSave={v => saveRecord(r.id, 'cumulative_dry_weight', v, r)} />, r), onCell },
    { title: '单步\n收率', dataIndex: 'single_step_yield', width: 52, render: (_: any, r: any) => M(<CellInput value={r.single_step_yield} color={r.single_step_yield != null ? (r.single_step_yield >= 85 ? '#52c41a' : '#f5222d') : undefined} onSave={v => saveRecord(r.id, 'single_step_yield', v, r)} />, r), onCell },
    { title: '二次结晶\n累计收率', dataIndex: 'cumulative_yield', width: 68, render: (_: any, r: any) => M(<CellInput value={r.cumulative_yield} onSave={v => saveRecord(r.id, 'cumulative_yield', v, r)} />, r), onCell },
    { title: '操作', key: 'act', width: 50, fixed: 'right', render: (_: any, r: any) => M(<Button type="link" size="small" danger onClick={() => modal.confirm({ title: `删除 ${r.batch_no}?`, onOk: async () => { await api(`/refinement-records/${r.id}`, { method: 'DELETE' }); load() } })} style={{ fontSize: 10 }}>删除</Button>, r), onCell },
  ]

  const batchInputCounts = []
  for (const rec of records) batchInputCounts.push({ batchNo: rec.batch_no, recordId: rec.id, count: (rec.inputs || []).length })

  return (
    <div className="p-6">
      <style>{`
        .refine-ledger-table .ant-table-thead > tr > th { white-space: normal !important; word-break: break-all; line-height: 1.15; padding: 2px 1px !important; font-size: 9px; text-align: center !important; vertical-align: middle !important; background: #fafafa; }
        .refine-ledger-table .ant-table-tbody > tr > td { white-space: normal !important; word-break: break-all; padding: 1px 2px !important; font-size: 10px; text-align: center !important; line-height: 1.2; }
        .refine-ledger-table .ant-input-number { font-size: 10px; width: 100%; } .refine-ledger-table .ant-input-number input { font-size: 10px; padding: 0 2px; text-align: center; height: 20px; }
        .refine-ledger-table .ant-input-number .ant-input-number-handler-wrap { display: none; } .refine-ledger-table .ant-picker { width: 100%; } .refine-ledger-table .ant-picker input { font-size: 10px; padding: 0 2px; text-align: center; height: 20px; }
      `}</style>

      <Card size="small" className="mb-4">
        <Space wrap>{STAGES.map(s => <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>{s.label}</Button>)}</Space>
      </Card>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <Title level={4} style={{ margin: 0 }}><Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/201-2')}>返回车间</Button>MC二次精制 — 湿粉→干粉 MC-F2（失焦自动保存）</Title>
        <Space size={8}>
          <Select size="small" style={{ width: 80 }} value={month} onChange={v => setMonth(v)}
            options={[{ value: 0, label: '全部' }, ...[1,2,3,4,5,6,7,8,9,10,11,12].map(m => ({ value: m, label: `${m}月` }))]} />
          <MCSheetsSyncButton />
          <MCTraceButton initialModule="refinement" />
        </Space>
      </div>

      <Dashboard title="MC二次精制仪表盘" data={records} dateField="created_at" month={month}
        cards={[
          { title: '累计折干产品量', value: (all) => { let v = null; for (const d of all) if (d.cumulative_dry_product != null) v = d.cumulative_dry_product; return v }, suffix: 'kg', precision: 0 },
          { title: '累计干粉重量', value: (all) => { let v = null; for (const d of all) if (d.cumulative_dry_weight != null) v = d.cumulative_dry_weight; return v }, suffix: 'kg', precision: 0 },
          { title: '批数', value: (_, f) => f.length, suffix: '批', precision: 0 },
          { title: '总干粉产量', value: (_, f) => f.reduce((a, b) => a + (b.dry_weight || 0), 0), suffix: 'kg', precision: 0 },
          { title: '平均收率', value: (_, f) => { let s = 0, n = 0; f.forEach(d => { if (d.single_step_yield != null) { s += d.single_step_yield; n++ } }); return n > 0 ? Math.round(s / n * 100) / 100 : null }, suffix: '%', precision: 1, color: (v: any) => v >= 85 ? '#52c41a' : '#f5222d' },
        ]}
        charts={[
          { key: 'yield', title: '单步收率趋势', unit: '%', color: '#1890ff', markLine: 85, label: '收率趋势', field: 'single_step_yield' },
          { key: 'dryWeight', title: '干粉产量趋势(kg)', unit: 'kg', color: '#52c41a', label: '干粉产量趋势', field: 'dry_weight' },
          { key: 'dryProduct', title: '折干产品总量趋势(kg)', unit: 'kg', color: '#722ed1', label: '折干产品总量趋势', field: 'dry_product_total' },
        ]}
      />

      <Card extra={<Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateVisible(true) }}>新建精制记录</Button>}>
        <Table size="small" rowKey="_key" loading={loading} className="refine-ledger-table" dataSource={flattenData()} scroll={{ x: 1900 }} columns={columns} pagination={false} />
        <div style={{ padding: '8px 0', display: 'flex', flexWrap: 'wrap', gap: 8, borderTop: '1px solid #f0f0f0', marginTop: 8 }}>
          {batchInputCounts.map(bic => <Button key={bic.recordId} size="small" type="dashed" loading={saving} onClick={() => addInputRow(bic.batchNo)}>+ 投入 ({bic.batchNo})</Button>)}
          {batchInputCounts.length === 0 && <Text type="secondary">暂无精制记录</Text>}
        </div>
      </Card>

      <Modal title="新建MC精制记录" open={createVisible} onOk={handleCreate} onCancel={() => setCreateVisible(false)} width={800} okText="确认" cancelText="取消" destroyOnHidden>
        <Form form={form} layout="vertical" style={{ maxHeight: '70vh', overflow: 'auto' }}>
          <Row gutter={16}><Col span={8}><Form.Item name="batch_no" label="批号（MC-F2-XXXXXX）" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="input_date" label="投料日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col></Row>
          <Row gutter={16}><Col span={8}><Form.Item name="dissolution_tank" label="溶解用罐"><Input placeholder="1#结晶罐 / 8#浓缩罐" /></Form.Item></Col>
            <Col span={8}><Form.Item name="butyl_acetate_volume" label="丁酯量(m³)"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="crystallization_tank" label="结晶用罐"><Input placeholder="3#结晶罐 / 1#溶解罐" /></Form.Item></Col></Row>
          <Row gutter={16}><Col span={8}><Form.Item name="wet_weight" label="湿粉重量(kg)"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="dry_weight" label="干粉重量(kg)"><InputNumber style={{ width: '100%' }} /></Form.Item></Col></Row>
        </Form>
      </Modal>
    </div>
  )
}
