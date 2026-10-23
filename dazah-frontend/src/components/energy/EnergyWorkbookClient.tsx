'use client'

import { useState, useSyncExternalStore } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Drawer, Space, Table, Tag, Typography } from 'antd'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { formatAmount, ledgerRequest, reportQuery, type WorkbookReport } from '@/lib/api/energy-ledger'
import { useAuthStore } from '@/stores/auth'
import { EnergyWorkbookImport } from './EnergyWorkbookImport'
import { reviewDetails } from './energy-review'

const subscribeToHydration = () => () => {}

export function EnergyWorkbookClient({ year, month, dataset }: { year: number; month: number; dataset: string }) {
  const [importOpen, setImportOpen] = useState(false)
  const canImport = useAuthStore(state => state.hasPagePermission('energy:settings', 'query') && state.hasPagePermission('energy:settings', 'operate'))
  const hydrated = useSyncExternalStore(subscribeToHydration, () => true, () => false)
  const query = reportQuery({ year, month, dataset })
  const report = useQuery({ queryKey: ['energy-ledger', 'workbook', query], queryFn: () => ledgerRequest<WorkbookReport>(`/reporting/workbook?${query}`) })
  return <>
    <Space wrap>{hydrated && canImport && <Button onClick={() => setImportOpen(true)}>导入 Excel</Button>}<Button href={`/api/v1/energy/reporting/workbook/export?${query}`}>导出当前数据表</Button><Button href={`/api/v1/energy/reporting/workbook/export?${reportQuery({ year, month })}`}>导出全部21张数据表</Button></Space>
    {report.error && <PlatformNotice type="error" title={report.error.message} action={<Button onClick={() => void report.refetch()}>重试</Button>} />}
    {report.data && <Typography.Text>{dataset} · {year}年{month}月 · 已取得 {report.data.available_count}/{report.data.expected_count} 项</Typography.Text>}
    {report.data && !report.data.columns.length && <PlatformNotice title="该数据表暂无当前权限范围内的字段" description="请由能源管理员导入原表并核对字段与公式识别结果。" />}
    <Table rowKey="date" loading={report.isFetching} dataSource={report.data?.rows} pagination={false} scroll={{ x: Math.max(800, (report.data?.columns.length ?? 0) * 190 + 120) }} columns={[
      { title: '日期', dataIndex: 'date', width: 120, fixed: 'left' },
      ...(report.data?.columns.map(column => ({ title: column.label, key: column.key, width: 190, render: (_: unknown, row: WorkbookReport['rows'][number]) => {
        const cell = row.cells[column.key]
        if (cell.status !== 'pending_review') return formatAmount(cell.value)
        const reviews = reviewDetails(cell.provenance)
        return <Space orientation="vertical" size={0}><Tag color="warning">待确认</Tag><Typography.Text>原表值：{reviews.map(review => formatAmount(review.reportedValue)).join('；') || '—'}</Typography.Text><Typography.Text>系统计算值：{formatAmount(cell.calculated_value)}</Typography.Text><Typography.Text type="secondary">{reviews.map(review => `${review.reason}；${review.source}`).join('；')}</Typography.Text></Space>
      } })) ?? []),
    ]} />
    <Drawer title="导入能源 Excel" size={1000} open={canImport && importOpen} onClose={() => setImportOpen(false)} destroyOnHidden maskClosable={false}>
      {canImport && importOpen && <EnergyWorkbookImport year={year} />}
    </Drawer>
  </>
}
