'use client'

// 设备检修：飞书维修记录表镜像的只读查询 + 维修频次排行。
// 记录按表内原文展示，不与设备台账关联；频次按「设备名称/型号」原文聚合。

import { useEffect, useState, type Key } from 'react'
import {
  Alert, App, Avatar, Button, DatePicker, Descriptions, Empty, Input, Segmented, Select, Table, Tag, Tooltip,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CloudSyncOutlined, DownOutlined, DownloadOutlined, RightOutlined, SearchOutlined, SettingOutlined, SyncOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import {
  exportRepairRecords,
  fetchRepairFilterOptions,
  fetchRepairFrequency,
  fetchRepairRecords,
  fetchRepairResults,
  fetchRepairSyncStatus,
  triggerRepairSync,
  type RepairFilterOptions,
  type RepairFrequencyItem,
  type RepairRecord,
  type RepairSyncState,
} from '@/lib/api/repair-ledger'
import { RepairLedgerConfigDrawer } from './RepairLedgerConfigDrawer'

const C = {
  ink: 'var(--color-ink)', slate: 'var(--color-slate)', stone: 'var(--color-stone)',
  hairline: 'var(--color-hairline)', surface: 'var(--color-surface)',
  green: '#1aae39', orange: '#dd5b00', red: '#c0392b',
}

// 统计时间范围 → 维修日期起点（含当天）
const RANGES = [
  { value: '30d', label: '近30天', start: () => dayjs().subtract(29, 'day') },
  { value: '90d', label: '近90天', start: () => dayjs().subtract(89, 'day') },
  { value: 'year', label: '今年', start: () => dayjs().startOf('year') },
  { value: 'all', label: '全部', start: () => null },
]

type RangeValue = (typeof RANGES)[number]['value']

function rangeStart(value: RangeValue): string | undefined {
  return RANGES.find((item) => item.value === value)?.start()?.format('YYYY-MM-DD')
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = dayjs(iso)
  return d.isSame(dayjs(), 'day') ? d.format('HH:mm') : d.format('MM-DD HH:mm')
}

// 维修后状态是飞书单选原文：停机类红、待处理类橙、恢复类绿，其余中性
function resultColor(value: string): string {
  if (/停|报废|无法|未修复|未恢复/.test(value)) return 'red'
  if (/待|观察|跟进|跟踪/.test(value)) return 'orange'
  if (/正常|修复|完好|运行/.test(value)) return 'green'
  return 'default'
}

// 维修人员：通讯录解析成功时显示头像+姓名小圆片（无头像显示姓氏首字），
// 未解析时回退表内原文
function PersonCell({ record }: { record: RepairRecord }) {
  const people = record.persons
  if (!people?.length) return <>{record.person_text || '-'}</>
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
      {people.map((person, index) => (
        <Tooltip key={person.open_id ?? `${person.name}-${index}`} title={person.name}>
          <span className="inline-flex items-center gap-1">
            {person.avatar_url ? (
              <Avatar size={20} src={person.avatar_url} />
            ) : (
              <Avatar size={20} style={{ background: '#8b93e8', fontSize: 12 }}>
                {(person.name || '?').slice(0, 1)}
              </Avatar>
            )}
            <span>{person.name || '未知成员'}</span>
          </span>
        </Tooltip>
      ))}
    </span>
  )
}

// 表头样式：默认灰字偏淡，加深加粗让字段名一眼可辨
const headerCell = () => ({ style: { fontWeight: 600, color: C.ink } })

const columns: ColumnsType<RepairRecord> = [
  { title: '维修日期', dataIndex: 'repaired_at', key: 'repaired_at', width: 112, onHeaderCell: headerCell, render: (v: string | null) => v || '-' },
  // 四个内容列不设固定宽度：平分剩余空间（1600px 屏各约 265px，
  // 足够一行放下 2 个三字名 + 2 个两字名的头像小圆片）
  { title: '设备名称/型号', dataIndex: 'equipment_text', key: 'equipment_text', onHeaderCell: headerCell, ellipsis: true, render: (v: string | null) => v || '-' },
  { title: '故障描述/原因', dataIndex: 'fault_desc', key: 'fault_desc', ellipsis: true, onHeaderCell: headerCell, render: (v: string | null) => v || '-' },
  {
    title: '维修人员', dataIndex: 'person_text', key: 'person_text', onHeaderCell: headerCell,
    render: (_: string | null, record: RepairRecord) => <PersonCell record={record} />,
  },
  { title: '更换备件', dataIndex: 'spare_parts', key: 'spare_parts', onHeaderCell: headerCell, ellipsis: true, render: (v: string | null) => v || '-' },
  {
    title: '维修后状态', dataIndex: 'result', key: 'result', width: 104, onHeaderCell: headerCell,
    render: (v: string | null) => (v ? <Tag color={resultColor(v)}>{v}</Tag> : '-'),
  },
]

// 行展开（卡片式，由末列「详情」触发）：主表列做了省略，
// 这里放完整的地点、人员、备件与备注（每项占 1 格，各断点都对齐）
const expandedRowRender = (record: RepairRecord) => (
  <div
    data-testid="repair-detail-card"
    style={{
      background: C.surface,
      border: `1px solid ${C.hairline}`,
      borderRadius: 10,
      padding: '10px 16px',
    }}
  >
    <Descriptions
      size="small"
      column={{ xs: 1, sm: 2, lg: 4 }}
      styles={{
        label: { color: C.ink, fontWeight: 600, fontSize: 13 },
        content: { fontSize: 13 },
      }}
      items={[
        { key: 'place', label: '车间及地点', children: record.workshop_text || '-' },
        { key: 'person', label: '维修人员', children: <PersonCell record={record} /> },
        { key: 'parts', label: '更换备件', children: record.spare_parts || '-' },
        { key: 'remark', label: '备注', children: record.remark || '-' },
      ]}
    />
  </div>
)

// ── 维修频次排行 ───────────────────────────────────────────────────

function FrequencyRank({
  items, active, onSelect,
}: {
  items: RepairFrequencyItem[]
  active: string | null
  onSelect: (equipment: string) => void
}) {
  if (items.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="所选时间范围内没有检修记录"
        style={{ margin: '8px 0' }}
      />
    )
  }
  const max = Math.max(1, ...items.map((item) => item.times))
  return (
    // 竖排榜单：左栏窄列里一行一项
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {items.map((item, index) => {
        const isActive = active === item.equipment_text
        const hot = index < 3
        return (
          <button
            key={item.equipment_text}
            type="button"
            title={`${item.equipment_text}：${item.times} 次`}
            onClick={() => onSelect(item.equipment_text)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, width: '100%', minWidth: 0,
              padding: '6px 8px', borderRadius: 8, cursor: 'pointer', textAlign: 'left',
              fontFamily: 'inherit', fontSize: 13, color: C.ink,
              background: isActive ? 'var(--color-primary-soft)' : 'transparent',
              border: isActive ? '1px solid var(--color-primary-border)' : '1px solid transparent',
            }}
          >
            <span style={{ width: 18, flexShrink: 0, textAlign: 'center', fontWeight: 600, color: hot ? C.orange : C.stone }}>
              {index + 1}
            </span>
            <span style={{ flex: 1, minWidth: 0 }}>
              <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {item.equipment_text}
                </span>
                <span style={{ flexShrink: 0, fontWeight: 600 }}>
                  {item.times}
                  <span style={{ fontSize: 12, fontWeight: 400, color: C.slate }}>次</span>
                </span>
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ flex: 1, height: 6, borderRadius: 3, background: 'var(--color-hairline-soft)', overflow: 'hidden' }}>
                  <span
                    style={{
                      display: 'block', height: '100%', borderRadius: 3,
                      width: `${(item.times / max) * 100}%`,
                      background: hot ? C.orange : 'var(--color-primary)',
                    }}
                  />
                </span>
                <span style={{ flexShrink: 0, fontSize: 12, color: C.stone }}>
                  {item.last_repaired_at || '—'}
                </span>
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )
}

// ── 页面 ─────────────────────────────────────────────────────────

export function RepairLedgerPage({
  workshopCode, workshopLabel,
}: {
  workshopCode: string
  workshopLabel: string
}) {
  const { message } = App.useApp()
  const [range, setRange] = useState<RangeValue>('30d')
  // 自定义日期范围：设定后优先于预设时段（近30天等），清空即回落
  const [customRange, setCustomRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [resultFilter, setResultFilter] = useState<string | undefined>()
  const [equipmentFilter, setEquipmentFilter] = useState<string | null>(null)
  const [personFilter, setPersonFilter] = useState<string | undefined>()
  const [faultFilter, setFaultFilter] = useState<string | undefined>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [records, setRecords] = useState<RepairRecord[]>([])
  const [total, setTotal] = useState(0)
  const [loadedKey, setLoadedKey] = useState('')
  const [rankItems, setRankItems] = useState<RepairFrequencyItem[]>([])
  const [rankOpen, setRankOpen] = useState(true)
  const [resultOptions, setResultOptions] = useState<string[]>([])
  const [filterOptions, setFilterOptions] = useState<RepairFilterOptions>({ persons: [], faults: [], equipments: [] })
  const [syncState, setSyncState] = useState<RepairSyncState | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [configOpen, setConfigOpen] = useState(false)
  // 「详情」列展开的行（卡片式展开，替代默认的 + 号）
  const [expandedKeys, setExpandedKeys] = useState<readonly Key[]>([])
  // 手动同步后 +1，让三个数据 effect 重新拉取
  const [refreshKey, setRefreshKey] = useState(0)
  const dateFrom = customRange?.[0]
    ? customRange[0].format('YYYY-MM-DD')
    : rangeStart(range)
  const dateTo = customRange?.[1] ? customRange[1].format('YYYY-MM-DD') : undefined
  // 列表加载态由「已加载的筛选条件」推导：筛选一变 key 就不同，即进入加载
  const listKey = JSON.stringify(
    [workshopCode, dateFrom, dateTo, keyword, resultFilter, equipmentFilter, personFilter, faultFilter, page, pageSize],
  )
  const loading = loadedKey !== listKey

  useEffect(() => {
    let cancelled = false
    fetchRepairRecords({
      workshop: workshopCode,
      date_from: dateFrom,
      date_to: dateTo,
      keyword: keyword || undefined,
      result: resultFilter,
      equipment: equipmentFilter ?? undefined,
      person: personFilter,
      fault: faultFilter,
      page,
      page_size: pageSize,
    })
      .then((res) => {
        if (cancelled) return
        setRecords(res.items)
        setTotal(res.total)
        setLoadedKey(listKey)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        message.error((error as Error).message || '检修记录加载失败')
        setRecords([])
        setTotal(0)
        setLoadedKey(listKey)
      })
    return () => { cancelled = true }
  }, [workshopCode, dateFrom, dateTo, keyword, resultFilter, equipmentFilter, personFilter, faultFilter, page, pageSize, listKey, refreshKey, message])

  useEffect(() => {
    let cancelled = false
    fetchRepairFrequency(workshopCode, dateFrom)
      .then((items) => {
        if (!cancelled) setRankItems(items)
      })
      .catch(() => {
        // 频次榜加载失败不阻塞记录列表
      })
    return () => { cancelled = true }
  }, [workshopCode, dateFrom, refreshKey])

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetchRepairResults(workshopCode).catch(() => [] as string[]),
      fetchRepairFilterOptions(workshopCode).catch(() => null),
      fetchRepairSyncStatus(workshopCode).catch(() => null),
    ]).then(([results, options, status]) => {
      if (cancelled) return
      setResultOptions(results)
      if (options) setFilterOptions(options)
      setSyncState(status)
    })
    return () => { cancelled = true }
  }, [workshopCode, refreshKey])

  // 筛选条件变化后回到第一页
  const applyFilter = (apply: () => void) => {
    apply()
    setPage(1)
  }

  const reload = () => setRefreshKey((value) => value + 1)

  const handleSync = async () => {
    setSyncing(true)
    try {
      const result = (await triggerRepairSync(workshopCode))[workshopCode]
      if (!result) {
        message.warning('本车间未启用检修表同步')
      } else if (result.error) {
        message.error(result.error)
      } else {
        message.success(`飞书同步完成，共 ${result.total ?? 0} 条检修记录`)
      }
      reload()
    } catch (error) {
      message.error((error as Error).message || '同步失败')
    } finally {
      setSyncing(false)
    }
  }

  const notConfigured = Boolean(syncState && !syncState.enabled)
  const syncFailed = syncState?.last_status === 'failed'

  // 导出当前筛选命中的全部记录（与列表同一套筛选条件）
  const handleExport = async () => {
    if (exporting) return
    setExporting(true)
    try {
      await exportRepairRecords({
        workshop: workshopCode,
        date_from: dateFrom,
        date_to: dateTo,
        keyword: keyword || undefined,
        equipment: equipmentFilter ?? undefined,
        person: personFilter,
        fault: faultFilter,
        result: resultFilter,
      })
      message.success('Excel 已开始下载')
    } catch (error) {
      message.error((error as Error).message || '导出失败')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <RepairLedgerConfigDrawer
        workshopCode={workshopCode}
        workshopLabel={workshopLabel}
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        onSaved={() => { void handleSync() }}
      />

      {/* 左右分栏：左侧同步状态 + 频次榜单，右侧筛选 + 记录表（窄屏自动叠回单栏） */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start">
        {/* 左栏：同步状态在频次榜单上方 */}
        <aside className="flex w-full shrink-0 flex-col gap-3 lg:w-64">
          {/* 同步状态 + 飞书同步 / 配置 */}
          <div
            style={{
              background: C.surface,
              border: `1px solid ${C.hairline}`,
              borderRadius: 10,
              padding: '10px 12px',
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: C.slate }}>
              {notConfigured ? (
                <span style={{ color: C.stone }}>未连接检修表</span>
              ) : (
                <>
                  <CloudSyncOutlined style={{ color: syncFailed ? C.red : C.green }} />
                  {syncState?.last_run_at ? `最近同步 ${fmtTime(syncState.last_run_at)}` : '尚未同步'}
                  {syncFailed && (
                    <Tooltip title={syncState?.last_message || '同步失败'}>
                      <span style={{ color: C.red, cursor: 'help', borderBottom: `1px dotted ${C.red}` }}>
                        同步失败
                      </span>
                    </Tooltip>
                  )}
                </>
              )}
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button
                size="small"
                icon={<SyncOutlined spin={syncing} />}
                loading={syncing}
                onClick={() => { void handleSync() }}
              >
                飞书同步
              </Button>
              <Button size="small" icon={<SettingOutlined />} onClick={() => setConfigOpen(true)}>
                配置
              </Button>
            </div>
          </div>

          {/* 维修频次竖排榜单 */}
          <div
            style={{ background: C.surface, border: `1px solid ${C.hairline}`, borderRadius: 10, padding: '10px 12px 12px' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ fontWeight: 600, color: C.ink }}>维修频次</span>
              <div style={{ flex: 1 }} />
              <Button
                type="text" size="small"
                icon={rankOpen ? <DownOutlined /> : <RightOutlined />}
                onClick={() => setRankOpen((value) => !value)}
              >
                {rankOpen ? '收起' : '展开'}
              </Button>
            </div>
            <div style={{ fontSize: 12, color: C.stone, margin: '2px 0 6px' }}>
              点击设备只看它的记录，再点一次取消
            </div>
            {rankOpen && (
              <FrequencyRank
                items={rankItems}
                active={equipmentFilter}
                onSelect={(equipment) => applyFilter(() => setEquipmentFilter(
                  equipmentFilter === equipment ? null : equipment,
                ))}
              />
            )}
          </div>
        </aside>

        {/* 右栏：未配置提示 + 筛选行 + 记录表 */}
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          {notConfigured && (
            <Alert
              type="info"
              showIcon
              title="本车间尚未连接检修表"
              description="车间在飞书多维表格登记维修记录后，把表格链接配置到这里，平台会自动同步并统计各设备的维修频次。"
              action={(
                <Button size="small" type="primary" onClick={() => setConfigOpen(true)}>
                  去配置
                </Button>
              )}
            />
          )}

          {/* 筛选：始终单行，搜索框在最后弹性占满剩余宽度 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'nowrap', minWidth: 0 }}>
            <Segmented
              value={customRange ? undefined : range}
              options={RANGES.map(({ value, label }) => ({ value, label }))}
              onChange={(value) => applyFilter(() => {
                setRange(value as RangeValue)
                setCustomRange(null)
              })}
            />
            <DatePicker.RangePicker
              size="small"
              style={{ width: 210, flexShrink: 0 }}
              allowEmpty={[true, true]}
              value={customRange ?? undefined}
              onChange={(values) => applyFilter(() => setCustomRange(values ?? null))}
            />
            <Select
              placeholder="维修人员"
              allowClear
              showSearch
              optionFilterProp="label"
              style={{ width: 104, flexShrink: 0 }}
              value={personFilter}
              onChange={(value) => applyFilter(() => setPersonFilter(value))}
              options={filterOptions.persons.map((item) => ({ value: item, label: item }))}
            />
            <Select
              placeholder="故障描述"
              allowClear
              showSearch
              optionFilterProp="label"
              style={{ width: 116, flexShrink: 0 }}
              value={faultFilter}
              onChange={(value) => applyFilter(() => setFaultFilter(value))}
              options={filterOptions.faults.map((item) => ({ value: item, label: item }))}
            />
            <Select
              placeholder="设备名称"
              allowClear
              showSearch
              optionFilterProp="label"
              style={{ width: 116, flexShrink: 0 }}
              value={equipmentFilter ?? undefined}
              onChange={(value) => applyFilter(() => setEquipmentFilter(value ?? null))}
              options={filterOptions.equipments.map((item) => ({ value: item, label: item }))}
            />
            <Select
              placeholder="维修后状态"
              allowClear
              showSearch
              optionFilterProp="label"
              style={{ width: 104, flexShrink: 0 }}
              value={resultFilter}
              onChange={(value) => applyFilter(() => setResultFilter(value))}
              options={resultOptions.map((item) => ({ value: item, label: item }))}
            />
            <Input
              placeholder="搜索设备、故障、人员"
              prefix={<SearchOutlined style={{ color: '#a4a097' }} />}
              style={{ flex: '1 1 96px', minWidth: 96 }}
              allowClear
              value={keywordInput}
              onChange={(e) => {
                setKeywordInput(e.target.value)
                if (!e.target.value) applyFilter(() => setKeyword(''))
              }}
              onPressEnter={() => applyFilter(() => setKeyword(keywordInput.trim()))}
            />
            <Button
              size="small"
              icon={<DownloadOutlined />}
              loading={exporting}
              onClick={() => { void handleExport() }}
            >
              导出
            </Button>
          </div>

          {/* 记录表：与左栏卡片同款的圆角容器 */}
          <div
            style={{
              background: C.surface,
              border: `1px solid ${C.hairline}`,
              borderRadius: 10,
              padding: '8px 12px 12px',
            }}
          >
            <Table
              columns={[
                ...columns,
                {
                  title: '详情', key: 'detail', width: 76, onHeaderCell: headerCell,
                  render: (_: unknown, record: RepairRecord) => {
                    const open = expandedKeys.includes(record.id)
                    return (
                      <span
                        role="button"
                        style={{ color: 'var(--color-primary)', cursor: 'pointer', fontWeight: open ? 600 : 400 }}
                        onClick={() => {
                          setExpandedKeys((keys) =>
                            keys.includes(record.id)
                              ? keys.filter((key) => key !== record.id)
                              : [...keys, record.id],
                          )
                        }}
                      >
                        {open ? '收起' : '详情'}
                      </span>
                    )
                  },
                },
              ]}
              dataSource={records}
              rowKey="id"
              size="small"
              loading={loading}
              expandable={{
                expandedRowRender,
                expandedRowKeys: expandedKeys,
                showExpandColumn: false,
              }}
              locale={{ emptyText: notConfigured ? '尚未连接检修表' : '所选范围内没有检修记录' }}
              pagination={{
                current: page,
                pageSize,
                total,
                showSizeChanger: true,
                showTotal: (count) => `共 ${count} 条`,
                onChange: (nextPage, nextSize) => {
                  setPage(nextPage)
                  if (nextSize !== pageSize) setPageSize(nextSize)
                },
              }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
