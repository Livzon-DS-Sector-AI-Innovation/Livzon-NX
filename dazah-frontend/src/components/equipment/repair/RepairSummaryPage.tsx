'use client'

// 设备检修汇总（跨车间）：领导视角一屏看全厂，可下钻到单个车间。
// 只读聚合；设备按「车间+设备名称原文」分组，不跨车间合并。

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Alert,
  App,
  Avatar,
  Button,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Popconfirm,
  Segmented,
  Select,
  Spin,
  Table,
  Tag,
  Tooltip,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DownloadOutlined,
  ReloadOutlined,
  SaveOutlined,
  SearchOutlined,
  UndoOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import {
  exportRepairRecords,
  fetchRepairFilterOptions,
  fetchRepairRecords,
  fetchRepairResults,
  fetchRepairSummary,
  fetchRepairSummarySettings,
  resetRepairSummarySettings,
  saveRepairSummarySettings,
  type RepairFilterOptions,
  type RepairRecord,
  type RepairSummary,
  type RepairSummaryRangeKey,
  type RepairSummarySettings,
  type RepairSummarySortField,
  type RepairSummaryWorkshop,
  type RepairWorkshopStatus,
} from '@/lib/api/repair-ledger'
import { useEquipmentWorkshops } from '@/lib/equipment-workshop-registry'
import ThemedEChart from '@/components/shared/ThemedEChart'

const C = {
  ink: 'var(--color-ink)',
  slate: 'var(--color-slate)',
  stone: 'var(--color-stone)',
  hairline: 'var(--color-hairline)',
  surface: 'var(--color-surface)',
  green: '#1aae39',
  orange: '#dd5b00',
  red: '#c0392b',
  blue: '#5b8ff9',
}

const RANGES = [
  { value: '30d', label: '近30天', start: () => dayjs().subtract(29, 'day'), end: () => null },
  { value: '90d', label: '近90天', start: () => dayjs().subtract(89, 'day'), end: () => null },
  { value: 'year', label: '今年', start: () => dayjs().startOf('year'), end: () => null },
  {
    value: 'last-year',
    label: '去年',
    start: () => dayjs().subtract(1, 'year').startOf('year'),
    end: () => dayjs().subtract(1, 'year').endOf('year'),
  },
  { value: 'all', label: '全部', start: () => null, end: () => null },
]

type RangeValue = RepairSummaryRangeKey

/** 车间对比排序字段；workshop 即注册表顺序（组织架构顺序） */
type WorkshopSortField = RepairSummarySortField

const WORKSHOP_SORT_OPTIONS: Array<{ value: WorkshopSortField; label: string }> = [
  { value: 'workshop', label: '车间顺序' },
  { value: 'repair_count', label: '维修次数' },
  { value: 'equipment_count', label: '设备数' },
  { value: 'abnormal_count', label: '异常/待处理' },
  { value: 'person_count', label: '维修人数' },
  { value: 'last_repaired_at', label: '最近维修' },
]

function defaultSortOrder(field: WorkshopSortField): 'ascend' | 'descend' {
  return field === 'workshop' ? 'ascend' : 'descend'
}

function rangeStart(value: RangeValue): string | undefined {
  return RANGES.find((item) => item.value === value)?.start()?.format('YYYY-MM-DD')
}

function rangeEnd(value: RangeValue): string | undefined {
  return RANGES.find((item) => item.value === value)?.end()?.format('YYYY-MM-DD')
}

function fmtDate(value: string | null | undefined): string {
  return value ? dayjs(value).format('MM-DD') : '—'
}

function fmtTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = dayjs(value)
  return d.isSame(dayjs(), 'day') ? d.format('HH:mm') : d.format('MM-DD HH:mm')
}

const STATUS_META: Record<RepairWorkshopStatus, { label: string; color: string }> = {
  normal: { label: '正常', color: 'green' },
  sync_failed: { label: '同步失败', color: 'red' },
  disabled: { label: '已停用', color: 'default' },
  not_configured: { label: '未接入', color: 'default' },
  no_records: { label: '无记录', color: 'default' },
}

function StatusTag({ status }: { status: RepairWorkshopStatus }) {
  const meta = STATUS_META[status] ?? STATUS_META.no_records
  return <Tag color={meta.color}>{meta.label}</Tag>
}

function PersonChips({ record }: { record: RepairRecord }) {
  const people = record.persons
  if (!people?.length) return <>{record.person_text || '—'}</>
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

function KpiCard({
  title,
  value,
  extra,
}: {
  title: string
  value: string | number
  extra?: string
}) {
  return (
    <div
      style={{
        background: C.surface,
        border: `1px solid ${C.hairline}`,
        borderRadius: 10,
        padding: '12px 14px',
        minWidth: 0,
      }}
    >
      <div style={{ fontSize: 12, color: C.stone }}>{title}</div>
      <div style={{ fontSize: 24, fontWeight: 600, color: C.ink, lineHeight: 1.4 }}>
        {value}
      </div>
      <div style={{ fontSize: 12, color: C.slate, minHeight: 18 }}>{extra || ''}</div>
    </div>
  )
}

function RankRow({
  index,
  title,
  subtitle,
  subtitleTooltip,
  value,
  onClick,
}: {
  index: number
  title: string
  subtitle?: string
  subtitleTooltip?: string
  value: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        width: '100%',
        border: 'none',
        background: 'transparent',
        padding: '6px 2px',
        textAlign: 'left',
        cursor: 'pointer',
        borderBottom: `1px solid ${C.hairline}`,
      }}
    >
      <span
        style={{
          width: 20,
          fontWeight: 600,
          color: index < 3 ? C.orange : C.stone,
          flexShrink: 0,
        }}
      >
        {index + 1}
      </span>
      <span style={{ minWidth: 0, flex: 1 }}>
        <span
          style={{
            display: 'block',
            color: C.ink,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {title}
        </span>
        {subtitle && (
          <Tooltip title={subtitleTooltip} placement="topLeft">
            <span style={{ display: 'block', fontSize: 12, color: C.stone }}>
              {subtitle}
            </span>
          </Tooltip>
        )}
      </span>
      <span style={{ color: C.slate, flexShrink: 0 }}>{value}</span>
    </button>
  )
}

function SectionCard({
  title,
  extra,
  children,
}: {
  title: string
  extra?: ReactNode
  children: ReactNode
}) {
  return (
    <div
      style={{
        background: C.surface,
        border: `1px solid ${C.hairline}`,
        borderRadius: 10,
        padding: '10px 12px 12px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ fontWeight: 600, color: C.ink }}>{title}</span>
        <div style={{ flex: 1 }} />
        {extra}
      </div>
      {children}
    </div>
  )
}

function ActiveFilterTag({
  label,
  onClear,
}: {
  label: string
  onClear: () => void
}) {
  return (
    <Tag
      closable
      color="blue"
      onClose={(event) => {
        event.preventDefault()
        onClear()
      }}
    >
      已筛选：{label}
    </Tag>
  )
}

export function RepairSummaryPage() {
  const { message } = App.useApp()
  const workshops = useEquipmentWorkshops()

  const [range, setRange] = useState<RangeValue>('30d')
  const [customRange, setCustomRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [workshopFilter, setWorkshopFilter] = useState<string[]>([])
  const [personFilter, setPersonFilter] = useState<string | undefined>()
  const [faultFilter, setFaultFilter] = useState<string | undefined>()
  const [equipmentFilter, setEquipmentFilter] = useState<string | undefined>()
  const [resultFilter, setResultFilter] = useState<string | undefined>()
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [drillWorkshop, setDrillWorkshop] = useState<string | null>(null)
  const [detail, setDetail] = useState<RepairRecord | null>(null)
  const [summary, setSummary] = useState<RepairSummary | null>(null)
  const [loadedSummaryKey, setLoadedSummaryKey] = useState('')
  const [records, setRecords] = useState<RepairRecord[]>([])
  const [recordTotal, setRecordTotal] = useState(0)
  const [loadedRecordsKey, setLoadedRecordsKey] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [options, setOptions] = useState<RepairFilterOptions>({
    persons: [],
    faults: [],
    equipments: [],
  })
  const [results, setResults] = useState<string[]>([])
  const [exporting, setExporting] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [sortField, setSortField] = useState<WorkshopSortField>('workshop')
  const [sortOrder, setSortOrder] = useState<'ascend' | 'descend'>('ascend')
  const [showUnconfigured, setShowUnconfigured] = useState(false)
  const [summarySettings, setSummarySettings] =
    useState<RepairSummarySettings | null>(null)
  const [settingsReady, setSettingsReady] = useState(false)
  const [savingSettings, setSavingSettings] = useState(false)

  const dateFrom = customRange?.[0]
    ? customRange[0].format('YYYY-MM-DD')
    : rangeStart(range)
  const dateTo = customRange?.[1]
    ? customRange[1].format('YYYY-MM-DD')
    : rangeEnd(range)
  const effectiveWorkshops = drillWorkshop
    ? [drillWorkshop]
    : workshopFilter.length
      ? workshopFilter
      : undefined
  const workshopsKey = effectiveWorkshops?.join(',') ?? ''
  // 加载态由「已加载的筛选条件」推导，避免在 effect 里同步 setState
  const summaryKey = JSON.stringify([
    dateFrom,
    dateTo,
    workshopsKey,
    keyword,
    equipmentFilter ?? null,
    personFilter ?? null,
    faultFilter ?? null,
    resultFilter ?? null,
    refreshKey,
  ])
  const loading = loadedSummaryKey !== summaryKey
  const recordsKey = JSON.stringify([summaryKey, page, pageSize])
  const recordsLoading = loadedRecordsKey !== recordsKey

  // 先加载全厂默认设置，再按设置初始化筛选/排序，避免用默认值先请求一次
  useEffect(() => {
    let cancelled = false
    fetchRepairSummarySettings()
      .then((settings) => {
        if (cancelled) return
        setSummarySettings(settings)
        setSortField(settings.sort_field)
        setSortOrder(settings.sort_order)
        setRange(settings.range_key)
        setWorkshopFilter(settings.workshops ?? [])
      })
      .catch(() => {
        // 读取失败时按系统默认展示，不阻塞页面
      })
      .finally(() => {
        if (!cancelled) setSettingsReady(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!settingsReady) return
    let cancelled = false
    fetchRepairSummary({
      date_from: dateFrom,
      date_to: dateTo,
      workshops: workshopsKey ? workshopsKey.split(',') : undefined,
      keyword: keyword || undefined,
      equipment: equipmentFilter,
      person: personFilter,
      fault: faultFilter,
      result: resultFilter,
      top_limit: 10,
    })
      .then((data) => {
        if (!cancelled) {
          setSummary(data)
          setLoadedSummaryKey(summaryKey)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          message.error((error as Error).message || '检修汇总加载失败')
          setSummary(null)
          setLoadedSummaryKey(summaryKey)
        }
      })
    return () => {
      cancelled = true
    }
  }, [
    summaryKey,
    settingsReady,
    dateFrom,
    dateTo,
    workshopsKey,
    keyword,
    equipmentFilter,
    personFilter,
    faultFilter,
    resultFilter,
    refreshKey,
    message,
  ])

  useEffect(() => {
    if (!settingsReady) return
    let cancelled = false
    fetchRepairRecords({
      workshops: workshopsKey ? workshopsKey.split(',') : undefined,
      date_from: dateFrom,
      date_to: dateTo,
      keyword: keyword || undefined,
      equipment: equipmentFilter,
      person: personFilter,
      fault: faultFilter,
      result: resultFilter,
      page,
      page_size: pageSize,
    })
      .then((res) => {
        if (!cancelled) {
          setRecords(res.items)
          setRecordTotal(res.total)
          setLoadedRecordsKey(recordsKey)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          message.error((error as Error).message || '检修明细加载失败')
          setRecords([])
          setRecordTotal(0)
          setLoadedRecordsKey(recordsKey)
        }
      })
    return () => {
      cancelled = true
    }
  }, [
    recordsKey,
    summaryKey,
    settingsReady,
    dateFrom,
    dateTo,
    workshopsKey,
    keyword,
    equipmentFilter,
    personFilter,
    faultFilter,
    resultFilter,
    page,
    pageSize,
    refreshKey,
    message,
  ])

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchRepairFilterOptions(), fetchRepairResults()])
      .then(([opts, statuses]) => {
        if (!cancelled) {
          setOptions(opts)
          setResults(statuses)
        }
      })
      .catch(() => {
        // 下拉选项失败不阻塞汇总主体
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  const workshopName = (code: string) =>
    summary?.workshops.find((item) => item.workshop_code === code)?.workshop_name
    ?? workshops.find((item) => item.code === code)?.name
    ?? code

  const workshopOptions = useMemo(() => {
    if (summary?.workshops.length) {
      return summary.workshops.map((item) => ({
        value: item.workshop_code,
        label: item.workshop_name,
      }))
    }
    return workshops.map((item) => ({ value: item.code, label: item.name }))
  }, [summary, workshops])

  const applyFilter = (fn: () => void) => {
    fn()
    setPage(1)
  }

  const resetAll = () => {
    setRange('30d')
    setCustomRange(null)
    setWorkshopFilter([])
    setPersonFilter(undefined)
    setFaultFilter(undefined)
    setEquipmentFilter(undefined)
    setResultFilter(undefined)
    setKeyword('')
    setKeywordInput('')
    setDrillWorkshop(null)
    setPage(1)
  }

  const handleExport = async () => {
    if (exporting) return
    setExporting(true)
    try {
      await exportRepairRecords({
        workshops: effectiveWorkshops,
        date_from: dateFrom,
        date_to: dateTo,
        keyword: keyword || undefined,
        equipment: equipmentFilter,
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

  const handleSaveSettings = async () => {
    if (customRange) {
      message.warning('自定义日期为临时查询，请选择预设时间范围后再保存')
      return
    }
    setSavingSettings(true)
    try {
      const settings = await saveRepairSummarySettings({
        sort_field: sortField,
        sort_order: sortOrder,
        range_key: range,
        workshops: workshopFilter.length ? workshopFilter : null,
      })
      setSummarySettings(settings)
      message.success('已保存为全厂默认设置')
    } catch (error) {
      message.error((error as Error).message || '保存默认设置失败')
    } finally {
      setSavingSettings(false)
    }
  }

  const handleResetSettings = async () => {
    setSavingSettings(true)
    try {
      const settings = await resetRepairSummarySettings()
      setSummarySettings(settings)
      setSortField(settings.sort_field)
      setSortOrder(settings.sort_order)
      setRange(settings.range_key)
      setWorkshopFilter(settings.workshops ?? [])
      setCustomRange(null)
      message.success('已恢复系统默认设置')
    } catch (error) {
      message.error((error as Error).message || '恢复默认设置失败')
    } finally {
      setSavingSettings(false)
    }
  }

  const kpi = summary?.kpi
  const configuredCount =
    summary?.workshops.filter((item) => item.configured).length ?? 0
  const notConfigured =
    summary?.workshops.filter((item) => item.status === 'not_configured') ?? []
  const syncFailed =
    summary?.workshops.filter((item) => item.status === 'sync_failed') ?? []
  const maxCount = Math.max(
    1,
    ...(summary?.workshops.map((item) => item.repair_count) ?? [1]),
  )

  // 注册表顺序（组织架构顺序）：默认排序、以及所有排序的次级键
  const workshopOrder = useMemo(() => {
    const index = new Map<string, number>()
    workshops.forEach((item, position) => index.set(item.code, position))
    return index
  }, [workshops])

  const sortedWorkshops = useMemo(() => {
    const rows = [...(summary?.workshops ?? [])]
    const orderOf = (code: string) =>
      workshopOrder.get(code) ?? Number.MAX_SAFE_INTEGER
    const numeric = (row: RepairSummaryWorkshop) => {
      switch (sortField) {
        case 'repair_count':
          return row.repair_count
        case 'equipment_count':
          return row.equipment_count
        case 'abnormal_count':
          return row.abnormal_count
        case 'person_count':
          return row.person_count
        default:
          return 0
      }
    }
    rows.sort((a, b) => {
      let primary = 0
      if (sortField === 'workshop') {
        primary = orderOf(a.workshop_code) - orderOf(b.workshop_code)
      } else if (sortField === 'last_repaired_at') {
        primary = (a.last_repaired_at ?? '').localeCompare(
          b.last_repaired_at ?? '',
        )
      } else {
        primary = numeric(a) - numeric(b)
      }
      if (primary !== 0) {
        return sortOrder === 'ascend' ? primary : -primary
      }
      // 并列时始终按注册表顺序，不随升/降序翻转
      return orderOf(a.workshop_code) - orderOf(b.workshop_code)
    })
    return rows
  }, [summary, sortField, sortOrder, workshopOrder])

  const configuredWorkshops = sortedWorkshops.filter(
    (item) => item.status !== 'not_configured',
  )
  const unconfiguredWorkshops = sortedWorkshops.filter(
    (item) => item.status === 'not_configured',
  )

  const applySort = (field: WorkshopSortField) => {
    setSortField(field)
    setSortOrder(defaultSortOrder(field))
  }

  const handleTableSort = (field: WorkshopSortField, order?: 'ascend' | 'descend' | null) => {
    setSortField(field)
    if (!order) {
      // antd 的第三态是“取消排序”；这里改为翻转方向，保持两态循环
      setSortOrder((current) => (current === 'ascend' ? 'descend' : 'ascend'))
      return
    }
    setSortOrder(order)
  }

  const workshopColumns: ColumnsType<RepairSummaryWorkshop> = [
    {
      title: '车间',
      key: 'workshop',
      dataIndex: 'workshop_name',
      width: 160,
      sorter: true,
      sortOrder: sortField === 'workshop' ? sortOrder : null,
      sortDirections: ['ascend', 'descend', 'ascend'],
      render: (_: unknown, row) => (
        <div>
          <div style={{ fontWeight: 600, color: C.ink }}>{row.workshop_name}</div>
          <div style={{ fontSize: 12, color: C.stone }}>{row.workshop_code}</div>
        </div>
      ),
    },
    {
      title: '维修次数',
      key: 'repair_count',
      dataIndex: 'repair_count',
      width: 190,
      sorter: true,
      sortOrder: sortField === 'repair_count' ? sortOrder : null,
      sortDirections: ['descend', 'ascend', 'descend'],
      render: (value: number, row) =>
        row.status === 'not_configured' ? (
          <span style={{ color: C.stone }}>—</span>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 42, textAlign: 'right', color: C.ink }}>{value}</span>
            <div
              style={{
                flex: 1,
                height: 6,
                borderRadius: 3,
                background: C.hairline,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  width: `${Math.round((value / maxCount) * 100)}%`,
                  height: '100%',
                  background: C.blue,
                  borderRadius: 3,
                }}
              />
            </div>
          </div>
        ),
    },
    {
      title: '占比',
      dataIndex: 'repair_count',
      key: 'share',
      width: 70,
      render: (value: number, row) =>
        row.status === 'not_configured' || !kpi?.total_count
          ? '—'
          : `${Math.round((value / kpi.total_count) * 100)}%`,
    },
    {
      title: '设备数',
      key: 'equipment_count',
      dataIndex: 'equipment_count',
      width: 80,
      sorter: true,
      sortOrder: sortField === 'equipment_count' ? sortOrder : null,
      sortDirections: ['descend', 'ascend', 'descend'],
      render: (value: number, row) =>
        row.status === 'not_configured' ? '—' : value,
    },
    {
      title: '异常',
      key: 'abnormal_count',
      dataIndex: 'abnormal_count',
      width: 74,
      sorter: true,
      sortOrder: sortField === 'abnormal_count' ? sortOrder : null,
      sortDirections: ['descend', 'ascend', 'descend'],
      render: (value: number, row) => {
        if (row.status === 'not_configured') return '—'
        return value ? (
          <Tag color="orange">{value}</Tag>
        ) : (
          <span style={{ color: C.stone }}>0</span>
        )
      },
    },
    {
      title: '人数',
      key: 'person_count',
      dataIndex: 'person_count',
      width: 70,
      sorter: true,
      sortOrder: sortField === 'person_count' ? sortOrder : null,
      sortDirections: ['descend', 'ascend', 'descend'],
      render: (value: number, row) =>
        row.status === 'not_configured' ? '—' : value,
    },
    {
      title: '最近维修',
      key: 'last_repaired_at',
      dataIndex: 'last_repaired_at',
      width: 96,
      sorter: true,
      sortOrder: sortField === 'last_repaired_at' ? sortOrder : null,
      sortDirections: ['descend', 'ascend', 'descend'],
      render: (value: string | null) => fmtDate(value),
    },
    {
      title: '最近同步',
      dataIndex: 'last_synced_at',
      width: 112,
      render: (value: string | null) => fmtTime(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: RepairWorkshopStatus) => <StatusTag status={value} />,
    },
    {
      title: '操作',
      key: 'op',
      width: 84,
      render: (_: unknown, row) =>
        row.status === 'not_configured' ? (
          <a href={`/equipment?workshop=${row.workshop_code}&module=maintenance`}>
            去配置
          </a>
        ) : (
          <a onClick={() => setDrillWorkshop(row.workshop_code)}>查看</a>
        ),
    },
  ]

  const recordColumns: ColumnsType<RepairRecord> = [
    {
      title: '维修日期',
      dataIndex: 'repaired_at',
      width: 96,
      render: (value: string | null) => fmtDate(value),
    },
    {
      title: '车间',
      dataIndex: 'workshop_code',
      width: 110,
      render: (value: string) => workshopName(value),
    },
    {
      title: '设备名称/型号',
      dataIndex: 'equipment_text',
      ellipsis: true,
      render: (value: string | null) => value || '—',
    },
    {
      title: '故障描述/原因',
      dataIndex: 'fault_desc',
      ellipsis: true,
      render: (value: string | null) => value || '—',
    },
    {
      title: '维修人员',
      dataIndex: 'person_text',
      width: 220,
      render: (_: unknown, row) => <PersonChips record={row} />,
    },
    {
      title: '更换备件',
      dataIndex: 'spare_parts',
      ellipsis: true,
      render: (value: string | null) => value || '—',
    },
    {
      title: '维修后状态',
      dataIndex: 'result',
      width: 104,
      render: (value: string | null) => {
        if (!value) return '—'
        const color = /停|报废|无法|未修复|未恢复/.test(value)
          ? 'red'
          : /待|观察|跟进|跟踪/.test(value)
            ? 'orange'
            : /正常|修复|完好|运行/.test(value)
              ? 'green'
              : 'default'
        return <Tag color={color}>{value}</Tag>
      },
    },
    {
      title: '详情',
      key: 'detail',
      width: 70,
      render: (_: unknown, row) => <a onClick={() => setDetail(row)}>查看</a>,
    },
  ]

  const trendOption = useMemo(() => {
    const points = summary?.trend ?? []
    if (!points.length) return null
    const periods = [...new Set(points.map((item) => item.period))]
    const seriesMap = new Map<string, string>()
    for (const item of points) {
      seriesMap.set(item.workshop_code, item.workshop_name)
    }
    const monthly = summary?.trend_granularity === 'month'
    // 周：显示区间（周一~周日）；月：显示年月
    const periodLabel = (period: string) => {
      if (monthly) {
        return `${period.slice(0, 4)}年${Number(period.slice(5, 7))}月`
      }
      const start = dayjs(period)
      return `${start.format('MM-DD')}~${start.add(6, 'day').format('MM-DD')}`
    }
    return {
      tooltip: { trigger: 'axis' },
      legend: { top: 0, type: 'scroll' },
      grid: { left: 44, right: 16, top: 40, bottom: 28 },
      xAxis: { type: 'category', data: periods.map(periodLabel) },
      yAxis: { type: 'value', name: '次数' },
      series: [...seriesMap.entries()].map(([code, name]) => ({
        name,
        type: 'bar',
        stack: 'total',
        emphasis: { focus: 'series' },
        data: periods.map(
          (period) =>
            points.find(
              (item) => item.period === period && item.workshop_code === code,
            )?.count ?? 0,
        ),
      })),
    }
  }, [summary])

  const drilledName = drillWorkshop ? workshopName(drillWorkshop) : null

  return (
    <div className="flex flex-col gap-3">
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, color: C.ink }}>检修汇总</h2>
          <div style={{ fontSize: 12, color: C.stone }}>
            全厂 {kpi?.total_workshops ?? workshops.length} 个车间 · 已接入{' '}
            {configuredCount} 个 · 本期 {kpi?.total_count ?? 0} 次维修
            {summarySettings?.updated_at && (
              <>
                {' '}· 默认设置：{summarySettings.updated_by_name ?? '系统'} 于{' '}
                {dayjs(summarySettings.updated_at).format('MM-DD HH:mm')} 修改
              </>
            )}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        {summarySettings?.can_edit && (
          <>
            <Button
              icon={<SaveOutlined />}
              loading={savingSettings}
              onClick={() => {
                void handleSaveSettings()
              }}
            >
              保存为默认
            </Button>
            <Popconfirm
              title="恢复系统默认设置？"
              description="排序、时间范围、车间筛选将恢复系统默认，影响所有用户。"
              okText="恢复"
              cancelText="取消"
              onConfirm={() => {
                void handleResetSettings()
              }}
            >
              <Button icon={<UndoOutlined />} loading={savingSettings}>
                恢复默认
              </Button>
            </Popconfirm>
          </>
        )}
        <Button
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={() => setRefreshKey((value) => value + 1)}
        >
          刷新
        </Button>
        <Button
          type="primary"
          icon={<DownloadOutlined />}
          loading={exporting}
          disabled={!recordTotal}
          onClick={() => {
            void handleExport()
          }}
        >
          导出
        </Button>
      </div>

      {drillWorkshop && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <a onClick={() => setDrillWorkshop(null)}>全厂</a>
          <span style={{ color: C.stone }}>›</span>
          <strong style={{ color: C.ink }}>{drilledName}</strong>
          <Button size="small" type="link" onClick={() => setDrillWorkshop(null)}>
            返回全厂
          </Button>
          <Button
            size="small"
            type="link"
            href={`/equipment?workshop=${drillWorkshop}&module=maintenance`}
          >
            打开车间检修页
          </Button>
        </div>
      )}

      {notConfigured.length > 0 && (
        <Alert
          type="warning"
          showIcon
          title={`${notConfigured.length} 个车间未接入检修表，未计入汇总`}
          description="展开下方「未接入车间」查看并配置。"
        />
      )}
      {syncFailed.length > 0 && (
        <Alert
          type="error"
          showIcon
          title={`${syncFailed.length} 个车间同步失败`}
          description={syncFailed.map((item) => item.workshop_name).join('、')}
        />
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: C.stone }}>统计时间</span>
        <Segmented
          value={customRange ? undefined : range}
          options={RANGES.map(({ value, label }) => ({ value, label }))}
          onChange={(value) =>
            applyFilter(() => {
              setRange(value as RangeValue)
              setCustomRange(null)
            })
          }
        />
        <DatePicker.RangePicker
          size="small"
          style={{ width: 210 }}
          allowEmpty={[true, true]}
          value={customRange ?? undefined}
          onChange={(values) => applyFilter(() => setCustomRange(values ?? null))}
        />
        {!drillWorkshop && (
          <Select
            mode="multiple"
            allowClear
            size="small"
            style={{ minWidth: 180 }}
            placeholder="全部车间"
            maxTagCount="responsive"
            value={workshopFilter}
            options={workshopOptions}
            onChange={(values) => applyFilter(() => setWorkshopFilter(values))}
          />
        )}
        <Select
          allowClear
          showSearch
          size="small"
          style={{ width: 130 }}
          placeholder="维修人员"
          value={personFilter}
          options={options.persons.map((name) => ({ value: name, label: name }))}
          onChange={(value) => applyFilter(() => setPersonFilter(value))}
        />
        <Select
          allowClear
          showSearch
          size="small"
          style={{ width: 150 }}
          placeholder="故障描述"
          value={faultFilter}
          options={options.faults.map((item) => ({ value: item, label: item }))}
          onChange={(value) => applyFilter(() => setFaultFilter(value))}
        />
        <Select
          allowClear
          showSearch
          size="small"
          style={{ width: 150 }}
          placeholder="设备名称"
          value={equipmentFilter}
          options={options.equipments.map((item) => ({ value: item, label: item }))}
          onChange={(value) => applyFilter(() => setEquipmentFilter(value))}
        />
        <Select
          allowClear
          size="small"
          style={{ width: 130 }}
          placeholder="维修后状态"
          value={resultFilter}
          options={results.map((item) => ({ value: item, label: item }))}
          onChange={(value) => applyFilter(() => setResultFilter(value))}
        />
        <Input
          size="small"
          allowClear
          style={{ width: 180 }}
          prefix={<SearchOutlined />}
          placeholder="搜索设备、故障、人员"
          value={keywordInput}
          onChange={(event) => {
            setKeywordInput(event.target.value)
            if (!event.target.value) applyFilter(() => setKeyword(''))
          }}
          onPressEnter={() => applyFilter(() => setKeyword(keywordInput.trim()))}
        />
        <Button size="small" type="link" onClick={resetAll}>
          重置
        </Button>
      </div>

      <Spin spinning={loading}>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <KpiCard
            title="维修次数"
            value={kpi?.total_count ?? 0}
            extra={
              kpi?.change_rate == null
                ? undefined
                : `环比 ${kpi.change_rate > 0 ? '+' : ''}${kpi.change_rate}%`
            }
          />
          <KpiCard title="涉及设备" value={kpi?.equipment_count ?? 0} />
          <KpiCard
            title="有数据车间"
            value={`${kpi?.workshop_count ?? 0} / ${kpi?.total_workshops ?? 0}`}
          />
          <KpiCard title="维修人数" value={kpi?.person_count ?? 0} />
          <KpiCard
            title="异常/待处理"
            value={kpi?.abnormal_count ?? 0}
            extra={
              kpi?.total_count
                ? `占 ${Math.round((kpi.abnormal_count / kpi.total_count) * 100)}%`
                : undefined
            }
          />
          <KpiCard
            title="日均次数"
            value={kpi?.daily_average ?? 0}
            extra="按统计天数折算"
          />
        </div>
      </Spin>

      {!drillWorkshop && (
        <SectionCard
          title="车间对比"
          extra={(
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 12, color: C.stone }}>排序</span>
              <Select
                size="small"
                style={{ width: 118 }}
                value={sortField}
                options={WORKSHOP_SORT_OPTIONS}
                onChange={(value) => applySort(value as WorkshopSortField)}
              />
              <Tooltip
                title={
                  sortOrder === 'ascend'
                    ? '当前升序，点击切为降序'
                    : '当前降序，点击切为升序'
                }
              >
                <Button
                  size="small"
                  icon={
                    sortOrder === 'ascend'
                      ? <ArrowUpOutlined />
                      : <ArrowDownOutlined />
                  }
                  onClick={() =>
                    setSortOrder((value) =>
                      value === 'ascend' ? 'descend' : 'ascend',
                    )
                  }
                />
              </Tooltip>
            </div>
          )}
        >
          <Table
            size="small"
            rowKey="workshop_code"
            columns={workshopColumns}
            dataSource={configuredWorkshops}
            pagination={false}
            loading={loading}
            scroll={{ x: 1080 }}
            onChange={(_pagination, _filters, sorter) => {
              const info = Array.isArray(sorter) ? sorter[0] : sorter
              const field = String(info?.columnKey ?? info?.field ?? '')
              const mapped: WorkshopSortField | null =
                field === 'workshop' || field === 'workshop_name'
                  ? 'workshop'
                  : field === 'repair_count'
                    ? 'repair_count'
                    : field === 'equipment_count'
                      ? 'equipment_count'
                      : field === 'abnormal_count'
                        ? 'abnormal_count'
                        : field === 'person_count'
                          ? 'person_count'
                          : field === 'last_repaired_at'
                            ? 'last_repaired_at'
                            : null
              if (mapped) handleTableSort(mapped, info.order)
            }}
            onRow={(row) => ({
              onClick: () => {
                setDrillWorkshop(row.workshop_code)
                setPage(1)
              },
              style: { cursor: 'pointer' },
            })}
          />

          {unconfiguredWorkshops.length > 0 && (
            <div
              style={{
                marginTop: 8,
                borderTop: `1px solid ${C.hairline}`,
                paddingTop: 4,
              }}
            >
              <Button
                type="text"
                size="small"
                onClick={() => setShowUnconfigured((value) => !value)}
              >
                {showUnconfigured ? '收起' : '展开'} 未接入车间（
                {unconfiguredWorkshops.length}）
              </Button>
              {showUnconfigured && (
                <Table
                  size="small"
                  rowKey="workshop_code"
                  pagination={false}
                  dataSource={unconfiguredWorkshops}
                  columns={[
                    {
                      title: '车间',
                      dataIndex: 'workshop_name',
                      render: (_: unknown, row) => (
                        <div>
                          <div style={{ fontWeight: 600, color: C.ink }}>
                            {row.workshop_name}
                          </div>
                          <div style={{ fontSize: 12, color: C.stone }}>
                            {row.workshop_code}
                          </div>
                        </div>
                      ),
                    },
                    {
                      title: '状态',
                      dataIndex: 'status',
                      width: 110,
                      render: () => <StatusTag status="not_configured" />,
                    },
                    {
                      title: '操作',
                      key: 'op',
                      width: 90,
                      render: (_: unknown, row) => (
                        <a
                          href={`/equipment?workshop=${row.workshop_code}&module=maintenance`}
                        >
                          去配置
                        </a>
                      ),
                    },
                  ]}
                />
              )}
            </div>
          )}
        </SectionCard>
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <SectionCard
          title={drillWorkshop ? `${drilledName} · 高频设备` : '高频设备 TOP10'}
          extra={
            equipmentFilter ? (
              <ActiveFilterTag
                label={equipmentFilter}
                onClear={() => applyFilter(() => setEquipmentFilter(undefined))}
              />
            ) : (
              <span style={{ fontSize: 12, color: C.stone }}>点击筛明细</span>
            )
          }
        >
          {summary?.top_equipment.length ? (
            summary.top_equipment.map((item, index) => (
              <RankRow
                key={`${item.workshop_code}-${item.equipment_text}`}
                index={index}
                title={item.equipment_text}
                subtitle={`${item.workshop_name} · 最近 ${fmtDate(item.last_repaired_at)}`}
                value={`${item.times} 次`}
                onClick={() =>
                  applyFilter(() => {
                    setDrillWorkshop(null)
                    setEquipmentFilter((current) =>
                      current === item.equipment_text ? undefined : item.equipment_text,
                    )
                  })
                }
              />
            ))
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
          )}
        </SectionCard>

        <SectionCard
          title={drillWorkshop ? `${drilledName} · 高频故障` : '高频故障 TOP10'}
          extra={
            faultFilter ? (
              <ActiveFilterTag
                label={faultFilter}
                onClear={() => applyFilter(() => setFaultFilter(undefined))}
              />
            ) : (
              <span style={{ fontSize: 12, color: C.stone }}>点击筛明细</span>
            )
          }
        >
          {summary?.top_faults.length ? (
            summary.top_faults.map((item, index) => (
              <RankRow
                key={item.fault_desc}
                index={index}
                title={item.fault_desc}
                subtitle={[
                  `涉及 ${item.equipment_count} 台设备`,
                  !drillWorkshop && item.workshops?.length
                    ? `${item.workshops
                        .slice(0, 2)
                        .map((workshop) => workshop.workshop_name)
                        .join('、')}${
                        item.workshops.length > 2
                          ? ` 等 ${item.workshops.length} 个车间`
                          : ''
                      }`
                    : '',
                ]
                  .filter(Boolean)
                  .join(' · ')}
                subtitleTooltip={
                  !drillWorkshop && item.workshops?.length
                    ? `最近 ${fmtDate(item.last_repaired_at)} · ${item.workshops
                        .map(
                          (workshop) =>
                            `${workshop.workshop_name} ${workshop.times} 次`,
                        )
                        .join('、')}`
                    : undefined
                }
                value={`${item.times} 次`}
                onClick={() =>
                  applyFilter(() => {
                    setDrillWorkshop(null)
                    setFaultFilter((current) =>
                      current === item.fault_desc ? undefined : item.fault_desc,
                    )
                  })
                }
              />
            ))
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
          )}
        </SectionCard>

        <SectionCard
          title={drillWorkshop ? `${drilledName} · 人员工作量` : '人员工作量 TOP10'}
          extra={
            personFilter ? (
              <ActiveFilterTag
                label={personFilter}
                onClear={() => applyFilter(() => setPersonFilter(undefined))}
              />
            ) : (
              <span style={{ fontSize: 12, color: C.stone }}>点击筛明细</span>
            )
          }
        >
          {summary?.top_persons.length ? (
            summary.top_persons.map((item, index) => (
              <RankRow
                key={item.name}
                index={index}
                title={item.name}
                subtitle={[
                  !drillWorkshop && item.workshops?.length
                    ? `${item.workshops
                        .slice(0, 2)
                        .map((workshop) => workshop.workshop_name)
                        .join('、')}${
                        item.workshops.length > 2
                          ? ` 等 ${item.workshops.length} 个车间`
                          : ''
                      }`
                    : '',
                  `最近 ${fmtDate(item.last_repaired_at)}`,
                ]
                  .filter(Boolean)
                  .join(' · ')}
                subtitleTooltip={
                  !drillWorkshop && item.workshops?.length
                    ? `最近 ${fmtDate(item.last_repaired_at)} · ${item.workshops
                        .map(
                          (workshop) =>
                            `${workshop.workshop_name} ${workshop.times} 次`,
                        )
                        .join('、')}`
                    : undefined
                }
                value={`${item.times} 次`}
                onClick={() =>
                  applyFilter(() => {
                    setDrillWorkshop(null)
                    setPersonFilter((current) =>
                      current === item.name ? undefined : item.name,
                    )
                  })
                }
              />
            ))
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="维修趋势"
        extra={
          <span style={{ fontSize: 12, color: C.stone }}>
            {summary?.trend_granularity === 'month'
              ? '按月'
              : '按周（周一为起点）'} · 按车间堆叠
          </span>
        }
      >
        {trendOption ? (
          <ThemedEChart option={trendOption} style={{ height: 260 }} />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无趋势数据" />
        )}
      </SectionCard>

      <SectionCard
        title="维修明细"
        extra={
          <span style={{ fontSize: 12, color: C.stone }}>
            共 {recordTotal} 条 · 当前筛选
          </span>
        }
      >
        <Table
          size="small"
          rowKey="id"
          columns={recordColumns}
          dataSource={records}
          loading={recordsLoading}
          scroll={{ x: 1120 }}
          pagination={{
            current: page,
            pageSize,
            total: recordTotal,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage)
              setPageSize(nextPageSize)
            },
          }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="所选范围内没有检修记录"
              />
            ),
          }}
        />
      </SectionCard>

      <Drawer
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        size={420}
        title="检修记录详情"
      >
        {detail && (
          <Descriptions
            column={1}
            size="small"
            bordered
            items={[
              { key: 'date', label: '维修日期', children: fmtDate(detail.repaired_at) },
              {
                key: 'workshop',
                label: '车间',
                children: workshopName(detail.workshop_code),
              },
              {
                key: 'place',
                label: '车间及地点',
                children: detail.workshop_text || '—',
              },
              {
                key: 'equipment',
                label: '设备名称/型号',
                children: detail.equipment_text || '—',
              },
              {
                key: 'fault',
                label: '故障描述/原因',
                children: detail.fault_desc || '—',
              },
              {
                key: 'persons',
                label: '维修人员',
                children: <PersonChips record={detail} />,
              },
              {
                key: 'parts',
                label: '更换备件',
                children: detail.spare_parts || '—',
              },
              {
                key: 'result',
                label: '维修后状态',
                children: detail.result || '—',
              },
              { key: 'remark', label: '备注', children: detail.remark || '—' },
            ]}
          />
        )}
      </Drawer>
    </div>
  )
}
