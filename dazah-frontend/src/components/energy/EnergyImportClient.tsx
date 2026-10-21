'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { App, Button, Input, InputNumber, Select, Space, Table, Typography } from 'antd'
import { confirmLedgerImport, createLedgerTemplateDraft, previewLedgerImport, previewLedgerSnapshots } from '@/actions/energy-ledger'
import { resolveLedgerAction, ledgerRequest, type SnapshotOption, type ImportPreview, type Meter, type Rule, type TemplateDraft } from '@/lib/api/energy-ledger'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { importRows, type ImportColumn as Column, type ImportAdjustment as ManualValue } from './energy-import'
import styles from './EnergyWorkspace.module.css'

export function EnergyImportClient({ meters, rules, onChanged }: { meters: Meter[]; rules: Rule[]; onChanged: () => Promise<unknown> }) {
  const { message, modal } = App.useApp()
  const [file, setFile] = useState<File>()
  const [year, setYear] = useState(new Date().getFullYear())
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const invalidPeriod = Boolean(startDate && endDate && startDate > endDate)
  const [preview, setPreview] = useState<ImportPreview>()
  const [draft, setDraft] = useState<TemplateDraft>()
  const [mapping, setMapping] = useState<Record<string, string | undefined>>({})
  const [manualMetrics, setManualMetrics] = useState<Record<string, string | undefined>>({})
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [snapshotIds, setSnapshotIds] = useState<string[]>([])
  const snapshots = useQuery({ queryKey: ['energy-ledger', 'snapshot-options'], queryFn: () => ledgerRequest<SnapshotOption[]>('/imports/snapshot-options') })
  const { columns, manualRows } = useMemo(() => importRows(preview), [preview])

  function clearPreview() {
    setPreview(undefined); setDraft(undefined); setMapping({}); setManualMetrics({})
  }

  async function inspect() {
    if (!file) return
    if (invalidPeriod) { setError('有效结束日期不能早于开始日期'); return }
    setBusy(true); setError('')
    try {
      const data = new FormData(); data.set('file', file); data.set('year', String(year)); data.set('start_date', startDate); data.set('end_date', endDate)
      setPreview(await resolveLedgerAction(previewLedgerImport(data))); setDraft(undefined); setMapping({}); setManualMetrics({})
    } catch (cause) { setError(cause instanceof Error ? cause.message : '无法读取文件') }
    finally { setBusy(false) }
  }

  async function createDraft() {
    if (!preview) return
    setBusy(true); setError('')
    try { setDraft(await resolveLedgerAction(createLedgerTemplateDraft(preview.id))); await onChanged(); message.success('配置草案已生成，尚未启用；可到计量点和计算关系中核对') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '生成草案失败') }
    finally { setBusy(false) }
  }

  function pointFor(row: Column) { return mapping[row.key] ?? meters.find(meter => meter.definition.source_sheet === row.sheet && meter.definition.source_column === row.column)?.id }

  async function confirm() {
    if (!preview) return
    const mappings = columns.flatMap(row => { const point = pointFor(row); return point ? [{ sheet: row.sheet, column: row.column, point_id: point }] : [] })
    if (!mappings.length || !reason) { setError('请选择至少一个计量点映射并填写导入原因'); return }
    setBusy(true); setError('')
    const adjustments = manualRows.flatMap(row => { const metric = manualMetrics[row.key]; return metric ? [{ metric_key: metric, usage_date: row.date, value: row.value, mode: 'override' as const, reason: `${reason}；原表 ${row.sheet}·${row.label}` }] : [] })
    try { setPreview(await resolveLedgerAction(confirmLedgerImport(preview.id, { mappings, reason, adjustments }))); await onChanged(); message.success('历史原始数据已导入；重复数据不会重复入账') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '导入未完成，未覆盖已有数据') }
    finally { setBusy(false) }
  }

  return <Space orientation="vertical" style={{ width: '100%' }}>
    <PlatformNotice title="先预览、核对配置与来源映射，再确认导入" description="必须指定年份。原始记录来自五类表码和电量；汇总公式只用于提取计算草案与核对。配置草案默认停用，单位、部门、倍率和共享关系确认后才能启用。电量总计、小计、差额和分表总和由系统自动计算。缺少次日表码时保留缺项，不补零。未保留公式的结果表只作核对。原文件不会被修改。" />
    <div className={styles.toolbar}><input type="file" accept=".xlsx" aria-label="选择能源 Excel" disabled={busy} onChange={event => { setFile(event.target.files?.[0]); clearPreview() }} /><InputNumber aria-label="导入年份" value={year} disabled={busy} onChange={value => { setYear(value || new Date().getFullYear()); clearPreview() }} min={2000} max={2100} /><label>有效开始日期<Input style={{ width: 170 }} type="date" aria-label="有效开始日期" value={startDate} disabled={busy} onChange={event => { setStartDate(event.target.value); clearPreview() }} /></label><label>有效结束日期<Input style={{ width: 170 }} type="date" aria-label="有效结束日期" value={endDate} disabled={busy} onChange={event => { setEndDate(event.target.value); clearPreview() }} /></label><Button type="primary" disabled={!file} loading={busy} onClick={() => void inspect()}>预览文件</Button></div>
    <div className={styles.toolbar}><Select mode="multiple" maxCount={6} aria-label="选择历史快照" placeholder="选择六类原始表的历史快照（可选）" value={snapshotIds} disabled={busy} onChange={value => { setSnapshotIds(value); clearPreview() }} loading={snapshots.isLoading} style={{ minWidth: 330, maxWidth: '100%' }} options={snapshots.data?.map(item => ({ value: item.id, label: `${item.sheet_title} · ${item.captured_at} · 第${item.snapshot_number}版` }))} /><Button disabled={!snapshotIds.length || invalidPeriod} loading={busy} onClick={async () => { setBusy(true); setError(''); try { setPreview(await resolveLedgerAction(previewLedgerSnapshots({ snapshot_ids: snapshotIds, year, start_date: startDate || null, end_date: endDate || null }))); setDraft(undefined); setMapping({}); setManualMetrics({}) } catch (cause) { setError(cause instanceof Error ? cause.message : '快照读取失败') } finally { setBusy(false) } }}>预览所选历史快照</Button></div>
    {snapshots.error && <PlatformNotice type="warning" title="历史快照列表读取失败，仍可使用 Excel 导入" description={snapshots.error.message} />}
    {error && <PlatformNotice type="error" title={error} />}
    {preview && <>
      <Typography.Text>状态：{preview.status === 'imported' ? '已导入' : '待核对'}；原始数值列 {columns.length} 项；有效范围 {String(preview.payload.start_date || '不限')} 至 {String(preview.payload.end_date || '不限')}</Typography.Text>
      {Array.isArray(preview.payload.notes) && <PlatformNotice title={preview.payload.notes.filter(item => typeof item === 'string').join(' ')} />}
      <Button loading={busy} onClick={() => modal.confirm({ title: '生成未启用的配置草案', content: '将从表头和公式提取计量点、计算关系及疑似错行问题；相同编号的已有配置保留。生成后仍需核对并逐项启用。', onOk: createDraft })}>生成计量与计算配置草案</Button>
      {draft && <><PlatformNotice type="success" title={`提取 ${draft.meters.length} 个计量点、${draft.rules.length} 个计算关系；${draft.issues.length} 项需核对`} /><ul>{draft.issues.map((issue, index) => <li key={`${index}:${issue}`}>{issue}</li>)}</ul></>}
      <Table<Column> rowKey="key" dataSource={columns} pagination={{ pageSize: 20 }} scroll={{ x: 750 }} columns={[{ title: '来源表', dataIndex: 'sheet' }, { title: '原始字段', dataIndex: 'label' }, { title: '记录数', dataIndex: 'count' }, { title: '对应计量点', render: (_, row) => <Select aria-label={`${row.sheet}${row.label}对应计量点`} allowClear showSearch optionFilterProp="label" value={pointFor(row)} style={{ width: 310 }} onChange={value => setMapping(current => ({ ...current, [row.key]: value || '' }))} options={meters.filter(meter => meter.definition.source_sheet === row.sheet || !meter.definition.source_sheet).map(meter => ({ value: meter.id, label: `${meter.definition.name}（${meter.definition.unit}）` }))} /> }]} />
      {!!manualRows.length && <><Typography.Title level={5}>人工覆盖值候选（仅导入明确选择的修正）</Typography.Title><Table<ManualValue> rowKey="key" dataSource={manualRows} pagination={{ pageSize: 10 }} scroll={{ x: 750 }} columns={[{ title: '原表与字段', render: (_, row) => `${row.sheet}·${row.label}` }, { title: '日期', dataIndex: 'date' }, { title: '原表直接值', dataIndex: 'value' }, { title: '修正对应指标', render: (_, row) => <Select allowClear showSearch optionFilterProp="label" style={{ width: 280 }} value={manualMetrics[row.key]} placeholder="不导入；或选择已核对指标" options={[...meters.map(item => ({ value: `point:${item.definition.code}`, label: item.definition.name })), ...rules.map(item => ({ value: `rule:${item.definition.code}`, label: item.definition.name }))]} onChange={value => setManualMetrics(current => ({ ...current, [row.key]: value }))} /> }]} /></>}
      <Input.TextArea aria-label="历史导入原因" placeholder="填写导入来源及核对依据" value={reason} onChange={event => setReason(event.target.value)} maxLength={1000} />
      <Button disabled={!reason} loading={busy} onClick={() => modal.confirm({ title: '确认导入历史原始数据', content: '仅导入已映射的原始数值和已选人工修正；与已有数据冲突时整批停止，不覆盖新填报数据。', onOk: confirm })}>确认导入已映射数据</Button>
    </>}
  </Space>
}
