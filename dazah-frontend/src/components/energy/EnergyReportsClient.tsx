'use client'

import { useMemo, useState } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Drawer, Input, Select, Skeleton, Space, Statistic, Table, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import PlatformNotice from '@/components/shared/PlatformNotice'
import ThemedEChart from '@/components/shared/ThemedEChart'
import { CATEGORY_LABELS, QUALITY_LABELS, formatAmount, ledgerRequest, reportQuery, type Report, type UsageRow, type WorkbookDataset, type EnergyMetricOption } from '@/lib/api/energy-ledger'
import { EnergyPeriodSelect } from './EnergyPeriodSelect'
import { EnergyWorkbookClient } from './EnergyWorkbookClient'
import { monthPeriod, resolveMonth } from './energy-period'
import { EnergyEvidence } from './EnergyEvidence'
import { EnergyOverviewCards } from './EnergyOverviewCards'
import { EnergyUsageTrends } from './EnergyUsageTrends'
import styles from './EnergyWorkspace.module.css'

type Mode = 'overview' | 'reports' | 'analysis' | 'data-quality'
function totalKey(row: Report['totals'][number]) { return `${row.category}/${row.unit}/${row.quantity_kind}/${row.temperature}` }
function comparison(current: string | null, previous: string | null | undefined) {
  if (previous === undefined || previous === null || current === null) return '缺少可比数据'
  if (Number(previous) === 0) return '基期为零'
  return `${((Number(current) - Number(previous)) / Math.abs(Number(previous)) * 100).toFixed(1)}%`
}

export function EnergyReportsClient({ mode }: { mode: Mode }) {
  const params = useSearchParams()
  const pathname = usePathname()
  const selectedMonth = resolveMonth(new URLSearchParams(params))
  const [year, setYear] = useState(selectedMonth.year)
  const [month, setMonth] = useState(selectedMonth.month)
  const period = monthPeriod(selectedMonth.year, selectedMonth.month)
  const selectedDataset = mode === 'reports' ? params.get('dataset') || '日总量' : ''
  const [dataset, setDataset] = useState(selectedDataset)
  const datasets = useQuery({ queryKey: ['energy-ledger', 'datasets'], queryFn: () => ledgerRequest<WorkbookDataset[]>('/reporting/datasets'), enabled: mode === 'reports' })
  const [category, setCategory] = useState(params.get('category') || '')
  const [scope, setScope] = useState(params.get('report_scope') || (mode === 'overview' ? 'plant' : 'detail'))
  const [workshop, setWorkshop] = useState(params.get('workshop') || '')
  const [qualityStatus, setQualityStatus] = useState(params.get('quality_status') || '')
  const [metricKey, setMetricKey] = useState(params.get('metric_key') || '')
  const metrics = useQuery({ queryKey: ['energy-ledger', 'metrics'], queryFn: () => ledgerRequest<EnergyMetricOption[]>('/reporting/metrics'), enabled: mode === 'analysis' })
  const [traceId, setTraceId] = useState<string>()
  const startDate = period.start
  const endDate = period.end
  const reportScope = params.get('report_scope') || (mode === 'overview' ? 'plant' : 'detail')
  const page = Number(params.get('page') || 1)
  const query = reportQuery({ start_date: startDate, end_date: endDate, report_scope: reportScope, metric_key: params.get('metric_key') || undefined, category: params.get('category') || undefined, workshop: params.get('workshop') || undefined, quality_status: params.get('quality_status') || undefined, page, page_size: 100, include_basis: mode === 'overview' ? 'true' : undefined })
  const report = useQuery({ queryKey: ['energy-ledger', mode, query], queryFn: () => ledgerRequest<Report>(`/${mode === 'data-quality' ? 'data-quality' : 'reporting'}?${query}`), enabled: !selectedDataset })
  const previousEnd = dayjs(period.previousEnd)
  const previousStart = dayjs(period.previousStart)
  const baselineQuery = reportQuery({ start_date: previousStart.format('YYYY-MM-DD'), end_date: previousEnd.format('YYYY-MM-DD'), report_scope: reportScope, metric_key: params.get('metric_key') || undefined, category: params.get('category') || undefined, workshop: params.get('workshop') || undefined, page_size: 1 })
  const baseline = useQuery({ queryKey: ['energy-ledger', 'baseline', baselineQuery], queryFn: () => ledgerRequest<Report>(`/reporting?${baselineQuery}`), enabled: mode === 'analysis' })
  const yearQuery = reportQuery({ start_date: period.yearStart, end_date: period.yearEnd, report_scope: reportScope, metric_key: params.get('metric_key') || undefined, category: params.get('category') || undefined, workshop: params.get('workshop') || undefined, page_size: 1 })
  const previousYear = useQuery({ queryKey: ['energy-ledger', 'baseline', yearQuery], queryFn: () => ledgerRequest<Report>(`/reporting?${yearQuery}`), enabled: mode === 'analysis' })
  const trace = useQuery({ queryKey: ['energy-ledger', 'trace', traceId], queryFn: () => ledgerRequest<UsageRow>(`/reporting/trace/${traceId}`), enabled: Boolean(traceId) })

  function apply(nextPage = 1) {
    // All report data is queried on the client. Keep search changes local so
    // switching worksheets does not wait for another server layout render.
    const filters = mode === 'reports' ? { year, month, dataset } : { year, month, category, workshop, quality_status: qualityStatus, metric_key: metricKey, report_scope: scope, page: nextPage }
    window.history.replaceState(null, '', `${pathname}?${reportQuery(filters)}`)
  }

  const charts = useMemo(() => report.data?.totals.map(total => {
    const trend = report.data?.trend?.filter(row => totalKey(row) === totalKey(total)) ?? []
    const distribution = report.data?.distribution?.filter(row => totalKey(row) === totalKey(total)) ?? []
    const title = `${CATEGORY_LABELS[total.category]} ${total.temperature}（${total.unit}）`
    return { key: totalKey(total), title, trend: { tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: trend.map(row => row.usage_date) }, yAxis: { type: 'value', name: total.unit }, series: [{ name: title, type: 'line', connectNulls: false, data: trend.map(row => row.available_count === row.expected_count && row.value !== null ? Number(row.value) : null) }] }, distribution: { tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: distribution.map(row => row.workshop), axisLabel: { rotate: 25 } }, yAxis: { type: 'value', name: total.unit }, series: [{ name: title, type: 'bar', data: distribution.map(row => row.available_count === row.expected_count && row.value !== null ? Number(row.value) : null) }] } }
  }) ?? [], [report.data])

  return <>
    <div className={styles.filters}>
      <EnergyPeriodSelect year={year} month={month} onYear={setYear} onMonth={setMonth} />
      {mode === 'analysis' && <label className={`${styles.filterField} ${styles.filterFieldWide}`} htmlFor="energy-report-metric">单项指标<Select id="energy-report-metric" aria-label="单项指标" showSearch optionFilterProp="label" allowClear value={metricKey || undefined} onChange={value => setMetricKey(value || '')} placeholder="单项指标（可选）" loading={metrics.isLoading} options={metrics.data?.map(item => ({ value: item.metric_key, label: `${CATEGORY_LABELS[item.category]} · ${item.name}（${item.unit}）` }))} /></label>}
      {mode === 'reports' && <label className={styles.filterField} htmlFor="energy-report-dataset">数据表<Select id="energy-report-dataset" aria-label="数据表" showSearch optionFilterProp="label" virtual={false} value={dataset} onChange={setDataset} loading={datasets.isLoading} options={datasets.data?.map(item => ({ value: item.name, label: item.name })) ?? []} /></label>}
      {mode !== 'reports' && <>{mode !== 'data-quality' && <label className={styles.filterField} htmlFor="energy-report-scope">统计范围<Select id="energy-report-scope" aria-label="统计范围" disabled={mode === 'analysis' && Boolean(metricKey)} value={mode === 'analysis' && metricKey ? 'all' : scope} onChange={setScope} options={[{ value: 'plant', label: '已配置能源汇总' }, { value: 'detail', label: '车间及公共区域明细' }, { value: 'source', label: '原始计量点' }, { value: 'check', label: '核对与差值' }, ...(mode === 'analysis' && metricKey ? [{ value: 'all', label: '单项指标口径' }] : [])]} /></label>}
        <label className={styles.filterField} htmlFor="energy-report-category">能源类别<Select id="energy-report-category" aria-label="能源类别" value={category || undefined} allowClear onChange={value => setCategory(value || '')} placeholder="全部能源" options={Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ value, label }))} /></label>
        <label className={styles.filterField} htmlFor="energy-report-workshop">车间<Input id="energy-report-workshop" aria-label="车间" placeholder="车间名称" value={workshop} onChange={event => setWorkshop(event.target.value)} /></label></>}
      {mode === 'data-quality' && <label className={styles.filterField} htmlFor="energy-report-quality">异常类型<Select id="energy-report-quality" aria-label="异常类型" allowClear value={qualityStatus || undefined} onChange={value => setQualityStatus(value || '')} placeholder="全部异常" options={Object.entries(report.data?.quality_counts ?? {}).map(([value, count]) => ({ value, label: `${QUALITY_LABELS[value] || value}（${count}）` }))} /></label>}
      <Space>
        <Button type="primary" onClick={() => apply()}>查询</Button>
        <Button onClick={() => window.history.replaceState(null, '', pathname)}>重置</Button>
      </Space>
    </div>
    {datasets.error && <PlatformNotice type="error" title={datasets.error.message} action={<Button onClick={() => void datasets.refetch()}>重试</Button>} />}
    {metrics.error && <PlatformNotice type="error" title={metrics.error.message} action={<Button onClick={() => void metrics.refetch()}>重试</Button>} />}
    {selectedDataset && <EnergyWorkbookClient year={selectedMonth.year} month={selectedMonth.month} dataset={selectedDataset} />}
    {!selectedDataset && report.isLoading && <Skeleton active />}
    {!selectedDataset && report.error && <PlatformNotice type="error" title={report.error.message} action={<Button onClick={() => void report.refetch()}>重试</Button>} />}
    {!selectedDataset && report.data && <>
      {mode === 'data-quality' && <PlatformNotice title="待确认复核" description="待确认区间由能源配置管理员在“配置管理 → 待确认复核”中处理；清除后自动恢复有效汇总和占比。" />}
      {mode !== 'overview' && <PlatformNotice type={report.data.status === 'complete' ? 'success' : 'warning'} title={`${startDate} 至 ${endDate}：${QUALITY_LABELS[report.data.status]}${report.data.latest_complete_date ? `；当前范围最近完整日 ${report.data.latest_complete_date}` : ''}`} description="累计表码按次日减当日计算。不同能源、单位、温度和热量指标独立统计。期间累计只包含完整或已调整值，待确认值不计入；图表对不完整期间保留断点。原始计量点口径用于查询，不替代已配置的汇总口径。" />}
      {mode !== 'overview' && !report.data.total_count && <PlatformNotice title={mode === 'data-quality' ? '当前范围没有已记录的异常项' : '当前筛选范围没有可展示的能源结果'} description="请先配置并启用计量点、填报计划和计算关系。已提交数据会形成用量结果。" />}
      {mode === 'overview' && <EnergyOverviewCards report={report.data} />}
      {(mode === 'reports' || mode === 'analysis') && <div className={styles.grid}>
        {report.data.totals.map(total => <Card key={totalKey(total)}>
          <Statistic title={`${CATEGORY_LABELS[total.category]} ${total.temperature}`} value={formatAmount(total.value)} suffix={total.unit} />
          <Typography.Text type="secondary">有效 {total.available_count}/{total.expected_count}</Typography.Text>
          {mode === 'analysis' && <div><p>环比 {baseline.data?.status === 'complete' && total.available_count === total.expected_count ? comparison(total.value, baseline.data.totals.find(row => totalKey(row) === totalKey(total))?.value) : '期间数据不完整或缺失'}</p><p>同比 {previousYear.data?.status === 'complete' && total.available_count === total.expected_count ? comparison(total.value, previousYear.data.totals.find(row => totalKey(row) === totalKey(total))?.value) : '期间数据不完整或缺失'}</p></div>}
        </Card>)}
      </div>}
      {mode === 'analysis' && <Typography.Text type="secondary">环比期间 {previousStart.format('YYYY-MM-DD')} 至 {previousEnd.format('YYYY-MM-DD')}；同比期间为上一年相同日期。{baseline.error?.message || previousYear.error?.message}</Typography.Text>}
      {mode === 'overview' && report.data.totals.length > 0 && <EnergyUsageTrends report={report.data} />}
      {mode === 'analysis' && charts.map(chart => <Card key={chart.key}><Typography.Title level={5}>{chart.title}用量趋势</Typography.Title><ThemedEChart option={chart.trend} style={{ height: 280 }} /><Typography.Title level={5}>{chart.title}车间对比</Typography.Title><ThemedEChart option={chart.distribution} style={{ height: 280 }} /></Card>)}
      {mode !== 'data-quality' && !!report.data.period_metrics?.filter(metric => metric.quantity_kind === 'ratio' || reportScope === 'check').length && <Table rowKey="metric_key" dataSource={report.data.period_metrics.filter(metric => metric.quantity_kind === 'ratio' || reportScope === 'check')} pagination={false} columns={[{ title: '期间指标', dataIndex: 'name' }, { title: '期间值', render: (_, metric) => `${formatAmount(metric.value)} ${metric.unit}` }, { title: '完整度', dataIndex: 'status', render: (value: string) => QUALITY_LABELS[value] || value }]} />}
      {mode !== 'overview' && <Table<UsageRow> rowKey="id" loading={report.isFetching} dataSource={report.data.rows} scroll={{ x: 1000 }} pagination={{ current: page, total: report.data.total_count, pageSize: 100, showSizeChanger: false, onChange: next => { const updated = new URLSearchParams(params); updated.set('page', String(next)); window.history.replaceState(null, '', `${pathname}?${updated}`) } }} columns={[
        { title: '日期', dataIndex: 'usage_date', width: 115 },
        { title: '指标', dataIndex: 'name', width: 190 },
        { title: '车间／区域', dataIndex: 'workshop', render: value => value || '公共区域' },
        { title: '能源', dataIndex: 'category', render: (value: UsageRow['category']) => CATEGORY_LABELS[value] },
        { title: '温度', dataIndex: 'temperature' },
        { title: '计算值', render: (_, row) => formatAmount(row.calculated_value) },
        { title: '有效值', render: (_, row) => `${formatAmount(row.effective_value)} ${row.unit}` },
        { title: '状态', dataIndex: 'status', render: (value: string, row: UsageRow) => <Space wrap><Tag>{QUALITY_LABELS[value] || value}</Tag>{Boolean(row.provenance.late) && <Tag>逾期补填</Tag>}</Space> },
        { title: '依据', render: (_, row) => row.provenance.unmaterialized ? '尚无原始记录' : <Button type="link" onClick={() => setTraceId(row.id)}>查看来源</Button> },
      ]} />}
    </>}
    <Drawer title="用量计算依据" open={Boolean(traceId)} onClose={() => setTraceId(undefined)} size={600}>
      {trace.error && <PlatformNotice type="error" title={trace.error.message} />}
      {trace.data && <Space orientation="vertical"><Typography.Title level={4}>{trace.data.name} · {trace.data.usage_date}</Typography.Title><p>计算值 {formatAmount(trace.data.calculated_value)}，有效值 {formatAmount(trace.data.effective_value)} {trace.data.unit}</p><p>状态：{QUALITY_LABELS[trace.data.status] || trace.data.status}</p><Typography.Paragraph>来源读数日期：{Array.isArray(trace.data.provenance.reading_dates) ? trace.data.provenance.reading_dates.join('、') : '由关联计量点计算'}</Typography.Paragraph><Typography.Paragraph>配置版本：{String(trace.data.provenance.configuration_version ?? '—')}</Typography.Paragraph><EnergyEvidence value={trace.data.provenance} /></Space>}
    </Drawer>
  </>
}
