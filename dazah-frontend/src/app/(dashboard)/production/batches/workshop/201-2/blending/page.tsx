'use client'
import {useEffect, useState, useCallback,} from 'react'
import { Table, Button, Space, Modal, Form, Input, InputNumber, Card, Typography, App, Row, Col, Tag, Select } from 'antd'
import { PlusOutlined, CalculatorOutlined, ArrowLeftOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import dayjs from 'dayjs'
import { calculateBlendImpurities, deleteBlendingRecord } from '@/actions/mc/stages'
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
  { key: 'blending', label: '混粉杂质计算', path: '/production/batches/workshop/201-2/blending', active: true },
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

function TextCellInput({ value, onSave }: { value: string | null | undefined; onSave: (v: string | null) => void }) {
  const [editing, setEditing] = useState(false)
  if (!editing) return <div style={{ width: '100%', height: 20, cursor: 'text', fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setEditing(true)}>{value ?? ''}</div>
  return <Input size="small" autoFocus style={{ width: '100%', fontSize: 10, height: 20, padding: '0 2px' }} defaultValue={value ?? ''} onBlur={e => { setEditing(false); onSave(e.target.value || null) }} />
}

const IMPURITY_FIELDS = [
  { key: 'rrt_053', title: 'RRT=0.53', limit: 0.05, limitText: '<0.05' },
  { key: 'rrt_0755', title: 'RRT=0.755', limit: 0.07, limitText: '<0.07' },
  { key: 'rrt_094_096', title: 'RRT=0.94-0.96', limit: 0.14, limitText: '<0.14' },
  { key: 'rrt_103_106', title: 'RRT=1.03-1.06', limit: 0.075, limitText: '<0.075' },
  { key: 'rrt_201', title: 'RRT=2.01', limit: 0.08, limitText: '<0.08' },
  { key: 'total_impurity', title: '总杂', limit: 0.6, limitText: '<0.6' },
  { key: 'content', title: '含量', limit: 99, limitText: '>99' },
]

export default function BlendingPage() {
  const router = useRouter(); const { message, modal } = App.useApp()
  const [form] = Form.useForm()
  const [records, setRecords] = useState<any[]>([]); const [loading, setLoading] = useState(false); const [, setSaving] = useState(false)
  const [month, setMonth] = useState<number>(dayjs().month() + 1)
  const [createVisible, setCreateVisible] = useState(false)
  const [calculating, setCalculating] = useState<Record<string, boolean>>({})

  const load = useCallback(async () => {
    setLoading(true)
    const params = 'workshop=201-2' + (month > 0 ? `&month=${month}` : '')
    try { const r = await api(`/blending-records/full-list?${params}`); if (r.code === 200) setRecords(r.data) } catch { message.error('加载失败') } finally { setLoading(false) }
  }, [message, month])
  useEffect(() => { load() }, [load]) // eslint-disable-line react-hooks/set-state-in-effect

  const saveRecord = async (id: string, field: string, value: any) => {
    setSaving(true); await api(`/blending-records/${id}`, { method: 'PUT', body: JSON.stringify({ [field]: value }) }); setSaving(false); load()
  }

  const saveInput = async (input: any, field: string, value: any) => {
    setSaving(true); await api(`/blending-inputs/${input.id}`, { method: 'PUT', body: JSON.stringify({ [field]: value }) }); setSaving(false); load()
  }

  const handleCalculate = async (batchNo: string) => {
    setCalculating(p => ({ ...p, [batchNo]: true }))
    const res = await calculateBlendImpurities(batchNo)
    if (res.code === 200) {
      const w = res.data.warnings
      if (w && Object.keys(w).length > 0) message.warning(`杂质预警: ${Object.entries(w).map(([k, v]) => `${k}: ${v}`).join(', ')}`)
      else message.success('计算完成')
      load()
    } else message.error(res.message || '计算失败')
    setCalculating(p => ({ ...p, [batchNo]: false }))
  }

  const handleCreate = async () => {
    try { const vals = await form.validateFields(); vals.workshop = '201-2'; await api('/blending-records', { method: 'POST', body: JSON.stringify(vals) }); message.success('创建成功'); setCreateVisible(false); form.resetFields(); load() }
    catch { message.error('请检查表单') }
  }

  const flattenData = () => {
    const rows: any[] = []
    for (const rec of records) { const inputs = rec.inputs || []; const c = Math.max(inputs.length, 1); for (let i = 0; i < c; i++) rows.push({ ...rec, input: inputs[i] || {}, _key: `${rec.id}-${i}`, _rowCount: c, _isFirst: i === 0 }) }
    return rows
  }

  const M = (content: any, r: any) => (r._isFirst ? content : null)
  const onCell = (r: any) => { const rowSpan = r._isFirst ? r._rowCount : 0; return { rowSpan, style: rowSpan > 1 ? { verticalAlign: 'middle' } : undefined } as any }

  const impurityColor = (key: string, val: number | null | undefined) => {
    if (val == null) return undefined; const f = IMPURITY_FIELDS.find(x => x.key === key); if (!f) return undefined
    if (key === 'content') return val >= f.limit ? '#52c41a' : '#f5222d'
    return val <= f.limit ? '#52c41a' : '#f5222d'
  }

  const columns: any[] = [
    { title: '混合\n批号', dataIndex: 'batch_no', width: 100, fixed: 'left', render: (_: any, r: any) => M(<Text strong style={{ fontSize: 11 }}>{r.batch_no}</Text>, r), onCell },
    { title: '单批\n批号', key: 'inp_batch', width: 110, render: (_: any, r: any) => <TextCellInput value={r.input?.input_batch_no} onSave={v => saveInput(r.input, 'input_batch_no', v)} /> },
    { title: '单批\n数量(kg)', key: 'inp_w', width: 68, render: (_: any, r: any) => <CellInput value={r.input?.input_weight} onSave={v => saveInput(r.input, 'input_weight', v)} /> },
    { title: '包装\n重量(kg)', dataIndex: 'total_weight', width: 68, render: (_: any, r: any) => M(<CellInput value={r.total_weight} onSave={v => saveRecord(r.id, 'total_weight', v)} />, r), onCell },
    { title: '规格', dataIndex: 'pack_spec', width: 80, render: (_: any, r: any) => M(<TextCellInput value={r.pack_spec} onSave={v => saveRecord(r.id, 'pack_spec', v)} />, r), onCell },
    ...IMPURITY_FIELDS.map(({ key, title, limit }) => ({
      title: <><Text style={{ fontSize: 9 }}>{title}</Text><br /><Text style={{ fontSize: 8, color: '#999' }}>{key === 'content' ? `>${limit}` : `<${limit}`}</Text></>,
      key: `inp_${key}`, width: 60,
      render: (_: any, r: any) => <CellInput value={r.input?.[key]} color={impurityColor(key, r.input?.[key])} onSave={v => saveInput(r.input, key, v)} />,
    })),
    ...IMPURITY_FIELDS.map(({ key, title, limit }) => ({
      title: <><Text strong style={{ fontSize: 9, color: '#1677ff' }}>{title}</Text><br /><Text style={{ fontSize: 8, color: '#1677ff' }}>{key === 'content' ? `>${limit}` : `<${limit}`}</Text></>,
      key: `calc_${key}`, width: 62,
      render: (_: any, r: any) => M(<Text style={{ fontSize: 11, fontWeight: 'bold', color: r[key] != null ? impurityColor(key, r[key]) : '#ccc' }}>{r[key] != null ? (typeof r[key] === 'number' ? r[key].toFixed(key === 'content' ? 1 : 3) : r[key]) : '-'}</Text>, r),
      onCell,
    })),
    { title: <Text strong style={{ fontSize: 10, color: '#1677ff' }}>操作</Text>, key: 'calc', width: 68, fixed: 'right',
      render: (_: any, r: any) => M(<Space orientation="vertical" size={0}><Button type="primary" size="small" icon={<CalculatorOutlined />} loading={calculating[r.batch_no]} onClick={() => handleCalculate(r.batch_no)} style={{ fontSize: 10 }}>计算</Button>
        <Button type="link" size="small" danger onClick={() => modal.confirm({ title: `删除 ${r.batch_no}?`, onOk: async () => { await deleteBlendingRecord(r.id); load() } })} style={{ fontSize: 10 }}>删除</Button></Space>, r), onCell },
  ]

  return (
    <div className="p-6">
      <style>{`
        .blend-ledger-table .ant-table-thead > tr > th { white-space: normal !important; word-break: break-all; line-height: 1.1; padding: 2px 1px !important; font-size: 9px; text-align: center !important; vertical-align: middle !important; background: #fafafa; }
        .blend-ledger-table .ant-table-tbody > tr > td { white-space: normal !important; word-break: break-all; padding: 1px 2px !important; font-size: 10px; text-align: center !important; line-height: 1.2; }
        .blend-ledger-table .ant-input-number { font-size: 10px; width: 100%; } .blend-ledger-table .ant-input-number input { font-size: 10px; padding: 0 2px; text-align: center; height: 20px; }
        .blend-ledger-table .ant-input-number .ant-input-number-handler-wrap { display: none; }
      `}</style>

      <Card size="small" className="mb-4">
        <Space wrap>{STAGES.map(s => <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>{s.label}</Button>)}</Space>
      </Card>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <Title level={4} style={{ margin: 0 }}><Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/201-2')}>返回车间</Button><CalculatorOutlined className="ml-2 mr-2" />混粉杂质计算 — 加权平均</Title>
        <Space size={8}>
          <Select size="small" style={{ width: 80 }} value={month} onChange={v => setMonth(v)}
            options={[{ value: 0, label: '全部' }, ...[1,2,3,4,5,6,7,8,9,10,11,12].map(m => ({ value: m, label: `${m}月` }))]} />
          <MCSheetsSyncButton />
          <MCTraceButton initialModule="blending" />
        </Space>
      </div>

      <Dashboard title="混粉杂质计算仪表盘" data={records} dateField="created_at" month={month}
        cards={[
          { title: '总批数', value: (_, f) => f.length, suffix: '批', precision: 0 },
          { title: '已计算', value: (_, f) => f.filter(d => d.total_impurity != null).length, suffix: '批', precision: 0 },
          { title: '含量均值', value: (_, f) => { let s = 0, n = 0; f.forEach(d => { if (d.content != null) { s += d.content; n++ } }); return n > 0 ? Math.round(s / n * 100) / 100 : null }, suffix: '%', precision: 1, color: (v: any) => v >= 99 ? '#52c41a' : '#f5222d' },
          { title: '总杂均值', value: (_, f) => { let s = 0, n = 0; f.forEach(d => { if (d.total_impurity != null) { s += d.total_impurity; n++ } }); return n > 0 ? Math.round(s / n * 10000) / 10000 : null }, suffix: '', precision: 3, color: (v: any) => v <= 0.6 ? '#52c41a' : '#f5222d' },
        ]}
        charts={[
          { key: 'total_impurity', title: '总杂趋势', unit: '%', color: '#f5222d', markLine: 0.6, label: '总杂趋势', field: 'total_impurity' },
          { key: 'content', title: '含量趋势', unit: '%', color: '#52c41a', markLine: 99, markLineAbove: true, label: '含量趋势', field: 'content' },
          { key: 'rrt_053', title: 'RRT=0.53趋势', unit: '', color: '#1890ff', markLine: 0.05, label: 'RRT=0.53', field: 'rrt_053' },
          { key: 'rrt_201', title: 'RRT=2.01趋势', unit: '', color: '#fa8c16', markLine: 0.08, label: 'RRT=2.01', field: 'rrt_201' },
        ]}
      />

      <Card extra={<Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateVisible(true) }}>新建混粉批次</Button>}>
        <Table size="small" rowKey="_key" loading={loading} className="blend-ledger-table" dataSource={flattenData()} scroll={{ x: 2200 }} columns={columns} pagination={false} />
      </Card>

      <Card size="small" className="mt-4">
        <Space wrap>
          <Text type="secondary" style={{ fontSize: 11 }}>杂质标准：</Text>
          {IMPURITY_FIELDS.map(f => <Tag key={f.key} color={f.key === 'content' ? 'green' : 'blue'} style={{ fontSize: 10 }}>{f.title}: {f.limitText}</Tag>)}
          <Text type="secondary" style={{ fontSize: 11 }}>🟢 合规 🔴 超限</Text>
        </Space>
      </Card>

      <Modal title="新建混粉批次" open={createVisible} onOk={handleCreate} onCancel={() => setCreateVisible(false)} width={500} okText="确认" cancelText="取消" destroyOnHidden>
        <Form form={form} layout="vertical">
          <Row gutter={16}><Col span={12}><Form.Item name="batch_no" label="混合批号" rules={[{ required: true }]}><Input placeholder="MC-260101" /></Form.Item></Col>
            <Col span={12}><Form.Item name="pack_spec" label="包装规格"><Input placeholder="20kg/桶" /></Form.Item></Col></Row>
        </Form>
      </Modal>
    </div>
  )
}
