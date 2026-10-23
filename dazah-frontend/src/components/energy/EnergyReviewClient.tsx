'use client'

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Input, InputNumber, Select, Space, Table, Typography } from 'antd'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { saveUsageReviews } from '@/actions/energy-ledger'
import {
  resolveLedgerAction,
  ledgerRequest,
  reportQuery,
  type UsageReview,
  type UsageReviewResponse,
  type WorkbookDataset,
  type WorkbookReport,
} from '@/lib/api/energy-ledger'
import { EnergyPeriodSelect } from './EnergyPeriodSelect'
import { EnergyDatePicker } from './EnergyDatePicker'
import styles from './EnergyWorkspace.module.css'

function periodLabel(review: UsageReview) {
  return (review.periods ?? [])
    .map(period => `${period.start_date} 至 ${period.end_date}`)
    .join('；') || '已清除'
}

export function EnergyReviewClient() {
  const { message } = App.useApp()
  const client = useQueryClient()
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [dataset, setDataset] = useState('')
  const [column, setColumn] = useState<string>()
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [reason, setReason] = useState('')
  const [source, setSource] = useState('')
  const [reportedValue, setReportedValue] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<UsageReviewResponse>()
  const reviews = useQuery({ queryKey: ['energy-ledger', 'usage-reviews'], queryFn: () => ledgerRequest<UsageReviewResponse[]>('/usage-reviews') })
  const datasets = useQuery({ queryKey: ['energy-ledger', 'datasets'], queryFn: () => ledgerRequest<WorkbookDataset[]>('/reporting/datasets') })
  const workbookQuery = reportQuery({ year, month, dataset })
  const workbook = useQuery({ queryKey: ['energy-ledger', 'review-workbook', workbookQuery], queryFn: () => ledgerRequest<WorkbookReport>(`/reporting/workbook?${workbookQuery}`), enabled: Boolean(dataset) })
  const datasetOptions = (datasets.data ?? []).filter(item => item.kind !== 'reading')

  async function submit() {
    const columnNumber = Number(column)
    if (!dataset || !Number.isInteger(columnNumber) || columnNumber < 2) { setError('请选择数据表和字段'); return }
    if (!startDate || !endDate) { setError('请选择待确认的开始和结束日期'); return }
    if (!reason.trim() || !source.trim()) { setError('请填写待确认原因和核对依据'); return }
    setBusy(true); setError('')
    const reported = reportedValue === undefined || reportedValue === ''
      ? {}
      : { [startDate]: reportedValue }
    const remaining = editing && editing.dataset === dataset && editing.column === columnNumber
      ? (editing.periods ?? []).slice(1)
      : []
    try {
      await resolveLedgerAction(saveUsageReviews({
        reviews: [{
          dataset,
          column: columnNumber,
          periods: [
            { start_date: startDate, end_date: endDate, reason: reason.trim(), source: source.trim(), reported_values: reported },
            ...remaining,
          ],
        }],
        reason: 'Web 复核',
      }))
      await client.invalidateQueries({ queryKey: ['energy-ledger'] })
      message.success('待确认区间已保存')
      setEditing(undefined)
      setStartDate(''); setEndDate(''); setReason(''); setSource(''); setReportedValue(undefined); setError('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '待确认区间未保存') }
    finally { setBusy(false) }
  }

  async function clear(review: UsageReviewResponse) {
    setBusy(true); setError('')
    try {
      await resolveLedgerAction(saveUsageReviews({
        reviews: [{ dataset: review.dataset, column: review.column, periods: [] }],
        reason: '确认完成',
      }))
      await client.invalidateQueries({ queryKey: ['energy-ledger'] })
      message.success('已清除该字段的待确认标记')
      setEditing(undefined)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '待确认标记未清除') }
    finally { setBusy(false) }
  }

  function edit(review: UsageReviewResponse) {
    setEditing(review)
    setDataset(review.dataset)
    setColumn(String(review.column))
    const period = review.periods?.[0]
    setStartDate(period?.start_date ?? '')
    setEndDate(period?.end_date ?? '')
    setReason(period?.reason ?? '')
    setSource(period?.source ?? '')
    setReportedValue(period ? period.reported_values?.[period.start_date] : undefined)
  }

  return <Space orientation="vertical" style={{ width: '100%' }}>
    <PlatformNotice
      title="标记或清除用量字段的待确认区间"
      description="待确认期间的原表值、系统计算值、原因和依据都会被保留；该区间不会进入有效汇总和占比。清除标记即视为已确认，原表读数不会被修改。"
    />
    {error && <PlatformNotice type="error" title={error} />}
    <div className={styles.filters}>
      <EnergyPeriodSelect year={year} month={month} onYear={setYear} onMonth={setMonth} />
      <label className={`${styles.filterField} ${styles.filterFieldWide}`} htmlFor="energy-review-dataset">
        数据表
        <Select id="energy-review-dataset" aria-label="数据表" showSearch optionFilterProp="label" value={dataset || undefined} onChange={value => { setEditing(undefined); setDataset(value); setColumn(undefined) }} options={datasetOptions.map(item => ({ value: item.name, label: item.name }))} loading={datasets.isLoading} />
      </label>
      <label className={`${styles.filterField} ${styles.filterFieldWide}`} htmlFor="energy-review-column">
        用量字段
        <Select id="energy-review-column" aria-label="用量字段" showSearch optionFilterProp="label" value={column} onChange={value => { setEditing(undefined); setColumn(value) }} options={(workbook.data?.columns ?? []).map(item => ({ value: item.key, label: `${item.label}（${item.unit}）` }))} loading={workbook.isLoading} disabled={!dataset} />
      </label>
    </div>
    <div className={styles.filters}>
      <div className={styles.filterField}><label htmlFor="energy-review-start">开始日期</label><EnergyDatePicker id="energy-review-start" label="开始日期" value={startDate} onChange={setStartDate} /></div>
      <div className={styles.filterField}><label htmlFor="energy-review-end">结束日期</label><EnergyDatePicker id="energy-review-end" label="结束日期" value={endDate} onChange={setEndDate} /></div>
      <label className={`${styles.filterField} ${styles.filterFieldWide}`} htmlFor="energy-review-reported">原表值（可选，填写到开始日期）
        <InputNumber<string> id="energy-review-reported" aria-label="原表值" stringMode value={reportedValue} onChange={value => setReportedValue(value ?? undefined)} placeholder="原表手填值" style={{ width: '100%' }} />
      </label>
    </div>
    <div className={styles.filters}>
      <label className={`${styles.filterField} ${styles.filterFieldWide}`} htmlFor="energy-review-reason">待确认原因<Input id="energy-review-reason" aria-label="待确认原因" value={reason} onChange={event => setReason(event.target.value)} maxLength={2000} /></label>
      <label className={`${styles.filterField} ${styles.filterFieldWide}`} htmlFor="energy-review-source">核对依据<Input id="energy-review-source" aria-label="核对依据" value={source} onChange={event => setSource(event.target.value)} maxLength={2000} /></label>
      <Button type="primary" loading={busy} onClick={() => void submit()}>保存待确认区间</Button>
    </div>
    <Typography.Title level={5}>当前待确认</Typography.Title>
    {reviews.error && <PlatformNotice type="error" title={reviews.error.message} action={<Button onClick={() => void reviews.refetch()}>重试</Button>} />}
    <Table<UsageReviewResponse>
      rowKey={row => `${row.dataset}:${row.column}`}
      dataSource={reviews.data}
      loading={reviews.isFetching}
      pagination={false}
      scroll={{ x: 800 }}
      columns={[
        { title: '数据表', dataIndex: 'dataset', width: 150 },
        { title: '字段列', dataIndex: 'column', width: 90 },
        { title: '区间', render: (_, row) => periodLabel(row) },
        { title: '原因', render: (_, row) => (row.periods ?? []).map(period => period.reason).join('；') },
        { title: '依据', render: (_, row) => (row.periods ?? []).map(period => period.source).join('；') },
        { title: '更新时间', dataIndex: 'updated_at', width: 170 },
        { title: '操作', width: 150, render: (_, row) => <Space><Button type="link" onClick={() => edit(row)}>编辑</Button><Button type="link" danger disabled={busy} onClick={() => void clear(row)}>清除</Button></Space> },
      ]}
    />
  </Space>
}
