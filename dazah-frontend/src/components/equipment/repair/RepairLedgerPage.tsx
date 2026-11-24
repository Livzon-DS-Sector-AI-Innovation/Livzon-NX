'use client'

// 设备检修：飞书维修记录表镜像的只读查询 + 维修频次排行。
// 记录按表内原文展示，不与设备台账关联；频次按「设备名称/型号」原文聚合。

import { useEffect, useState } from 'react'
import {
  Alert, App, Button, Descriptions, Empty, Input, Segmented, Select, Table, Tag, Tooltip,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CloudSyncOutlined, DownOutlined, RightOutlined, SearchOutlined, SettingOutlined, SyncOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  fetchRepairFrequency,
  fetchRepairRecords,
  fetchRepairResults,
  fetchRepairSyncStatus,
  triggerRepairSync,
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

const columns: ColumnsType<RepairRecord> = [
  { title: '维修日期', dataIndex: 'repaired_at', key: 'repaired_at', width: 112, render: (v: string | null) => v || '-' },
  { title: '设备名称/型号', dataIndex: 'equipment_text', key: 'equipment_text', width: 190, ellipsis: true, render: (v: string | null) => v || '-' },
  { title: '故障描述/原因', dataIndex: 'fault_desc', key: 'fault_desc', ellipsis: true, render: (v: string | null) => v || '-' },
  { title: '维修人员', dataIndex: 'person_text', key: 'person_text', width: 120, ellipsis: true, render: (v: string | null) => v || '-' },
  { title: '更换备件', dataIndex: 'spare_parts', key: 'spare_parts', width: 160, ellipsis: true, render: (v: string | null) => v || '-' },
  {
    title: '维修后状态', dataIndex: 'result', key: 'result', width: 104,
    render: (v: string | null) => (v ? <Tag color={resultColor(v)}>{v}</Tag> : '-'),
  },
]

// 行展开：主表列做了省略，这里放完整的地点、人员、备件与备注（每项占 1 格，各断点都对齐）
const expandedRowRender = (record: RepairRecord) => (
  <Descriptions
    size="small"
    column={{ xs: 1, sm: 2, lg: 4 }}
    items={[
      { key: 'place', label: '车间及地点', children: record.workshop_text || '-' },
      { key: 'person', label: '维修人员', children: record.person_text || '-' },
      { key: 'parts', label: '更换备件', children: record.spare_parts || '-' },
      { key: 'remark', label: '备注', children: record.remark || '-' },
    ]}
  />
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
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '4px 16px' }}>
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
              display: 'flex', alignItems: 'center', gap: 8, minWidth: 0,
              padding: '6px 10px', borderRadius: 8, cursor: 'pointer', textAlign: 'left',
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
                  最近 {item.last_repaired_at || '—'}
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
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [resultFilter, setResultFilter] = useState<string | undefined>()
  const [equipmentFilter, setEquipmentFilter] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [records, setRecords] = useState<RepairRecord[]>([])
  const [total, setTotal] = useState(0)
  const [loadedKey, setLoadedKey] = useState('')
  const [rankItems, setRankItems] = useState<RepairFrequencyItem[]>([])
  const [rankOpen, setRankOpen] = useState(true)
  const [resultOptions, setResultOptions] = useState<string[]>([])
  const [syncState, setSyncState] = useState<RepairSyncState | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [configOpen, setConfigOpen] = useState(false)
  // 手动同步后 +1，让三个数据 effect 重新拉取
  const [refreshKey, setRefreshKey] = useState(0)
  const dateFrom = rangeStart(range)
  // 列表加载态由「已加载的筛选条件」推导：筛选一变 key 就不同，即进入加载
  const listKey = JSON.stringify(
    [workshopCode, dateFrom, keyword, resultFilter, equipmentFilter, page, pageSize],
  )
  const loading = loadedKey !== listKey

  useEffect(() => {
    let cancelled = false
    fetchRepairRecords({
      workshop: workshopCode,
      date_from: dateFrom,
      keyword: keyword || undefined,
      result: resultFilter,
      equipment: equipmentFilter ?? undefined,
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
  }, [workshopCode, dateFrom, keyword, resultFilter, equipmentFilter, page, pageSize, listKey, refreshKey, message])

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
      fetchRepairSyncStatus(workshopCode).catch(() => null),
    ]).then(([results, status]) => {
      if (cancelled) return
      setResultOptions(results)
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <RepairLedgerConfigDrawer
        workshopCode={workshopCode}
        workshopLabel={workshopLabel}
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        onSaved={() => { void handleSync() }}
      />

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

      {/* 筛选 + 飞书同步 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <Segmented
          value={range}
          options={RANGES.map(({ value, label }) => ({ value, label }))}
          onChange={(value) => applyFilter(() => setRange(value as RangeValue))}
        />
        <Input
          placeholder="搜索设备、故障描述或维修人员"
          prefix={<SearchOutlined style={{ color: '#a4a097' }} />}
          style={{ width: 250 }}
          allowClear
          value={keywordInput}
          onChange={(e) => {
            setKeywordInput(e.target.value)
            if (!e.target.value) applyFilter(() => setKeyword(''))
          }}
          onPressEnter={() => applyFilter(() => setKeyword(keywordInput.trim()))}
        />
        <Select
          placeholder="维修后状态"
          allowClear
          showSearch
          optionFilterProp="label"
          style={{ width: 140 }}
          value={resultFilter}
          onChange={(value) => applyFilter(() => setResultFilter(value))}
          options={resultOptions.map((item) => ({ value: item, label: item }))}
        />
        {equipmentFilter && (
          <Tag
            color="purple"
            closable
            onClose={() => applyFilter(() => setEquipmentFilter(null))}
          >
            设备：{equipmentFilter}
          </Tag>
        )}
        <div style={{ flex: 1 }} />
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

      {/* 维修频次排行：哪台设备修得最多 */}
      <div style={{ background: C.surface, border: `1px solid ${C.hairline}`, borderRadius: 10, padding: '10px 16px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontWeight: 600, color: C.ink }}>维修频次</span>
          <span style={{ fontSize: 12, color: C.stone }}>
            按「设备名称/型号」统计维修次数；点击设备只看它的记录，再点一次取消
          </span>
          <div style={{ flex: 1 }} />
          <Button
            type="text" size="small"
            icon={rankOpen ? <DownOutlined /> : <RightOutlined />}
            onClick={() => setRankOpen((value) => !value)}
          >
            {rankOpen ? '收起' : '展开'}
          </Button>
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

      <Table
        columns={columns}
        dataSource={records}
        rowKey="id"
        size="small"
        loading={loading}
        expandable={{ expandedRowRender }}
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
  )
}
