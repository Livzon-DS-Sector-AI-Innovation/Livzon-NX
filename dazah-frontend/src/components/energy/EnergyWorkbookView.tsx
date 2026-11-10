import { useState } from 'react'
import { App, Button, Checkbox, DatePicker, Empty, Input, Pagination, Popover, Segmented } from 'antd'
import { CopyOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import type { WorkbookReport } from '@/lib/api/energy-ledger'
import { EnergyWorkbookGrid, type WorkbookEditing } from './EnergyWorkbookGrid'
import { needsWorkbookAttention, sortWorkbookRows, workbookClipboardText, type WorkbookSort } from './workbook-view'
import styles from './EnergyWorkbookGrid.module.css'

export function EnergyWorkbookView({ report, loading, editing }: { report: WorkbookReport; loading: boolean; editing?: WorkbookEditing }) {
  const { message } = App.useApp()
  const [search, setSearch] = useState('')
  const [customFields, setCustomFields] = useState<string[]>()
  const [onlyIssues, setOnlyIssues] = useState(false)
  const [range, setRange] = useState<[string, string]>()
  const [density, setDensity] = useState<'middle' | 'small'>('middle')
  const [sort, setSort] = useState<WorkbookSort>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [copying, setCopying] = useState(false)
  const matches = report.columns.filter(column => column.label.toLowerCase().includes(search.trim().toLowerCase()))
  const columns = customFields ? matches.filter(column => customFields.includes(column.key)) : matches
  const filteredRows = report.rows.filter(row => (!range || (row.date >= range[0] && row.date <= range[1])) && (!onlyIssues || columns.some(column => needsWorkbookAttention(row.cells[column.key]))))
  const sortedRows = sortWorkbookRows(filteredRows, sort && (sort.key === 'date' || columns.some(column => column.key === sort.key)) ? sort : undefined)
  const currentPage = Math.min(page, Math.max(1, Math.ceil(sortedRows.length / pageSize)))
  const rows = sortedRows.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  const view = { ...report, columns, rows }
  const viewKey = JSON.stringify([columns.map(column => column.key), rows.map(row => row.date)])
  function resetView() {
    setSearch(''); setCustomFields(undefined); setOnlyIssues(false); setRange(undefined); setSort(undefined); setPage(1); setPageSize(10); setDensity('middle')
  }
  async function copyPage() {
    setCopying(true)
    try {
      await navigator.clipboard.writeText(workbookClipboardText(rows, columns))
      void message.success(`已复制 ${rows.length} 行、${columns.length + 1} 列（含表头）`)
    } catch {
      void message.error('复制失败，请选中表格区域后按 Ctrl+C 复制')
    } finally { setCopying(false) }
  }
  return <>
    <div className={styles.viewToolbar}>
      <div className={styles.viewFilters}>
        <Input className={styles.fieldSearch} aria-label="搜索报表字段" prefix={<SearchOutlined />} placeholder="搜索车间 / 字段" allowClear value={search} onChange={event => { setSearch(event.target.value); setPage(1) }} />
        <DatePicker.RangePicker aria-label="筛选日期范围" placeholder={['开始日期', '结束日期']} defaultPickerValue={[dayjs(`${report.year}-${report.month}-01`), dayjs(`${report.year}-${report.month}-01`)]} value={range ? [dayjs(range[0]), dayjs(range[1])] : null} onChange={value => { setRange(value?.[0] && value[1] ? [value[0].format('YYYY-MM-DD'), value[1].format('YYYY-MM-DD')] : undefined); setPage(1) }} disabledDate={date => date.year() !== report.year || date.month() + 1 !== report.month} />
        <Checkbox checked={onlyIssues} onChange={event => { setOnlyIssues(event.target.checked); setPage(1) }}>仅看当前字段异常</Checkbox>
      </div>
      <div className={styles.viewActions}>
        <Popover trigger="click" placement="bottomRight" title="选择展示字段" content={<div className={styles.fieldPicker}>
          <div className={styles.fieldPickerActions}><Button size="small" onClick={() => { setCustomFields(report.columns.map(column => column.key)); setPage(1) }}>全选</Button><Button size="small" onClick={() => { setCustomFields(undefined); setPage(1) }}>显示全部</Button></div>
          <Checkbox.Group value={customFields ?? columns.map(column => column.key)} onChange={keys => { setCustomFields(keys.map(String)); setPage(1) }} options={report.columns.map(column => ({ value: column.key, label: column.label }))} />
        </div>}><Button aria-label={`显示字段 ${columns.length}/${report.columns.length}`} icon={<SettingOutlined />}>显示字段 {columns.length}/{report.columns.length}</Button></Popover>
        <Segmented aria-label="表格密度" value={density} onChange={value => setDensity(value === 'small' ? 'small' : 'middle')} options={[{ label: '舒适', value: 'middle' }, { label: '紧凑', value: 'small' }]} />
        <Button icon={<CopyOutlined />} disabled={!rows.length || !columns.length} loading={copying} onClick={() => void copyPage()}>复制本页</Button>
      </div>
    </div>
    <div className={styles.viewSummary}>
      <span>显示 {filteredRows.length} 个日期 · {columns.length} 个字段</span>
      <Button type="link" onClick={resetView}>重置视图</Button>
    </div>
    {!columns.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={search ? '没有匹配的字段' : '请选择展示字段'} /> : !rows.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选没有匹配的日期" /> : <EnergyWorkbookGrid key={viewKey} report={view} loading={loading} editing={editing} density={density} sort={sort} onSort={next => { setSort(next); setPage(1) }} />}
    <div className={styles.tableFooter}><span>共 {filteredRows.length} 个日期</span><Pagination size="small" current={currentPage} total={filteredRows.length} pageSize={pageSize} showSizeChanger pageSizeOptions={[10, 20, 31]} onChange={(next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size) }} /></div>
  </>
}
