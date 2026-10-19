'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Drawer, Space, Table, Tag, Typography } from 'antd'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { EnergyEvidence } from './EnergyEvidence'
import { formatAmount, ledgerRequest, QUALITY_LABELS, reportQuery, type Revision, type UsageRow, type WorkbookCell, type WorkbookReport } from '@/lib/api/energy-ledger'

export function EnergyWorkbookClient({ year, month, dataset }: { year: number; month: number; dataset: string }) {
  const query = reportQuery({ year, month, dataset })
  const report = useQuery({ queryKey: ['energy-ledger', 'workbook', query], queryFn: () => ledgerRequest<WorkbookReport>(`/reporting/workbook?${query}`) })
  const [selected, setSelected] = useState<{ label: string; date: string; cell: WorkbookCell }>()
  const trace = useQuery({ queryKey: ['energy-ledger', 'trace', selected?.cell.trace_id], queryFn: () => ledgerRequest<UsageRow>(`/reporting/trace/${selected?.cell.trace_id}`), enabled: Boolean(selected?.cell.trace_id) })
  const history = useQuery({ queryKey: ['energy-ledger', 'reading-history', selected?.cell.reading_id], queryFn: () => ledgerRequest<Revision[]>(`/ledger-history/reading/${selected?.cell.reading_id}`), enabled: Boolean(selected?.cell.reading_id) })
  return <>
    <Space wrap><Button href={`/api/v1/energy/reporting/workbook/export?${query}`}>导出当前数据表</Button><Button href={`/api/v1/energy/reporting/workbook/export?${reportQuery({ year, month })}`}>导出全部21张数据表</Button></Space>
    <PlatformNotice title="按原表逐日查看；表码保留累计读数，用量使用正式计算结果" description="数据表保留原始指标顺序，取消的大罐数量不再展示。空缺、真实零值、不适用和待确认配置分别标识。累计读数、父子表及比例不直接累加；全部21张数据表导出不会将公式结果作为原始输入。" />
    {report.error && <PlatformNotice type="error" title={report.error.message} action={<Button onClick={() => void report.refetch()}>重试</Button>} />}
    {report.data && <Typography.Text>{dataset} · {year}年{month}月 · 已取得 {report.data.available_count}/{report.data.expected_count} 项</Typography.Text>}
    {report.data && !report.data.columns.length && <PlatformNotice title="该数据表暂无当前权限范围内的指标配置" description="请由能源管理员导入原表并核对计量点、计算关系及归属部门。" />}
    <Table rowKey="date" loading={report.isFetching} dataSource={report.data?.rows} pagination={false} scroll={{ x: Math.max(800, (report.data?.columns.length ?? 0) * 190 + 120) }} columns={[
      { title: '日期', dataIndex: 'date', width: 120, fixed: 'left' },
      ...(report.data?.columns.map(column => ({ title: <span>{column.label}<br /><Typography.Text type="secondary">{column.value_kind === 'reading' ? '原始读数' : '计算结果'} · {column.unit}</Typography.Text></span>, key: column.key, width: 190, render: (_: unknown, row: WorkbookReport['rows'][number]) => {
        const cell = row.cells[column.key]
        return <Space orientation="vertical" size={2}>{cell.trace_id || cell.reading_id ? <Button type="link" onClick={() => setSelected({ label: column.label, date: row.date, cell })}>{formatAmount(cell.value)}</Button> : <span>{formatAmount(cell.value)}</span>}{cell.status !== 'complete' && <Tag>{QUALITY_LABELS[cell.status] || cell.status}</Tag>}</Space>
      } })) ?? []),
    ]} />
    <Drawer title="原表数据依据" open={Boolean(selected)} onClose={() => setSelected(undefined)} size={600}>
      {selected && <><Typography.Title level={4}>{selected.label} · {selected.date}</Typography.Title><p>值 {formatAmount(selected.cell.value)}；状态 {QUALITY_LABELS[selected.cell.status] || selected.cell.status}</p><p>来源 {String(selected.cell.provenance?.source ?? '自动计算')}；记录版本 {String(selected.cell.provenance?.version ?? selected.cell.provenance?.configuration_version ?? '—')}</p></>}
      {(trace.error || history.error) && <PlatformNotice type="error" title={trace.error?.message || history.error?.message} />}
      {trace.data && <EnergyEvidence value={trace.data.provenance} />}
      {history.data && <Table rowKey="id" dataSource={history.data} pagination={false} columns={[{ title: '版本', dataIndex: 'version' }, { title: '值', render: (_, row) => String(row.payload.value ?? '—') }, { title: '更正原因', dataIndex: 'reason' }, { title: '时间', dataIndex: 'created_at' }]} />}
    </Drawer>
  </>
}
