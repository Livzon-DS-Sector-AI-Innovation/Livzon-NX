'use client'

import { useMemo, useState } from 'react'
import { App, Button, Input, InputNumber, Select, Space, Table, Tooltip, Typography, Upload } from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import { confirmLedgerImport, prepareLedgerImport, previewLedgerImport } from '@/actions/energy-ledger'
import { resolveLedgerAction, type ImportPreview, type Meter, type TemplateDraft } from '@/lib/api/energy-ledger'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { importRows, type ImportColumn as Column } from './energy-import'
import styles from './EnergyWorkspace.module.css'
import { EnergyDatePicker } from './EnergyDatePicker'

export function EnergyImportClient({ meters, onChanged, initialYear }: { meters: Meter[]; onChanged: () => Promise<unknown>; initialYear?: number }) {
  const { message, modal } = App.useApp()
  const [file, setFile] = useState<File>()
  const [year, setYear] = useState(initialYear ?? new Date().getFullYear())
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const invalidPeriod = Boolean(startDate && endDate && startDate > endDate)
  const [preview, setPreview] = useState<ImportPreview>()
  const [draft, setDraft] = useState<TemplateDraft>()
  const [mapping, setMapping] = useState<Record<string, string | undefined>>({})
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const { columns } = useMemo(() => importRows(preview), [preview])

  function clearPreview() {
    setPreview(undefined); setDraft(undefined); setMapping({})
  }

  async function inspect() {
    if (!file) return
    if (invalidPeriod) { setError('有效结束日期不能早于开始日期'); return }
    setBusy(true); setError('')
    try {
      const data = new FormData(); data.set('file', file); data.set('year', String(year)); data.set('start_date', startDate); data.set('end_date', endDate)
      setPreview(await resolveLedgerAction(previewLedgerImport(data))); setDraft(undefined); setMapping({})
    } catch (cause) { setError(cause instanceof Error ? cause.message : '无法读取文件') }
    finally { setBusy(false) }
  }

  async function createDraft() {
    if (!preview) return
    setBusy(true); setError('')
    try { setDraft(await resolveLedgerAction(prepareLedgerImport(preview.id))); await onChanged(); message.success('原表字段与公式已识别，可直接导入和填写') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '识别原表字段与公式失败') }
    finally { setBusy(false) }
  }

  function pointFor(row: Column) { return mapping[row.key] ?? meters.find(meter => meter.definition.source_sheet === row.sheet && meter.definition.source_column === row.column)?.id }

  async function confirm() {
    if (!preview) return
    const mappings = columns.flatMap(row => { const point = pointFor(row); return point ? [{ sheet: row.sheet, column: row.column, point_id: point }] : [] })
    if (!mappings.length || !reason) { setError('请选择至少一个计量点映射并填写导入原因'); return }
    setBusy(true); setError('')
    try { setPreview(await resolveLedgerAction(confirmLedgerImport(preview.id, { mappings, reason }))); await onChanged(); message.success('历史原始数据已导入；重复数据不会重复入账') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '导入未完成，未覆盖已有数据') }
    finally { setBusy(false) }
  }

  return <Space orientation="vertical" style={{ width: '100%' }}>
    <PlatformNotice title="先预览、核对原表字段与来源映射，再确认导入" description="必须指定年份。原始记录来自五类表码和电量；原始字段及固定公式由工作簿识别。电量总计、小计、差额和分表总和由系统自动计算。缺少次日表码时保留缺项，不补零。未保留公式的结果表只作核对。原文件不会被修改。" />
    <div className={styles.filters}>
      <div className={`${styles.filterField} ${styles.filterFieldFile}`}><label htmlFor="energy-import-file">能源 Excel</label><Upload className={styles.importUpload} accept=".xlsx" maxCount={1} disabled={busy} showUploadList={false} fileList={file ? [{ uid: 'energy-import', name: file.name }] : []} beforeUpload={selected => { setFile(selected); clearPreview(); return false }}><Tooltip title={file?.name}><Button id="energy-import-file" className={styles.importUploadButton} icon={<UploadOutlined />} disabled={busy} aria-label="选择能源 Excel">{file?.name ?? '选择 Excel 文件'}</Button></Tooltip></Upload></div>
      <label className={`${styles.filterField} ${styles.filterFieldCompact}`} htmlFor="energy-import-year">导入年份<InputNumber id="energy-import-year" aria-label="导入年份" value={year} disabled={busy} onChange={value => { setYear(value || new Date().getFullYear()); clearPreview() }} min={2000} max={2100} /></label>
      <div className={styles.filterField}><label htmlFor="energy-import-start">有效开始日期</label><EnergyDatePicker id="energy-import-start" label="有效开始日期" value={startDate} disabled={busy} onChange={value => { setStartDate(value); clearPreview() }} /></div>
      <div className={styles.filterField}><label htmlFor="energy-import-end">有效结束日期</label><EnergyDatePicker id="energy-import-end" label="有效结束日期" value={endDate} disabled={busy} onChange={value => { setEndDate(value); clearPreview() }} /></div>
      <Button type="primary" disabled={!file} loading={busy} onClick={() => void inspect()}>预览文件</Button>
    </div>
    {error && <PlatformNotice type="error" title={error} />}
    {preview && <>
      <Typography.Text>状态：{preview.status === 'imported' ? '已导入' : '待核对'}；原始数值列 {columns.length} 项；有效范围 {String(preview.payload.start_date || '不限')} 至 {String(preview.payload.end_date || '不限')}</Typography.Text>
      {Array.isArray(preview.payload.notes) && <PlatformNotice title={preview.payload.notes.filter(item => typeof item === 'string').join(' ')} />}
      <Button loading={busy} onClick={() => modal.confirm({ title: '识别原表字段与公式', content: '从原表识别六类原始字段及自动计算公式，已有字段和数据不会覆盖。', onOk: createDraft })}>识别原表字段与公式</Button>
      {draft && <><PlatformNotice type="success" title={`识别 ${draft.meters.length} 个原始字段、${draft.rules.length} 个固定公式；${draft.issues.length} 项需核对`} /><ul>{draft.issues.map((issue, index) => <li key={`${index}:${issue}`}>{issue}</li>)}</ul></>}
      <Table<Column> rowKey="key" dataSource={columns} pagination={{ pageSize: 20 }} scroll={{ x: 750 }} columns={[{ title: '来源表', dataIndex: 'sheet' }, { title: '原始字段', dataIndex: 'label' }, { title: '记录数', dataIndex: 'count' }, { title: '对应计量点', render: (_, row) => <Select aria-label={`${row.sheet}${row.label}对应计量点`} allowClear showSearch optionFilterProp="label" value={pointFor(row)} style={{ width: 310 }} onChange={value => setMapping(current => ({ ...current, [row.key]: value || '' }))} options={meters.filter(meter => meter.definition.source_sheet === row.sheet || !meter.definition.source_sheet).map(meter => ({ value: meter.id, label: `${meter.definition.name}（${meter.definition.unit}）` }))} /> }]} />
      <Input.TextArea aria-label="导入原因" placeholder="填写导入来源及核对依据" value={reason} onChange={event => setReason(event.target.value)} maxLength={1000} />
      <Button disabled={!reason} loading={busy} onClick={() => modal.confirm({ title: '确认导入原始数据', content: '仅导入已映射的六类原始数值，计算字段不作为输入；与已有数据冲突时整批停止，不覆盖新填报数据。', onOk: confirm })}>确认导入已映射数据</Button>
    </>}
  </Space>
}
