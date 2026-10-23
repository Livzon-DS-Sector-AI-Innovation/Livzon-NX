'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Collapse, Empty, Select, Skeleton, Space, Table, Tabs, Tag, Typography } from 'antd'
import PlatformNotice from '@/components/shared/PlatformNotice'
import ThemedEChart from '@/components/shared/ThemedEChart'
import { CATEGORY_LABELS, QUALITY_LABELS, formatAmount, ledgerRequest, reportQuery, type Report, type WorkbookDataset, type WorkbookReport } from '@/lib/api/energy-ledger'
import { EnergyPeriodSelect } from './EnergyPeriodSelect'
import { EnergyOverviewCards } from './EnergyOverviewCards'
import { monthPeriod, resolveMonth } from './energy-period'
import { DASHBOARD_GROUPS, QUANTITY_LABELS, contributionOption, datasetGroup, shareOption, trendOption, workbookMetric, workshopGroups } from './dashboard-data'
import styles from './EnergyWorkspace.module.css'

function DatasetChart({ dataset, year, month }: { dataset: WorkbookDataset; year: number; month: number }) {
  const [selected, setSelected] = useState('')
  const query = reportQuery({ year, month, dataset: dataset.name })
  const report = useQuery({ queryKey: ['energy-ledger', 'workbook', query], queryFn: () => ledgerRequest<WorkbookReport>(`/reporting/workbook?${query}`), staleTime: 60_000 })
  const data = report.data
  const metric = data ? workbookMetric(data, data.columns.some(column => column.key === selected) ? selected : data.columns[0]?.key ?? '') : null
  const column = metric?.column
  return <Card className={styles.trendCard} title={dataset.name} extra={<Link href={`/energy/reports?${query}`}>查看台账</Link>}>
    {report.isPending && <Skeleton active />}
    {report.error && <PlatformNotice type="error" title={`${dataset.name}：${report.error.message}`} action={<Button onClick={() => void report.refetch()}>重试</Button>} />}
    {data && !data.columns.length && <Empty description="当前权限内暂无已配置字段" />}
    {column && metric && <Space orientation="vertical" style={{ width: '100%' }}>
      <label className={`${styles.filterField} ${styles.dashboardMetric}`} htmlFor={`dashboard-${dataset.name}`}>统计字段<Select id={`dashboard-${dataset.name}`} aria-label={`${dataset.name}统计字段`} showSearch optionFilterProp="label" value={column.key} onChange={setSelected} options={data?.columns.map(item => ({ value: item.key, label: `${item.label}（${item.unit}）` }))} /></label>
      {metric.points.some(point => point.status === 'pending_review') && <PlatformNotice type="warning" title={`本字段 ${metric.points.filter(point => point.status === 'pending_review').length} 天待确认，已排除在有效汇总和占比之外`} description={[...new Set(metric.points.flatMap(point => point.reviews.map(review => review.reason)))].join('；')} />}
      <div className={styles.dashboardCharts}>
        <section className={styles.trendCard}>
          <Typography.Text type="secondary">{metric.reading ? '原始表码趋势' : '每日指标趋势'} · 单位：{column.unit} · 有效 {metric.points.filter(point => point.value !== null).length}/{metric.points.length} 天</Typography.Text>
          {metric.points.some(point => point.value !== null) ? <ThemedEChart option={trendOption(column.label, column.unit, metric.points, metric.reading)} style={{ height: 280 }} /> : <Empty description="暂无完整有效的日数据" />}
        </section>
        {!metric.reading && <section className={styles.trendCard}>
          <Typography.Text strong>月内每日贡献占比</Typography.Text>
          {metric.shares.length ? <ThemedEChart option={contributionOption(column.label, metric.shares)} style={{ height: 280 }} /> : <Typography.Paragraph type="secondary">占比暂不可用：需要整月完整、非负且合计大于零的可累计用量；比例及核对差值不计算占比。</Typography.Paragraph>}
        </section>}
      </div>
      <Collapse items={[{ key: 'values', label: '查看每日数值与占比', children: <Table pagination={false} size="small" rowKey="date" scroll={{ x: 850, y: 260 }} dataSource={metric.points} columns={[
        { title: '日期', dataIndex: 'date' },
        { title: `有效值（${column.unit}）`, render: (_, row) => formatAmount(row.raw) },
        { title: '原表值（待确认）', render: (_, row) => row.reviews.map(review => review.reportedValue).filter(value => value !== null).map(value => formatAmount(value)).join('；') || '—' },
        { title: '系统计算值', render: (_, row) => formatAmount(row.calculated) },
        { title: '状态', dataIndex: 'status', render: value => QUALITY_LABELS[value] || value },
        { title: '异常原因／依据', render: (_, row) => row.reviews.map(review => `${review.reason}；${review.source}`).join('；') || '—' },
        { title: '占比', render: (_, row) => metric.shares.length ? `${(Number(row.value) / metric.shares.reduce((sum, item) => sum + item.value, 0) * 100).toFixed(2)}%` : '—' },
      ]} /> }]} />
    </Space>}
  </Card>
}

function WorkshopComparison({ report }: { report: Report }) {
  const groups = workshopGroups(report)
  const [selection, setSelection] = useState('')
  const key = groups.has(selection) ? selection : groups.keys().next().value
  const group = key ? groups.get(key) : undefined
  const category = group?.rows[0]?.category
  const title = category ? `${CATEGORY_LABELS[category]} ${group.rows[0].temperature} · ${group.unit} · ${QUANTITY_LABELS[group.rows[0].quantity_kind] || '独立计量'}` : ''
  return <Card title="同口径车间用量对比">
    {!group ? <Empty description="当前权限内暂无车间用量" /> : <Space orientation="vertical" style={{ width: '100%' }}>
      <label className={`${styles.filterField} ${styles.dashboardMetric}`} htmlFor="dashboard-workshop-metric">能源口径<Select id="dashboard-workshop-metric" aria-label="车间对比能源口径" value={key} onChange={setSelection} options={[...groups].map(([value, item]) => ({ value, label: `${CATEGORY_LABELS[item.rows[0].category]} ${item.rows[0].temperature} · ${item.unit} · ${QUANTITY_LABELS[item.rows[0].quantity_kind] || '独立计量'}` }))} /></label>
      <Typography.Text type="secondary">分母为当前权限内同口径车间及公共区域的合计；不代表全厂能源结构。缺项或异常期间不计算占比。</Typography.Text>
      <div className={styles.trendGrid}>
        <ThemedEChart option={{ aria: { enabled: true }, tooltip: { trigger: 'axis' }, grid: { left: 85, right: 30, top: 30, bottom: 50 }, legend: { bottom: 0 }, xAxis: { type: 'value', name: group.unit }, yAxis: { type: 'category', data: group.rows.map(row => row.workshop || '公共区域') }, series: [{ name: title, type: 'bar', data: group.rows.map(row => row.expected_count > 0 && row.available_count === row.expected_count && row.value !== null ? Number(row.value) : null) }] }} style={{ height: 320 }} />
        {group.shares.length ? <ThemedEChart option={shareOption(title, group.shares)} style={{ height: 320 }} /> : <Empty description="期间数据不完整、异常或合计为零，暂不计算车间占比" />}
      </div>
      <Collapse items={[{ key: 'values', label: '查看车间数值与占比', children: <Table size="small" pagination={false} rowKey="workshop" scroll={{ x: 450 }} dataSource={group.rows} columns={[
        { title: '车间／区域', render: (_, row) => row.workshop || '公共区域' },
        { title: `期间已有数值（${group.unit}）`, render: (_, row) => formatAmount(row.value) },
        { title: '完整度', render: (_, row) => `${row.available_count}/${row.expected_count}` },
        { title: '占比', render: (_, row) => group.shares.length ? `${(Number(row.value) / group.shares.reduce((sum, item) => sum + item.value, 0) * 100).toFixed(2)}%` : '—' },
      ]} /> }]} />
    </Space>}
  </Card>
}

export function EnergyDashboard() {
  const params = useSearchParams()
  const selected = resolveMonth(new URLSearchParams(params))
  const [year, setYear] = useState(selected.year)
  const [month, setMonth] = useState(selected.month)
  const client = useQueryClient()
  const period = monthPeriod(selected.year, selected.month)
  const datasets = useQuery({ queryKey: ['energy-ledger', 'datasets'], queryFn: () => ledgerRequest<WorkbookDataset[]>('/reporting/datasets'), staleTime: 60_000 })
  const query = (scope: string) => reportQuery({ start_date: period.start, end_date: period.end, report_scope: scope, page_size: 1, include_basis: scope === 'plant' ? 'true' : undefined })
  const plant = useQuery({ queryKey: ['energy-ledger', 'dashboard-plant', query('plant')], queryFn: () => ledgerRequest<Report>(`/reporting?${query('plant')}`) })
  const workshops = useQuery({ queryKey: ['energy-ledger', 'dashboard-workshops', query('detail')], queryFn: () => ledgerRequest<Report>(`/reporting?${query('detail')}`) })
  return <>
    <div className={styles.filters}>
      <EnergyPeriodSelect year={year} month={month} onYear={setYear} onMonth={setMonth} />
      <Button type="primary" onClick={() => window.history.replaceState(null, '', `/energy?${reportQuery({ year, month })}`)}>查询</Button>
      <Button onClick={() => void client.invalidateQueries({ queryKey: ['energy-ledger'] })} loading={plant.isFetching || workshops.isFetching || datasets.isFetching}>刷新</Button>
      <Tag>{datasets.data?.length ?? '—'} 张能源数据表</Tag>
    </div>
    <PlatformNotice title="原始表码 → 分类用量 → 日总量／车间台账；各层分别展示，避免重复累计" description="五类累计表码通过次日减当日及倍率形成用量，电量由原始电量及固定公式形成。五类用量和电量被日总量、九张车间表引用；具体字段依赖以已导入公式和计算依据为准。不同能源、单位、温度、热量与体积分别统计。折线对缺项和异常保留断点，环图仅对同口径完整非负用量计算占比。" />
    {Boolean(plant.data?.quality_counts?.pending_review || workshops.data?.quality_counts?.pending_review) && <PlatformNotice type="warning" title="存在待确认用量，已排除在有效汇总和占比之外" description="待确认记录保留原表相关值、系统计算值、异常原因及核对依据。已确认日期正常展示；异常会沿计算依赖传播。可在各表每日明细、台账及数据质量中查看。" action={<Link href={`/energy/data-quality?${reportQuery({ year: selected.year, month: selected.month, quality_status: 'pending_review' })}`}>查看待确认</Link>} />}
    <Typography.Title level={4}>已配置能源汇总</Typography.Title>
    {plant.isPending && <Skeleton active />}
    {plant.error && <PlatformNotice type="error" title={plant.error.message} action={<Button onClick={() => void plant.refetch()}>重试</Button>} />}
    {plant.data && (plant.data.totals.length ? <EnergyOverviewCards report={plant.data} /> : <Empty description="当前权限内暂无已配置的能源汇总" />)}
    {workshops.isPending && <Skeleton active />}
    {workshops.error && <PlatformNotice type="error" title={`车间对比：${workshops.error.message}`} action={<Button onClick={() => void workshops.refetch()}>重试</Button>} />}
    {workshops.data && <WorkshopComparison report={workshops.data} />}
    <Typography.Title level={4}>21 张数据表趋势与占比</Typography.Title>
    {datasets.isPending && <Skeleton active />}
    {datasets.error && <PlatformNotice type="error" title={datasets.error.message} action={<Button onClick={() => void datasets.refetch()}>重试</Button>} />}
    {datasets.data && !datasets.data.length && <Empty description="暂无能源数据表" />}
    {datasets.data && <Tabs destroyOnHidden items={DASHBOARD_GROUPS.map(group => {
      const members = datasets.data.filter(item => datasetGroup(item) === group.key)
      return { key: group.key, label: `${group.label}（${members.length}）`, children: <Space orientation="vertical" style={{ width: '100%' }}>
        <Typography.Paragraph type="secondary">{group.description} 各表选择字段查看趋势；占比柱图展示该字段在所选月份的每日贡献。</Typography.Paragraph>
        <div className={members.length === 1 ? styles.dashboardCharts : styles.trendGrid}>{members.map(dataset => <DatasetChart key={`${selected.year}-${selected.month}-${dataset.name}`} dataset={dataset} year={selected.year} month={selected.month} />)}</div>
      </Space> }
    })} />}
  </>
}
