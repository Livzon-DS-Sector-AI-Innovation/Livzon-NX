'use client'

import { useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Collapse, Empty, Segmented, Select, Skeleton, Space, Statistic, Table, Tag, Typography } from 'antd'
import PlatformNotice from '@/components/shared/PlatformNotice'
import ThemedEChart from '@/components/shared/ThemedEChart'
import { QUALITY_LABELS, formatAmount, ledgerRequest, reportQuery, type WorkbookReport } from '@/lib/api/energy-ledger'
import { DASHBOARD_GROUPS, datasetGroup, trendOption, workbookMetric } from './dashboard-data'
import { SUMMARY_METRICS, dashboardPeriods, displayMetric, monthlyOption, summarizeMetric, workbookEvidence } from './dashboard-summary'
import { EnergyPeriodSelect } from './EnergyPeriodSelect'
import { resolveMonth } from './energy-period'
import styles from './EnergyDashboard.module.css'

const DATASETS = [
  '日总量', '饮用水量', '蒸汽量', '冰水量', '空气量', '循环水量',
  '101车间', '102-1车间', '103-1车间', '103-2车间', '201-1车间', '201-2车间', '203-1车间', '203-2车间', '203-3车间',
  '饮用水码', '冰水码', '蒸汽码', '循环水码', '空气码', '电量',
]

function sourceQuery(year: number, month: number, dataset: string) {
  return reportQuery({ year, month, dataset })
}

function SourceDetail({ year, month }: { year: number; month: number }) {
  const [dataset, setDataset] = useState('日总量')
  const [selected, setSelected] = useState('')
  const query = sourceQuery(year, month, dataset)
  const request = useQuery({ queryKey: ['energy-ledger', 'workbook', query], queryFn: () => ledgerRequest<WorkbookReport>(`/reporting/workbook?${query}`), staleTime: 60_000 })
  const data = request.data
  const metric = data ? workbookMetric(data, data.columns.some(column => column.key === selected) ? selected : data.columns[0]?.key ?? '') : null
  return <Space orientation="vertical" style={{ width: '100%' }}>
    <div className={styles.controls}>
      <label className={styles.field}>数据表<Select aria-label="明细数据表" showSearch optionFilterProp="label" value={dataset} onChange={value => { setDataset(value); setSelected('') }} options={DASHBOARD_GROUPS.map(group => ({ label: group.label, options: DATASETS.filter(name => datasetGroup({ name, kind: name.endsWith('码') ? 'reading' : name === '电量' ? 'mixed' : 'usage' }) === group.key).map(name => ({ value: name, label: name })) }))} /></label>
      {metric?.column && <label className={styles.field}>统计字段<Select aria-label="明细统计字段" showSearch optionFilterProp="label" value={metric.column.key} onChange={setSelected} options={data?.columns.map(column => ({ value: column.key, label: `${column.label}（${column.unit}）` }))} /></label>}
    </div>
    {request.isPending && <Skeleton active />}
    {request.error && <PlatformNotice type="error" title={request.error.message} action={<Button onClick={() => void request.refetch()}>重试</Button>} />}
    {metric?.column && <>
      <Typography.Text type="secondary">{metric.reading ? '原始累计表码，不做期间求和' : '原表字段'} · {metric.column.unit}</Typography.Text>
      {metric.points.some(point => point.value !== null) ? <ThemedEChart option={trendOption(metric.column.label, metric.column.unit, metric.points, metric.reading)} style={{ height: 280 }} /> : <Empty description="该字段暂无有效数据" />}
      <Table size="small" rowKey="date" pagination={{ pageSize: 10, showSizeChanger: false }} scroll={{ x: 560 }} dataSource={metric.points} columns={[
        { title: '日期', dataIndex: 'date' },
        { title: `原表值（${metric.column.unit}）`, render: (_, row) => formatAmount(row.raw) },
        { title: '状态', render: (_, row) => QUALITY_LABELS[row.status] || row.status },
        { title: '字段／计算依据', render: (_, row) => workbookEvidence(data?.rows.find(item => item.date === row.date)?.cells[metric.column!.key]?.provenance), ellipsis: true },
      ]} />
    </>}
    {data && !data.columns.length && <Empty description="原表中暂无可展示字段" />}
  </Space>
}

export function EnergyDashboard() {
  const params = useSearchParams()
  const client = useQueryClient()
  const period = resolveMonth(new URLSearchParams(params))
  const periods = dashboardPeriods(period.year, period.month)
  const [selected, setSelected] = useState('6')
  const [comparison, setComparison] = useState('total')
  const [details, setDetails] = useState(false)
  const currentQuery = sourceQuery(period.year, period.month, '日总量')
  const current = useQuery({ queryKey: ['energy-ledger', 'workbook', currentQuery], queryFn: () => ledgerRequest<WorkbookReport>(`/reporting/workbook?${currentQuery}`), staleTime: 60_000 })
  const history = useQueries({ queries: periods.slice(0, -1).map(value => {
    const query = sourceQuery(value.year, value.month, '日总量')
    return { queryKey: ['energy-ledger', 'workbook', query], queryFn: () => ledgerRequest<WorkbookReport>(`/reporting/workbook?${query}`), staleTime: 60_000, enabled: !current.isPending }
  }) })
  const requests = [...history, current]
  const data = current.data
  const label = SUMMARY_METRICS.find(item => item.key === selected)!.label
  const metric = data?.columns.length ? summarizeMetric(data, selected) : null
  const periodLabel = `${period.month} 月`
  const sourceUnit = metric?.column?.unit ?? '待确认'
  const unit = sourceUnit === '待确认' ? '原表数值' : sourceUnit
  const comparisonAvailable = requests.some(request => {
    if (!request.data) return false
    const summary = summarizeMetric(request.data, selected)
    return summary.column?.unit === sourceUnit && summary.total !== null
  })
  const failures = requests.flatMap((request, index) => request.error ? [`${periods[index].year}年${periods[index].month}月：${request.error.message}`] : [])

  function changePeriod(year: number, month: number) {
    const query = new URLSearchParams(params)
    query.set('year', String(year))
    query.set('month', String(month))
    window.history.replaceState(null, '', `/energy?${query}`)
  }

  return <div className={styles.dashboard}>
    <header className={styles.header}>
      <Typography.Title level={3}>能源仪表盘</Typography.Title>
      <div className={styles.controls}>
        <EnergyPeriodSelect year={period.year} month={period.month} onYear={year => changePeriod(year, period.month)} onMonth={month => changePeriod(period.year, month)} />
        <Button onClick={() => void client.invalidateQueries({ queryKey: ['energy-ledger', 'workbook'] })} loading={requests.some(request => request.isFetching)}>刷新</Button>
      </div>
    </header>
    {failures.length > 0 && <PlatformNotice type="error" title="部分月份原表暂不可用" description={failures.join('；')} action={<Button onClick={() => { requests.forEach(request => { if (request.error) void request.refetch() }) }}>重试</Button>} />}
    <section aria-label="月度能源概览" className={styles.overview}>
      <Typography.Title level={4}>{periodLabel}能源概览</Typography.Title>
      {current.isPending && <Skeleton active />}
      {data && !data.columns.length && <Empty description={`${period.year} 年 ${period.month} 月暂无已配置的能源字段`} />}
      {data && data.columns.length > 0 && <div className={styles.metrics}>{SUMMARY_METRICS.map(item => {
        const summary = summarizeMetric(data, item.key)
        return <Button type="text" key={item.key} className={styles.metric} aria-pressed={selected === item.key} onClick={() => setSelected(item.key)}>
          <span className={styles.metricLabel}>{item.label}<span>{summary.column?.unit && summary.column.unit !== '待确认' ? summary.column.unit : '单位未注明'}</span></span>
          <span className={styles.metricValue}>{displayMetric(summary.subtotal)}</span>
          <span className={styles.metricHint}>累计用量 · 已统计 {summary.available} 天</span>
        </Button>
      })}</div>}
    </section>
    {metric && <>
      <div className={styles.charts}>
        <Card size="small" title={`${label}每日趋势`} className={styles.chart}>
          <div className={styles.facts}>
            <Statistic title="日均用量" value={displayMetric(metric.average)} suffix={unit} />
            <Statistic title={`最高日用量${metric.peak ? ` · ${metric.peak.date.slice(5)}` : ''}`} value={displayMetric(metric.peak?.value ?? null)} suffix={unit} />
            <Tag>已统计 {metric.available} 天</Tag>
          </div>
          {metric.available ? <ThemedEChart option={trendOption(label, unit, metric.points)} style={{ height: 260 }} /> : <Empty description="本月暂无有效日数据" />}
          <Collapse size="small" style={{ marginTop: 12 }} items={[{ key: 'daily', label: `${label}每日数值`, children: <Table size="small" rowKey="date" pagination={{ pageSize: 10, showSizeChanger: false }} scroll={{ x: 640 }} dataSource={metric.points} columns={[
            { title: '日期', dataIndex: 'date' },
            { title: `有效用量（${unit}）`, render: (_, row) => displayMetric(row.value) },
            { title: '原表值', render: (_, row) => formatAmount(row.raw) },
            { title: '状态', render: (_, row) => QUALITY_LABELS[row.status] || row.status },
            { title: '字段／计算依据', dataIndex: 'evidence', ellipsis: true },
          ]} /> }]} />
        </Card>
        <Card size="small" title={`${label}月度对比`} className={styles.chart}>
          <Segmented aria-label="月度对比口径" value={comparison} onChange={setComparison} options={[{ value: 'total', label: '月累计' }, { value: 'average', label: '日均' }]} />
          {comparisonAvailable ? <ThemedEChart option={monthlyOption(label, sourceUnit, requests.map(request => request.data), selected, comparison === 'average', periods)} style={{ height: 260 }} /> : <Empty description="暂无月度对比数据" />}
          <Typography.Text type="secondary">对比所选月及前三个月；累计和日均按各月已统计的有效天数计算。</Typography.Text>
          <Collapse size="small" style={{ marginTop: 12 }} items={[{ key: 'months', label: '查看月度数值', children: <Table size="small" rowKey="month" pagination={false} scroll={{ x: 420 }} dataSource={requests.map((request, index) => ({ month: `${periods[index].year}-${periods[index].month}`, summary: request.data ? summarizeMetric(request.data, selected) : null }))} columns={[
            { title: '月份', dataIndex: 'month' },
            { title: '月累计', render: (_, row) => displayMetric(row.summary?.column?.unit === sourceUnit ? row.summary.total : null) },
            { title: '日均', render: (_, row) => displayMetric(row.summary?.column?.unit === sourceUnit ? row.summary.average : null) },
            { title: '有效天数', render: (_, row) => row.summary ? `${row.summary.available} 天` : '原表暂不可用' },
          ]} /> }]} />
        </Card>
      </div>
    </>}
    <Collapse onChange={keys => setDetails(keys.includes('source'))} items={[{ key: 'source', label: '查看分类用量、车间与原始表码', children: details ? <SourceDetail key={`${period.year}-${period.month}`} year={period.year} month={period.month} /> : null }]} />
  </div>
}
