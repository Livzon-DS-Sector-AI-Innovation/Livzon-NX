'use client'
// 粗提工段 — 台账 + 仪表盘（4层嵌套扁平化 + 合并单元格 + 失焦保存 + 自动计算）

import { useEffect, useState, useCallback, useMemo } from 'react'
import type { ReactNode } from 'react'
import { Table, Button, Space, Modal, Form, Input, InputNumber, DatePicker, Card, Typography, App, Row, Col, Select } from 'antd'
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
  { key: 'crude', label: '粗提', path: '/production/batches/workshop/201-2/crude-extraction', active: true },
  { key: 'extraction', label: '提取', path: '/production/batches/workshop/201-2/extraction' },
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

interface SubTank {
  id?: string
  batch_no?: string
  fl_volume?: number | null
  fl_potency?: number | null
  fl_product_qty?: number | null
  total_input?: number | null
  cumulative_qty?: number | null
  crude_weight?: number | null
  bag_weight?: number | null
  crude_content?: number | null
  crude_moisture?: number | null
  crude_product_qty?: number | null
  yield_rate?: number | null
  cumulative_crude_qty?: number | null
  cumulative_crude_yield?: number | null
  remarks?: string | null
}

interface SodiumStep {
  id?: string
  na_before_volume?: number | null
  na_after_volume?: number | null
  na_potency?: number | null
  na_product_qty?: number | null
  sodium_total?: number | null
  ph_value?: number | null
  alkali_usage?: number | null
}

interface AcidStep {
  id?: string
  acid_filter_volume?: number | null
  acid_potency?: number | null
  acid_product_qty?: number | null
  filter_subtotal?: number | null
  ph_value?: number | null
  acid_usage?: number | null
  acid_filter_content?: number | null
  filter_total?: number | null
  na_to_fermentation_yield?: number | null
  monthly_cumulative_yield?: number | null
}

interface CrudeSubTankWrap {
  sub_tank?: SubTank
  sodium_steps?: SodiumStep[]
  acid_steps?: AcidStep[]
}

interface CrudeItem {
  refining?: { id?: string; batch_no?: string; produce_date?: string | null }
  fermentation?: { batch_no?: string }
  sub_tanks?: CrudeSubTankWrap[]
}

interface CrudeRow {
  _key: string
  fl?: { batch_no?: string }
  rb?: { id?: string; batch_no?: string; produce_date?: string | null }
  st?: SubTank
  sodium: SodiumStep
  acid: AcidStep
  _seqNo: number
  _isBatchFirst?: boolean
  _batchRowCount?: number
  _isStFirst?: boolean
  _stRowCount?: number
}

function CellInput({ value, onSave, color }: { value: number | null | undefined; onSave: (v: number | null) => void; color?: string }) {
  const [editing, setEditing] = useState(false)
  if (!editing) return <div style={{ width: '100%', height: 20, cursor: 'text', color: color || undefined, fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setEditing(true)}>{value != null ? value : ''}</div>
  return <InputNumber size="small" autoFocus style={{ width: '100%', color: color || undefined }} defaultValue={value ?? undefined}
    onBlur={e => { setEditing(false); const raw = e.target.value; if (raw === '' || raw === '-') { onSave(null); return } const n = Number(raw); if (!isNaN(n)) onSave(n) }}
    onPressEnter={(e) => { setEditing(false); const raw = e.currentTarget.value; if (raw === '' || raw === '-') { onSave(null); return } const n = Number(raw); if (!isNaN(n)) onSave(n) }} />
}

function DateCellInput({ value, onSave }: { value: string | null | undefined; onSave: (v: string | null) => void }) {
  const [editing, setEditing] = useState(false)
  if (!editing) return <div style={{ width: '100%', height: 20, cursor: 'text', fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setEditing(true)}>{value ?? ''}</div>
  return <DatePicker size="small" autoFocus open style={{ width: '100%', fontSize: 10 }} defaultValue={value ? dayjs(value) : undefined} format="YYYY.MM.DD"
    onChange={d => { setEditing(false); onSave(d ? d.format('YYYY-MM-DD') : null) }}
    onOpenChange={open => { if (!open) setEditing(false) }} />
}

export default function CrudeExtractionPage() {
  const router = useRouter(); const { message } = App.useApp()
  const [data, setData] = useState<CrudeItem[]>([]); const [loading, setLoading] = useState(false); const [saving, setSaving] = useState(false)
  const [month, setMonth] = useState<number>(dayjs().month() + 1) // 默认当前月份
  const [createVisible, setCreateVisible] = useState(false); const [createForm] = Form.useForm()
  const [flVisible, setFlVisible] = useState(false); const [flForm] = Form.useForm()
  const [flOptions, setFlOptions] = useState<{ batch_no: string }[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = 'workshop=201-2' + (month > 0 ? `&month=${month}` : '')
      const r = await api(`/crude-extract/full-list?${params}`)
      if (r.code === 200) setData(r.data)
      const fr = await api('/crude-extract/fermentation-liquids')
      if (fr.code === 200) setFlOptions(fr.data)
    } catch { message.error('加载失败') } finally { setLoading(false) }
  }, [message, month])
  useEffect(() => { load() }, [load]) // eslint-disable-line react-hooks/set-state-in-effect

  // 自动计算
  const calcCrPq = (w: number | string | null | undefined, ct: number | string | null | undefined, ms: number | string | null | undefined) => w != null && ct != null && ms != null ? Math.round(Number(w) * Number(ct) * (100 - Number(ms))) / 10000 : null

  const saveST = async (id: string | undefined, field: string, value: number | string | null, st: SubTank | undefined) => {
    setSaving(true)
    const d: Record<string, unknown> = { [field]: value }
    if (field === 'crude_weight' || field === 'crude_content' || field === 'crude_moisture')
      d.crude_product_qty = calcCrPq(field === 'crude_weight' ? value : st?.crude_weight, field === 'crude_content' ? value : st?.crude_content, field === 'crude_moisture' ? value : st?.crude_moisture)
    await api(`/crude-extract/sub-tank-records/${id}`, { method: 'PUT', body: JSON.stringify(d) })
    // 本地更新，不重载
    setData(prev => prev.map(item => ({
      ...item, sub_tanks: (item.sub_tanks || []).map((sw) =>
        sw.sub_tank?.id === id ? { ...sw, sub_tank: { ...sw.sub_tank, ...d } } : sw)
    })))
    setSaving(false)
  }

  const saveNa = async (na: SodiumStep, field: string, value: number | null, stId: string | undefined, seq: number) => {
    setSaving(true); const d: Record<string, unknown> = { [field]: value }
    if (field === 'na_after_volume' || field === 'na_potency') {
      const av = field === 'na_after_volume' ? value : na.na_after_volume
      const pv = field === 'na_potency' ? value : na.na_potency
      d.na_product_qty = av != null && pv != null ? Math.round(av * pv / 10) / 100 : null
    }
    if (na.id) await api(`/crude-extract/sodium-steps/${na.id}`, { method: 'PUT', body: JSON.stringify(d) })
    else await api('/crude-extract/sodium-steps', { method: 'POST', body: JSON.stringify({ sub_tank_id: stId, seq_no: seq, ...d }) })
    // 本地更新
    if (na.id) {
      setData(prev => prev.map(item => ({
        ...item, sub_tanks: (item.sub_tanks || []).map((sw) => ({
          ...sw, sodium_steps: (sw.sodium_steps || []).map((s) => s.id === na.id ? { ...s, ...d } : s)
        }))
      })))
    } else { load() } // 新建步骤需要重载拿 ID
    setSaving(false)
  }

  const saveAc = async (ac: AcidStep, field: string, value: number | null, stId: string | undefined, seq: number) => {
    setSaving(true); const d: Record<string, unknown> = { [field]: value }
    if (field === 'acid_filter_volume' || field === 'acid_potency') {
      const av = field === 'acid_filter_volume' ? value : ac.acid_filter_volume
      const pv = field === 'acid_potency' ? value : ac.acid_potency
      d.acid_product_qty = av != null && pv != null ? Math.round(av * pv / 10) / 100 : null
    }
    if (ac.id) await api(`/crude-extract/acid-steps/${ac.id}`, { method: 'PUT', body: JSON.stringify(d) })
    else await api('/crude-extract/acid-steps', { method: 'POST', body: JSON.stringify({ sub_tank_id: stId, seq_no: seq, ...d }) })
    if (ac.id) {
      setData(prev => prev.map(item => ({
        ...item, sub_tanks: (item.sub_tanks || []).map((sw) => ({
          ...sw, acid_steps: (sw.acid_steps || []).map((a) => a.id === ac.id ? { ...a, ...d } : a)
        }))
      })))
    } else { load() }
    setSaving(false)
  }

  const addStepRow = async (stId: string | undefined, count: number) => {
    setSaving(true); const seq = count + 1
    await api('/crude-extract/sodium-steps', { method: 'POST', body: JSON.stringify({ sub_tank_id: stId, seq_no: seq }) })
    await api('/crude-extract/acid-steps', { method: 'POST', body: JSON.stringify({ sub_tank_id: stId, seq_no: seq }) })
    setSaving(false); load()
  }

  const handleCreate = async () => {
    try {
      const vals = await createForm.validateFields(); vals.workshop = '201-2'
      if (vals.produce_date) vals.produce_date = dayjs(vals.produce_date).format('YYYY-MM-DD')
      const r = await api('/crude-extract/refining-batches', { method: 'POST', body: JSON.stringify(vals) })
      if (r.code === 200) { message.success('创建成功'); setCreateVisible(false); createForm.resetFields(); load() }
      else message.error(r.message || '创建失败')
    } catch { message.error('请检查表单') }
  }

  const handleCreateFL = async () => {
    try {
      const vals = await flForm.validateFields()
      if (vals.create_date) vals.create_date = dayjs(vals.create_date).format('YYYY-MM-DD')
      const r = await api('/crude-extract/fermentation-liquids', { method: 'POST', body: JSON.stringify(vals) })
      if (r.code === 200) { message.success('发酵液创建成功'); setFlVisible(false); flForm.resetFields(); load() }
      else message.error(r.message || '创建失败')
    } catch { message.error('请检查表单') }
  }

  // ── 扁平化（useMemo 缓存，只在 data 变时重算）──
  const flattenData = () => {
    const rows: CrudeRow[] = []
    for (const item of data) {
      const rb = item.refining; if (!rb) continue
      const subTanks = item.sub_tanks || []
      for (const stWrap of subTanks) {
        const st: SubTank = stWrap.sub_tank || {}
        const sodiums = stWrap.sodium_steps || []; const acids = stWrap.acid_steps || []
        const maxLen = Math.max(sodiums.length, acids.length, 1)
        for (let i = 0; i < maxLen; i++)
          rows.push({ _key: `${rb.id}-${st.batch_no}-${i}`, fl: item.fermentation || {}, rb, st, sodium: sodiums[i] || {}, acid: acids[i] || {}, _seqNo: i + 1 })
      }
      const batchStart = rows.length - subTanks.reduce((a: number, sw) => a + Math.max((sw.sodium_steps || []).length, (sw.acid_steps || []).length, 1), 0)
      const totalBatchRows = rows.length - batchStart
      let cursor = batchStart
      for (const stWrap of subTanks) {
        const maxLen = Math.max((stWrap.sodium_steps || []).length, (stWrap.acid_steps || []).length, 1)
        for (let i = 0; i < maxLen; i++) {
          rows[cursor + i]._batchRowCount = totalBatchRows; rows[cursor + i]._stRowCount = maxLen
          rows[cursor + i]._isBatchFirst = (i === 0 && cursor === batchStart); rows[cursor + i]._isStFirst = (i === 0)
        }
        cursor += maxLen
      }
    }
    return rows
  }
  const flatRows = useMemo(() => flattenData(), [data]) // eslint-disable-line react-hooks/exhaustive-deps

  const B = (v: ReactNode, r: CrudeRow): ReactNode => (r._isBatchFirst ? (v ?? '') : null)
  const SM = (content: ReactNode, r: CrudeRow): ReactNode => (r._isStFirst ? content : null)
  const onBatchCell = (r: CrudeRow) => { const rowSpan = r._isBatchFirst ? r._batchRowCount ?? 0 : 0; return { rowSpan, style: rowSpan > 1 ? { verticalAlign: 'middle' } : undefined } }
  const onStCell = (r: CrudeRow) => { const rowSpan = r._isStFirst ? r._stRowCount ?? 0 : 0; return { rowSpan, style: rowSpan > 1 ? { verticalAlign: 'middle' } : undefined } }

  // ── 仪表盘数据 ──
  const dashData = useMemo(() => data.map(item => {
    const rb = item.refining || {}; const st0 = item.sub_tanks?.[0]?.sub_tank || {}
    return { ...rb, ...st0, produce_date: rb.produce_date }
  }), [data])

  const columns: TableColumnsType<CrudeRow> = useMemo(() => [
    { title: '日期', dataIndex: 'produce_date', width: 72, fixed: 'left', render: (_, r) => B(<DateCellInput value={r.rb?.produce_date} onSave={() => {}} />, r), onCell: onBatchCell },
    { title: '发酵液\n批号', key: 'fl_batch', width: 95, fixed: 'left', render: (_, r) => B(<Text style={{ fontSize: 10 }}>{r.fl?.batch_no}</Text>, r), onCell: onBatchCell },
    { title: '提炼\n生产批号', dataIndex: 'batch_no', width: 85, fixed: 'left', render: (_, r) => B(<Text strong style={{ fontSize: 10 }}>{r.rb?.batch_no}</Text>, r), onCell: onBatchCell },
    { title: '体积\n(KL)', key: 'fl_v', width: 55, render: (_, r) => SM(<CellInput value={r.st?.fl_volume} onSave={v => saveST(r.st?.id, 'fl_volume', v, r.st)} />, r), onCell: onStCell },
    { title: '效价\n(mg/L)', key: 'fl_p', width: 62, render: (_, r) => SM(<CellInput value={r.st?.fl_potency} onSave={v => saveST(r.st?.id, 'fl_potency', v, r.st)} />, r), onCell: onStCell },
    { title: '核对产\n品量(kg)', key: 'fl_pq', width: 68, render: (_, r) => SM(<CellInput value={r.st?.fl_product_qty} onSave={v => saveST(r.st?.id, 'fl_product_qty', v, r.st)} />, r), onCell: onStCell },
    { title: '总产量\n(kg)', key: 'fl_ti', width: 60, render: (_, r) => B(<CellInput value={r.st?.total_input} onSave={v => saveST(r.st?.id, 'total_input', v, r.st)} />, r), onCell: onBatchCell },
    { title: '累计放\n罐产品量', key: 'fl_cq', width: 62, render: (_, r) => B(<CellInput value={r.st?.cumulative_qty} onSave={v => saveST(r.st?.id, 'cumulative_qty', v, r.st)} />, r), onCell: onBatchCell },
    { title: '钠化批号', key: 'na_batch', width: 80, render: (_, r) => SM(<Text style={{ fontSize: 10 }}>{r.st?.batch_no}</Text>, r), onCell: onStCell },
    { title: '钠化\n前体积', key: 'na_bv', width: 50, render: (_, r) => <CellInput value={r.sodium?.na_before_volume} onSave={v => saveNa(r.sodium, 'na_before_volume', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '钠化\n后体积', key: 'na_av', width: 50, render: (_, r) => <CellInput value={r.sodium?.na_after_volume} onSave={v => saveNa(r.sodium, 'na_after_volume', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '效价\n(mg/L)', key: 'na_pot', width: 62, render: (_, r) => <CellInput value={r.sodium?.na_potency} onSave={v => saveNa(r.sodium, 'na_potency', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '产品量\n(kg)', key: 'na_pq', width: 55, render: (_, r) => <CellInput value={r.sodium?.na_product_qty} color="#1677ff" onSave={v => saveNa(r.sodium, 'na_product_qty', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '钠化总\n产品量', key: 'na_total', width: 58, render: (_, r) => <CellInput value={r.sodium?.sodium_total} onSave={v => saveNa(r.sodium, 'sodium_total', v, r.st?.batch_no, r._seqNo)} /> },
    { title: 'PH', key: 'na_ph', width: 38, render: (_, r) => <CellInput value={r.sodium?.ph_value} onSave={v => saveNa(r.sodium, 'ph_value', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '液碱\n用量L', key: 'na_alk', width: 52, render: (_, r) => <CellInput value={r.sodium?.alkali_usage} onSave={v => saveNa(r.sodium, 'alkali_usage', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '钠化滤\n液体积', key: 'ac_fv', width: 55, render: (_, r) => <CellInput value={r.acid?.acid_filter_volume} onSave={v => saveAc(r.acid, 'acid_filter_volume', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '效价', key: 'ac_pot', width: 45, render: (_, r) => <CellInput value={r.acid?.acid_potency} onSave={v => saveAc(r.acid, 'acid_potency', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '产品\n量kg', key: 'ac_pq', width: 50, render: (_, r) => <CellInput value={r.acid?.acid_product_qty} color="#1677ff" onSave={v => saveAc(r.acid, 'acid_product_qty', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '滤液\n小计', key: 'ac_fs', width: 50, render: (_, r) => <CellInput value={r.acid?.filter_subtotal} onSave={v => saveAc(r.acid, 'filter_subtotal', v, r.st?.batch_no, r._seqNo)} /> },
    { title: 'PH', key: 'ac_ph', width: 38, render: (_, r) => <CellInput value={r.acid?.ph_value} onSave={v => saveAc(r.acid, 'ph_value', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '硫酸\n用量L', key: 'ac_sul', width: 52, render: (_, r) => <CellInput value={r.acid?.acid_usage} onSave={v => saveAc(r.acid, 'acid_usage', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '酸化滤\n液含量', key: 'ac_fc', width: 55, render: (_, r) => <CellInput value={r.acid?.acid_filter_content} onSave={v => saveAc(r.acid, 'acid_filter_content', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '滤液\n合计', key: 'ac_ft', width: 50, render: (_, r) => <CellInput value={r.acid?.filter_total} onSave={v => saveAc(r.acid, 'filter_total', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '对发酵\n液收率', key: 'ac_yf', width: 55, render: (_, r) => <CellInput value={r.acid?.na_to_fermentation_yield} onSave={v => saveAc(r.acid, 'na_to_fermentation_yield', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '当月累\n计收率', key: 'ac_my', width: 55, render: (_, r) => <CellInput value={r.acid?.monthly_cumulative_yield} onSave={v => saveAc(r.acid, 'monthly_cumulative_yield', v, r.st?.batch_no, r._seqNo)} /> },
    { title: '粗品\n重量', key: 'cr_w', width: 55, render: (_, r) => SM(<CellInput value={r.st?.crude_weight} onSave={v => saveST(r.st?.id, 'crude_weight', v, r.st)} />, r), onCell: onStCell },
    { title: '袋种\nKG', key: 'cr_bw', width: 45, render: (_, r) => SM(<CellInput value={r.st?.bag_weight} onSave={v => saveST(r.st?.id, 'bag_weight', v, r.st)} />, r), onCell: onStCell },
    { title: '含量\n(%)', key: 'cr_ct', width: 50, render: (_, r) => SM(<CellInput value={r.st?.crude_content} onSave={v => saveST(r.st?.id, 'crude_content', v, r.st)} />, r), onCell: onStCell },
    { title: '水分', key: 'cr_ms', width: 45, render: (_, r) => SM(<CellInput value={r.st?.crude_moisture} onSave={v => saveST(r.st?.id, 'crude_moisture', v, r.st)} />, r), onCell: onStCell },
    { title: '产品量\n(kg)', key: 'cr_pq', width: 58, render: (_, r) => SM(<CellInput value={r.st?.crude_product_qty} color="#1677ff" onSave={v => saveST(r.st?.id, 'crude_product_qty', v, r.st)} />, r), onCell: onStCell },
    { title: '收率\n≥92%', key: 'cr_yd', width: 55, render: (_, r) => SM(<CellInput value={r.st?.yield_rate} color={r.st?.yield_rate != null ? (r.st.yield_rate >= 92 ? '#52c41a' : '#f5222d') : undefined} onSave={v => saveST(r.st?.id, 'yield_rate', v, r.st)} />, r), onCell: onStCell },
    { title: '累积粗\n品产品量', key: 'cr_cq', width: 62, render: (_, r) => SM(<CellInput value={r.st?.cumulative_crude_qty} onSave={v => saveST(r.st?.id, 'cumulative_crude_qty', v, r.st)} />, r), onCell: onStCell },
    { title: '粗品累\n计收率', key: 'cr_cy', width: 58, render: (_, r) => SM(<CellInput value={r.st?.cumulative_crude_yield} onSave={v => saveST(r.st?.id, 'cumulative_crude_yield', v, r.st)} />, r), onCell: onStCell },
    { title: '备注', key: 'cr_rm', width: 55, render: (_, r) => SM(<Input size="small" style={{ width: '100%', fontSize: 10, height: 20, padding: '0 2px' }} defaultValue={r.st?.remarks ?? undefined} onBlur={e => saveST(r.st?.id, 'remarks', e.target.value, r.st)} />, r), onCell: onStCell },
  ], [data]) // eslint-disable-line react-hooks/exhaustive-deps

  const subTankInfos: { batchNo: string | undefined; stId: string | undefined; rowCount: number }[] = []
  const seen = new Set<string>()
  for (const item of data) for (const stWrap of (item.sub_tanks || [])) {
    const st: SubTank = stWrap.sub_tank || {}
    if (st.batch_no && !seen.has(st.batch_no)) { seen.add(st.batch_no); subTankInfos.push({ batchNo: st.batch_no, stId: st.id, rowCount: Math.max((stWrap.sodium_steps || []).length, (stWrap.acid_steps || []).length, 1) }) }
  }

  return (
    <div className="p-6">
      <style>{`
        .crude-ledger-table .ant-table-thead > tr > th { white-space: normal !important; word-break: break-all; line-height: 1.1; padding: 2px 1px !important; font-size: 9px; text-align: center !important; vertical-align: middle !important; background: #fafafa; }
        .crude-ledger-table .ant-table-tbody > tr > td { white-space: normal !important; word-break: break-all; padding: 1px 2px !important; font-size: 10px; text-align: center !important; vertical-align: middle !important; line-height: 1.2; }
        .crude-ledger-table .ant-input-number { font-size: 10px; width: 100%; }
        .crude-ledger-table .ant-input-number input { font-size: 10px; padding: 0 2px; text-align: center; height: 20px; }
        .crude-ledger-table .ant-input-number .ant-input-number-handler-wrap { display: none; }
        .crude-ledger-table .ant-picker { width: 100%; }
        .crude-ledger-table .ant-picker input { font-size: 10px; padding: 0 2px; text-align: center; height: 20px; }
      `}</style>

      <Card size="small" className="mb-4">
        <Space wrap>{STAGES.map(s => <Button key={s.key} type={s.active ? 'primary' : 'default'} size="small" onClick={() => router.push(s.path)}>{s.label}</Button>)}</Space>
      </Card>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <Title level={4} style={{ margin: 0 }}><Button type="link" icon={<ArrowLeftOutlined />} onClick={() => router.push('/production/batches/workshop/201-2')}>返回车间</Button>粗提工段 — 发酵液→粗品（失焦自动保存）</Title>
        <Space size={8}>
          <Select size="small" style={{ width: 80 }} value={month} onChange={v => setMonth(v)}
            options={[{ value: 0, label: '全部' }, ...[1,2,3,4,5,6,7,8,9,10,11,12].map(m => ({ value: m, label: `${m}月` }))]} />
          <MCSheetsSyncButton />
          <MCTraceButton initialModule="crude" />
        </Space>
      </div>

      <Dashboard title="粗提工段仪表盘" data={dashData} dateField="produce_date" month={month}
        cards={[
          { title: '累计放罐产品量', value: () => { let total = 0; for (const item of data) for (const sw of (item.sub_tanks || [])) { const q = sw.sub_tank?.total_input; if (q != null) total += q } return total > 0 ? Math.round(total) : null; }, suffix: 'kg', precision: 0 },
          { title: '累计粗品产量', value: () => { let total = 0; for (const item of data) for (const sw of (item.sub_tanks || [])) { const q = sw.sub_tank?.crude_product_qty; if (q != null) total += q } return total > 0 ? Math.round(total) : null; }, suffix: 'kg', precision: 0 },
          { title: '粗品累计收率', value: () => { let totalIn = 0, totalOut = 0; for (const item of data) for (const sw of (item.sub_tanks || [])) { const s = sw.sub_tank || {}; if (s.total_input != null) totalIn += s.total_input; if (s.crude_product_qty != null) totalOut += s.crude_product_qty } return totalIn > 0 ? Math.round(totalOut / totalIn * 1000) / 10 : null; }, suffix: '%', precision: 1, color: (v) => v >= 92 ? '#52c41a' : '#f5222d' },
          { title: '批数', value: (_, f) => f.length, suffix: '批', precision: 0 },
          { title: '平均收率', value: (_, f) => { let s = 0, n = 0; for (const d of f) { if (d.yield_rate != null) { s += d.yield_rate; n++ } } return n > 0 ? Math.round(s / n * 100) / 100 : null; }, suffix: '%', precision: 1, color: (v) => v >= 92 ? '#52c41a' : '#f5222d' },
        ]}
        charts={[
          { key: 'yield', title: '单批收率趋势', unit: '%', color: '#1890ff', markLine: 92, label: '收率趋势', field: 'yield_rate' },
          { key: 'crudeWeight', title: '粗品产量趋势(kg)', unit: 'kg', color: '#52c41a', label: '粗品产量趋势', field: 'crude_weight' },
          { key: 'crudeContent', title: '含量趋势(%)', unit: '%', color: '#13c2c2', markLine: 90, label: '含量趋势', field: 'crude_content' },
          { key: 'flPotency', title: '放罐效价趋势(mg/L)', unit: 'mg/L', color: '#fa8c16', label: '放罐效价趋势', field: 'fl_potency' },
          { key: 'flVolume', title: '放罐体积趋势(KL)', unit: 'KL', color: '#722ed1', label: '放罐体积趋势', field: 'fl_volume' },
        ]}
      />

      <Card title="霉酚酸粗提台账" extra={<Space>
        <Button size="small" onClick={() => { flForm.resetFields(); setFlVisible(true) }}>新建发酵液</Button>
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => { createForm.resetFields(); setCreateVisible(true) }}>新建提炼批次</Button>
      </Space>}>
        <Table size="small" rowKey="_key" loading={loading} className="crude-ledger-table" dataSource={flatRows} scroll={{ x: 2400 }} columns={columns} pagination={false} />
        <div style={{ padding: '8px 0', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {subTankInfos.map(st => <Button key={st.stId} size="small" type="dashed" loading={saving} onClick={() => addStepRow(st.batchNo, st.rowCount)}>+ 步骤 ({st.batchNo})</Button>)}
          {subTankInfos.length === 0 && <Text type="secondary">暂无分罐数据</Text>}
        </div>
      </Card>

      <Modal title="新建提炼批次（自动创建分罐-1/-2）" open={createVisible} onOk={handleCreate} onCancel={() => setCreateVisible(false)} width={700} okText="确认" cancelText="取消" destroyOnHidden>
        <Form form={createForm} layout="vertical">
          <Row gutter={16}>
            <Col span={8}><Form.Item name="batch_no" label="提炼生产批号" rules={[{ required: true }]}><Input placeholder="MC-251224" /></Form.Item></Col>
            <Col span={8}><Form.Item name="fermentation_no" label="关联发酵液批号" rules={[{ required: true }]}>
              <Select showSearch placeholder="选择发酵液" options={flOptions.map((f) => ({ value: f.batch_no, label: f.batch_no }))} /></Form.Item></Col>
            <Col span={8}><Form.Item name="produce_date" label="生产日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={6}><Form.Item name="year" label="年份"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={6}><Form.Item name="month" label="月份"><InputNumber style={{ width: '100%' }} min={1} max={12} /></Form.Item></Col>
            <Col span={6}><Form.Item name="monthly_seq" label="月流水号"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>

      <Modal title="新建发酵液" open={flVisible} onOk={handleCreateFL} onCancel={() => setFlVisible(false)} width={700} okText="确认" cancelText="取消" destroyOnHidden>
        <Form form={flForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}><Form.Item name="batch_no" label="发酵液批号" rules={[{ required: true }]}><Input placeholder="MC-101-25202" /></Form.Item></Col>
            <Col span={12}><Form.Item name="workshop" label="发酵车间" rules={[{ required: true }]}>
              <Select options={[{ value: '101', label: '101车间' }, { value: '103', label: '103车间' }]} /></Form.Item></Col>
          </Row>
          <Row gutter={16}><Col span={8}><Form.Item name="year" label="年份"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="annual_seq" label="年度流水号"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="create_date" label="生产日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col></Row>
        </Form>
      </Modal>
    </div>
  )
}
