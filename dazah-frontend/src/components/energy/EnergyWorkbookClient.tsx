'use client'

import { useCallback, useState, useSyncExternalStore } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Drawer, Dropdown, Skeleton, Space, Typography } from 'antd'
import { DownloadOutlined, UploadOutlined } from '@ant-design/icons'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { ledgerRequest, reportQuery, type WorkbookReport, type Meter } from '@/lib/api/energy-ledger'
import { useAuthStore } from '@/stores/auth'
import { EnergyWorkbookImport } from './EnergyWorkbookImport'
import { EnergyWorkbookView } from './EnergyWorkbookView'
import { EnergyWorkbookCellEditor } from './EnergyWorkbookCellEditor'
import styles from './EnergyWorkbookGrid.module.css'

const subscribeToHydration = () => () => {}

export function EnergyWorkbookClient({ year, month, dataset }: { year: number; month: number; dataset: string }) {
  const [importOpen, setImportOpen] = useState(false)
  const [active, setActive] = useState<{ date: string; key: string }[]>([])
  const closeEditor = useCallback((date: string, key: string) => setActive(current => current.filter(cell => cell.date !== date || cell.key !== key)), [])
  const canEdit = useAuthStore(state => state.hasPagePermission('energy:entry', 'query') && state.hasPagePermission('energy:entry', 'operate'))
  const canImport = useAuthStore(state => state.hasPagePermission('energy:settings', 'query') && state.hasPagePermission('energy:settings', 'operate'))
  const hydrated = useSyncExternalStore(subscribeToHydration, () => true, () => false)
  const editableDataset = ['饮用水码', '冰水码', '蒸汽码', '循环水码', '空气码', '电量'].includes(dataset)
  const fields = useQuery({ queryKey: ['energy-ledger', 'editable-fields'], queryFn: () => ledgerRequest<Meter[]>('/input-fields', { headers: { 'X-Dazah-Page-Path': '/energy/entry' } }), enabled: hydrated && canEdit && editableDataset })
  function field(key: string) {
    if (!editableDataset) return undefined
    const matches = fields.data?.filter(item => item.definition.enabled && item.definition.source_sheet === dataset && String(item.definition.source_column) === key)
    return matches?.length === 1 ? matches[0] : undefined
  }
  const query = reportQuery({ year, month, dataset })
  const report = useQuery({ queryKey: ['energy-ledger', 'workbook', query], queryFn: () => ledgerRequest<WorkbookReport>(`/reporting/workbook?${query}`) })
  return <>
    <div className={styles.reportHeader}>
      <div><Typography.Title level={4}>{dataset}</Typography.Title><div className={styles.reportMeta}>{year}年{month}月{report.data && <span>已取得 {report.data.available_count}/{report.data.expected_count} 项</span>}</div></div>
      <Space wrap>{hydrated && canImport && <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>导入 Excel</Button>}<Dropdown trigger={['click']} menu={{ items: [
        { key: 'current', label: <a href={`/api/v1/energy/reporting/workbook/export?${query}`}>导出当前数据表</a> },
        { key: 'all', label: <a href={`/api/v1/energy/reporting/workbook/export?${reportQuery({ year, month })}`}>导出全部21张数据表</a> },
      ] }}><Button icon={<DownloadOutlined />}>导出报表</Button></Dropdown></Space>
    </div>
    {report.error && <PlatformNotice type="error" title={report.error.message} action={<Button onClick={() => void report.refetch()}>重试</Button>} />}
    {report.data && !report.data.columns.length && <PlatformNotice title="该数据表暂无当前权限范围内的字段" description="请由能源管理员导入原表并核对字段与公式识别结果。" />}
    {report.isLoading && <Skeleton active paragraph={{ rows: 8 }} />}
    {editableDataset && canEdit && fields.error && <Space wrap><Typography.Text type="danger">无法加载可填写字段：{fields.error.message}</Typography.Text><Button onClick={() => void fields.refetch()}>重试</Button></Space>}
    {report.data && <EnergyWorkbookView key={query} report={report.data} loading={report.isFetching} editing={{
      canEdit: (date, key) => Boolean(hydrated && canEdit && field(key) && report.data?.columns.find(column => column.key === key)?.value_kind === 'reading' && ['complete', 'missing_reading', 'source_blank'].includes(report.data?.rows.find(row => row.date === date)?.cells[key]?.status ?? '')),
      start: (date, key) => setActive(current => current.some(cell => cell.date === date && cell.key === key) ? current : [...current, { date, key }]),
      render: (date, key) => {
        const target = field(key)
        return active.some(cell => cell.date === date && cell.key === key) && hydrated && canEdit && target ? <EnergyWorkbookCellEditor key={`${date}:${key}`} date={date} dataset={dataset} pointId={target.id} onClose={() => closeEditor(date, key)} /> : null
      },
    }} />}
    <Drawer title="导入能源 Excel" size={1000} open={canImport && importOpen} onClose={() => setImportOpen(false)} destroyOnHidden maskClosable={false}>
      {canImport && importOpen && <EnergyWorkbookImport year={year} />}
    </Drawer>
  </>
}
