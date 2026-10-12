'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  App, Button, Card, Checkbox, DatePicker, Input, Progress, Table, Tabs, Tag, Tooltip,
} from 'antd'
import {
  CheckSquareOutlined, CloudSyncOutlined, HistoryOutlined, SettingOutlined, SyncOutlined, TabletOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import {
  fetchInspectionFeishuDevices,
  fetchInspectionFeishuRecords,
  fetchInspectionFeishuSyncStatus,
  fetchInspectionFeishuTodaySummary,
  triggerInspectionFeishuSync,
} from '@/lib/api/inspection-feishu'
import type {
  InspectionFeishuDevice,
  InspectionFeishuRecord,
  InspectionFeishuSyncStatus,
  InspectionFeishuTodaySummary,
} from '@/types/inspection-feishu'
import { InspectionFeishuConfigDrawer } from './InspectionFeishuConfigDrawer'

const C = {
  ink: '#1a1a1a', slate: '#5d5b54', stone: '#a4a097',
  hairline: '#e5e3df', surface: '#f6f5f4', canvas: '#ffffff',
  green: '#1aae39', red: '#c0392b', purple: '#5645d4',
}

const AM_KEYS = ['am_clean', 'am_lubrication', 'am_fastening', 'am_sealing', 'am_vibration', 'am_sound', 'am_surface'] as const
const PM_KEYS = ['pm_clean', 'pm_lubrication', 'pm_fastening', 'pm_sealing', 'pm_vibration', 'pm_sound', 'pm_surface'] as const
const ITEM_LABELS = ['清洁', '润滑', '紧固', '密封', '无震动', '无异声', '外表面']

function CheckCell({ value }: { value: string | null }) {
  if (value === '√') return <span style={{ color: C.green, fontWeight: 600 }}>√</span>
  if (value === '×') return <span style={{ color: C.red, fontWeight: 700 }}>×</span>
  return <span style={{ color: '#c9c5bd' }}>—</span>
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  return dayjs(iso).format('MM-DD HH:mm')
}

// ── 同步状态栏 ─────────────────────────────────────────────────────

function SyncBar({
  status, syncing, onSync, onOpenConfig,
}: {
  status: InspectionFeishuSyncStatus | null
  syncing: boolean
  onSync: () => void
  onOpenConfig: () => void
}) {
  const newest = status?.tables
    ?.map((t) => t.last_run_at)
    .filter(Boolean)
    .sort()
    .at(-1)
  const failed = status?.tables?.some((t) => t.last_status === 'failed')
  const totalRows = status?.tables?.reduce((sum, t) => sum + (t.total_rows || 0), 0) || 0

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 13, color: C.slate }}>
      {status && !status.enabled ? (
        <span style={{ color: C.red }}>飞书镜像同步未配置（缺少应用凭据或表格 ID）</span>
      ) : (
        <>
          <CloudSyncOutlined style={{ color: failed ? C.red : C.green }} />
          <span>
            最近同步 {fmtTime(newest)}
            {failed ? <span style={{ color: C.red, marginLeft: 6 }}>同步失败</span> : ' ✓'}
            {status ? ` · 镜像 ${totalRows} 行` : ''}
          </span>
          {failed && (
            <Tooltip title={status?.tables?.filter((t) => t.last_status === 'failed').map((t) => `${t.table_key}: ${t.last_message}`).join('；')}>
              <span style={{ color: C.red, cursor: 'help', borderBottom: `1px dotted ${C.red}` }}>查看原因</span>
            </Tooltip>
          )}
        </>
      )}
      <Button
        size="small" icon={<SyncOutlined spin={syncing} />}
        onClick={onSync} loading={syncing}
      >
        飞书同步
      </Button>
      <Button
        size="small" icon={<SettingOutlined />}
        onClick={onOpenConfig}
      >
        配置
      </Button>
    </div>
  )
}

// ── 巡检记录表（今日/历史共用） ───────────────────────────────────

function recordColumns(opts: { showStatus: boolean }): ColumnsType<InspectionFeishuRecord> {
  const base: ColumnsType<InspectionFeishuRecord> = [
    { title: '日期', dataIndex: 'record_date', width: 95, render: (d: string | null) => d || '-' },
    { title: '设备名称', dataIndex: 'equipment_name', width: 140, ellipsis: true, render: (v: string | null) => v || '-' },
    { title: '设备编号', dataIndex: 'equipment_no', width: 125, render: (v: string | null) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v || '-'}</span> },
  ]
  const am = AM_KEYS.map((key, i) => ({
    title: ITEM_LABELS[i],
    dataIndex: key,
    width: 52,
    align: 'center' as const,
    render: (v: string | null) => <CheckCell value={v} />,
  }))
  const pm = PM_KEYS.map((key, i) => ({
    title: ITEM_LABELS[i],
    dataIndex: key,
    width: 52,
    align: 'center' as const,
    render: (v: string | null) => <CheckCell value={v} />,
  }))
  const tail: ColumnsType<InspectionFeishuRecord> = [
    {
      title: '异常情况', dataIndex: 'anomaly_note', width: 180, ellipsis: true,
      render: (v: string | null, record) =>
        record.has_abnormal
          ? <span style={{ color: C.red }}>{v || '（含异常项，未填写描述）'}</span>
          : (v || '-'),
    },
  ]
  if (opts.showStatus) {
    tail.unshift({
      title: '处理状态', dataIndex: 'process_status', width: 90,
      render: (v: string | null) => v || '-',
    })
  }
  // 分组表头：上午 / 下午
  const columns: ColumnsType<InspectionFeishuRecord> = [
    ...base,
    { title: '上午', children: am as ColumnsType<InspectionFeishuRecord> },
    { title: '下午', children: pm as ColumnsType<InspectionFeishuRecord> },
    ...tail,
  ]
  return columns
}

function RecordsTable({
  source, defaultDays, showStatus,
}: { source?: 'today' | 'history'; defaultDays: number | null; showStatus: boolean }) {
  const { message } = App.useApp()
  const [items, setItems] = useState<InspectionFeishuRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(
    defaultDays ? [dayjs().subtract(defaultDays - 1, 'day'), dayjs()] : null,
  )
  const [abnormalOnly, setAbnormalOnly] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await fetchInspectionFeishuRecords({
        source,
        date_from: range?.[0]?.format('YYYY-MM-DD'),
        date_to: range?.[1]?.format('YYYY-MM-DD'),
        keyword: keyword || undefined,
        abnormal_only: abnormalOnly,
        page,
        page_size: pageSize,
      })
      setItems(result.items)
      setTotal(result.total)
    } catch (error) {
      message.error((error as Error).message || '加载巡检记录失败')
    } finally {
      setLoading(false)
    }
  }, [source, keyword, range, abnormalOnly, page, pageSize, message])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load, refreshKey])

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <DatePicker.RangePicker
          value={range}
          onChange={(v) => { setRange(v); setPage(1) }}
          allowEmpty={[true, true]}
        />
        <Input.Search
          placeholder="搜索设备名称 / 编号" style={{ width: 220 }} allowClear
          onSearch={(v) => { setKeyword(v); setPage(1) }}
        />
        <Checkbox checked={abnormalOnly} onChange={(e) => { setAbnormalOnly(e.target.checked); setPage(1) }}>
          只看异常
        </Checkbox>
        <Button onClick={() => setRefreshKey((k) => k + 1)}>刷新</Button>
      </div>
      <Table
        rowKey="id" size="small" loading={loading}
        columns={recordColumns({ showStatus })} dataSource={items}
        scroll={{ x: 'max-content' }}
        pagination={{
          current: page, pageSize, total,
          showSizeChanger: true, showQuickJumper: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
        onRow={(record) => ({
          style: record.has_abnormal ? { background: '#fdf3f2' } : undefined,
        })}
      />
    </div>
  )
}

// ── 今日进度 ─────────────────────────────────────────────────────

function TodaySummaryCard({ refreshKey }: { refreshKey: number }) {
  const [summary, setSummary] = useState<InspectionFeishuTodaySummary | null>(null)

  useEffect(() => {
    fetchInspectionFeishuTodaySummary().then(setSummary).catch(() => setSummary(null))
  }, [refreshKey])

  if (!summary) return null
  const pct = summary.total_devices > 0
    ? Math.round((summary.inspected / summary.total_devices) * 100) : 0
  return (
    <Card size="small" style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
        <div style={{ minWidth: 260 }}>
          <div style={{ fontSize: 13, color: C.slate, marginBottom: 4 }}>
            今日进度（{summary.date}）
          </div>
          <Progress
            percent={pct} size="small"
            strokeColor={summary.abnormal > 0 ? '#e67e22' : C.green}
            format={() => `${summary.inspected} / ${summary.total_devices} 台`}
          />
        </div>
        <div style={{ fontSize: 13, color: C.slate }}>
          含异常 <span style={{ color: summary.abnormal > 0 ? C.red : C.green, fontWeight: 600, fontSize: 16 }}>{summary.abnormal}</span> 台
        </div>
      </div>
    </Card>
  )
}

// ── 巡检设备页签 ─────────────────────────────────────────────────

const TODAY_STATUS_META: Record<string, { label: string; color: string }> = {
  inspected: { label: '✓ 已巡', color: C.green },
  abnormal: { label: '⚠ 异常', color: C.red },
  pending: { label: '○ 未巡', color: C.stone },
}

function DevicesTab({ refreshKey }: { refreshKey: number }) {
  const { message } = App.useApp()
  const [devices, setDevices] = useState<InspectionFeishuDevice[]>([])
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoading(true)
      fetchInspectionFeishuDevices(keyword || undefined)
        .then(setDevices)
        .catch((error) => message.error((error as Error).message || '加载设备清单失败'))
        .finally(() => setLoading(false))
    }, 0)
    return () => window.clearTimeout(timer)
  }, [keyword, refreshKey, message])

  const columns: ColumnsType<InspectionFeishuDevice> = [
    { title: '设备名称', dataIndex: 'equipment_name', width: 170, ellipsis: true },
    { title: '设备编号', dataIndex: 'equipment_no', width: 130, render: (v: string | null) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v || '-'}</span> },
    { title: '型号（台账）', dataIndex: 'model', width: 150, ellipsis: true, render: (v: string | null) => v || '-' },
    { title: '安装地点（台账）', dataIndex: 'location_name', width: 150, ellipsis: true, render: (v: string | null) => v || '-' },
    {
      title: '在台账', dataIndex: 'in_ledger', width: 80,
      render: (v: boolean) => v
        ? <Tag color="green" style={{ fontSize: 12 }}>已关联</Tag>
        : <Tag color="default" style={{ fontSize: 12 }}>未关联</Tag>,
    },
    {
      title: '今日状态', dataIndex: 'today_status', width: 90,
      render: (v: string) => {
        const meta = TODAY_STATUS_META[v] || TODAY_STATUS_META.pending
        return <span style={{ color: meta.color, fontWeight: 600 }}>{meta.label}</span>
      },
    },
  ]
  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <Input.Search
          placeholder="搜索设备名称 / 编号" style={{ width: 260 }} allowClear
          onSearch={setKeyword}
        />
      </div>
      <Table
        rowKey="record_id" size="small" loading={loading}
        columns={columns} dataSource={devices}
        pagination={{ pageSize: 50, showTotal: (t) => `共 ${t} 台` }}
      />
    </div>
  )
}

// ── 主页面 ─────────────────────────────────────────────────────

export function FeishuInspectionPage() {
  const { message } = App.useApp()
  const [activeTab, setActiveTab] = useState('today')
  const [status, setStatus] = useState<InspectionFeishuSyncStatus | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [configOpen, setConfigOpen] = useState(false)

  useEffect(() => {
    fetchInspectionFeishuSyncStatus().then(setStatus).catch(() => setStatus(null))
  }, [refreshKey])

  const handleSync = async () => {
    setSyncing(true)
    try {
      const results = await triggerInspectionFeishuSync()
      const errors = Object.entries(results).filter(([, v]) => v.error)
      if (errors.length > 0) {
        message.warning(`同步完成，${errors.length} 张表失败：${errors.map(([k]) => k).join('、')}`)
      } else {
        const synced = Object.values(results).reduce((sum, v) => sum + (v.synced || 0), 0)
        message.success(`飞书同步完成，本次更新 ${synced} 条`)
      }
      setRefreshKey((k) => k + 1)
    } catch (error) {
      message.error((error as Error).message || '同步失败')
    } finally {
      setSyncing(false)
    }
  }

  const tabItems = useMemo(() => [
    {
      key: 'today',
      label: <span><CheckSquareOutlined /> 今日巡检</span>,
      children: (
        <div>
          <TodaySummaryCard refreshKey={refreshKey} />
          <RecordsTable source="today" defaultDays={null} showStatus={false} />
        </div>
      ),
    },
    {
      key: 'history',
      label: <span><HistoryOutlined /> 巡检记录</span>,
      children: <RecordsTable source="history" defaultDays={7} showStatus />,
    },
    {
      key: 'devices',
      label: <span><TabletOutlined /> 巡检设备</span>,
      children: <DevicesTab refreshKey={refreshKey} />,
    },
  ], [refreshKey])

  return (
    <div style={{ padding: '20px 24px 32px', maxWidth: 1440, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 600, color: C.ink, margin: 0 }}>设备巡检</h2>
          <p style={{ fontSize: 13, color: C.stone, margin: '4px 0 0' }}>
            岗位巡检记录（飞书多维表格镜像，只读展示）
          </p>
          <p style={{ fontSize: 12, color: '#b5b1a8', margin: '2px 0 0' }}>
            巡检数据在飞书多维表格录入，平台每 5 分钟自动同步
          </p>
        </div>
        <SyncBar
          status={status} syncing={syncing}
          onSync={handleSync} onOpenConfig={() => setConfigOpen(true)}
        />
      </div>

      <InspectionFeishuConfigDrawer
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        onSaved={() => setRefreshKey((k) => k + 1)}
      />

      <div style={{ background: C.canvas, border: `1px solid ${C.hairline}`, borderRadius: 10, padding: '4px 20px 20px' }}>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
          tabBarStyle={{ borderBottom: '1px solid #ede9e4', marginBottom: 16 }}
          tabBarGutter={32}
        />
      </div>
    </div>
  )
}
