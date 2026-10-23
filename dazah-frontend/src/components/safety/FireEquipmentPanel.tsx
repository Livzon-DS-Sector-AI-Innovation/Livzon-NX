'use client'

import { useCallback, useMemo, useState } from 'react'
import { flushSync } from 'react-dom'
import { createRoot } from 'react-dom/client'
import {
  Button,
  Card,
  Col,
  Input,
  Row,
  Segmented,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  DownloadOutlined,
  QrcodeOutlined,
  ReloadOutlined,
  SyncOutlined,
  CloudUploadOutlined,
} from '@ant-design/icons'
import { QRCodeCanvas } from 'qrcode.react'
import dayjs from 'dayjs'

import PlatformNotice from '@/components/shared/PlatformNotice'
import {
  getFireEquipmentList,
  getFireEquipmentStats,
  getFireInspectionRecords,
  initFireEquipmentWritebackTable,
  syncFireEquipment,
} from '@/actions/safety'
import { displayFieldText } from '@/lib/safety-page-tables'
import { downloadZip } from '@/lib/download'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import type { components } from '@/types/generated/schema'

import FireEquipmentDetailDrawer from './FireEquipmentDetailDrawer'
import FireEquipmentQrSheet, {
  fireEquipmentScanUrl,
  type FireEquipmentQrItem,
} from './FireEquipmentQrSheet'

const { Text } = Typography

type FireEquipmentItem = components['schemas']['FireEquipmentItem']
type FireEquipmentStats = components['schemas']['FireEquipmentStats']
type FireEquipmentListResponse =
  components['schemas']['FireEquipmentListResponse']
type FireInspectionRecordItem =
  components['schemas']['FireInspectionRecordItem']
type FireInspectionListResponse =
  components['schemas']['FireInspectionListResponse']

interface Props {
  pageKey: string
  initialStats: FireEquipmentStats | null
  initialEquipment: FireEquipmentListResponse | null
  initialRecords: FireInspectionListResponse | null
  initialError: string | null
}

const TYPE_OPTIONS = [
  { value: 'extinguisher', label: '灭火器' },
  { value: 'hydrant', label: '消防栓' },
]
const MONTH_STATUS_OPTIONS = [
  { value: 'inspected', label: '本月已检' },
  { value: 'uninspected', label: '本月未检' },
]
const RESULT_OPTIONS = [
  { value: 'pass', label: '合格' },
  { value: 'fail', label: '不合格' },
]

const RESULT_TAG: Record<string, { color: string; label: string }> = {
  pass: { color: 'success', label: '合格' },
  fail: { color: 'error', label: '不合格' },
}

function typeLabel(value: string | undefined): string {
  return TYPE_OPTIONS.find((option) => option.value === value)?.label ?? (value || '—')
}

function formatDateTime(value: string | null | undefined): string {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'
}

function toQrItem(row: FireEquipmentItem): FireEquipmentQrItem {
  return {
    id: String(row.id),
    equipmentTypeLabel: row.equipment_type_label || typeLabel(row.equipment_type),
    equipmentNo: row.equipment_no,
    department: row.department,
    location: row.location,
  }
}

function sanitizeFileName(text: string): string {
  return text.replace(/[\\/:*?"<>|\s]+/g, '_').slice(0, 60)
}

function qrFileName(row: FireEquipmentItem, index: number): string {
  const no = row.equipment_no || `未填编号_${row.record_id.slice(-6)}`
  const suffix = row.location ? `_${sanitizeFileName(row.location)}` : ''
  return `${String(index + 1).padStart(3, '0')}_${sanitizeFileName(no)}${suffix}.png`
}

function dataUrlToBytes(dataUrl: string): ArrayBuffer {
  const base64 = dataUrl.slice(dataUrl.indexOf(',') + 1)
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes.buffer
}

/** 灭火器/消防栓点检主面板：台账概览 + 器材台账 + 二维码打印 + 点检记录。 */
export default function FireEquipmentPanel({
  pageKey,
  initialStats,
  initialEquipment,
  initialRecords,
  initialError,
}: Props) {
  const { canOperate } = usePagePermissions(pageKey)
  const [stats, setStats] = useState<FireEquipmentStats | null>(initialStats)
  const [equipmentPage, setEquipmentPage] = useState(initialEquipment)
  const [recordsPage, setRecordsPage] = useState(initialRecords)
  const [loadError, setLoadError] = useState<string | null>(initialError)

  // 器材台账筛选与分页
  const [equipmentType, setEquipmentType] = useState<string>('all')
  const [monthStatus, setMonthStatus] = useState<string>('all')
  const [expiryStatus, setExpiryStatus] = useState<string>('all')
  const [equipmentKeyword, setEquipmentKeyword] = useState('')
  const [equipmentPageNo, setEquipmentPageNo] = useState(1)
  const [equipmentLoading, setEquipmentLoading] = useState(false)

  // 点检记录筛选与分页
  const [recordType, setRecordType] = useState<string>('all')
  const [recordResult, setRecordResult] = useState<string>('all')
  const [recordKeyword, setRecordKeyword] = useState('')
  const [recordPageNo, setRecordPageNo] = useState(1)
  const [recordsLoading, setRecordsLoading] = useState(false)

  const [syncing, setSyncing] = useState(false)
  const [initingWriteback, setInitingWriteback] = useState(false)
  const [qrItems, setQrItems] = useState<FireEquipmentQrItem[] | null>(null)
  const [batchPreparing, setBatchPreparing] = useState(false)
  const [downloadingQr, setDownloadingQr] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const configured = stats?.is_configured ?? false

  const refreshStats = useCallback(async () => {
    const res = await getFireEquipmentStats({ pageKey })
    if (res.code === 200 && res.data) {
      setStats(res.data)
      return res.data
    }
    return null
  }, [pageKey])

  const loadEquipment = useCallback(
    async (page = equipmentPageNo) => {
      setEquipmentLoading(true)
      try {
        const res = await getFireEquipmentList({
          pageKey,
          page,
          pageSize: 20,
          equipmentType: equipmentType === 'all' ? null : equipmentType,
          monthStatus: monthStatus === 'all' ? null : monthStatus,
          expiryStatus: expiryStatus === 'all' ? null : expiryStatus,
          keyword: equipmentKeyword.trim() || null,
        })
        if (res.code === 200 && res.data) {
          setEquipmentPage(res.data)
          setLoadError(null)
        } else {
          setLoadError(res.message || '读取器材台账失败')
        }
      } finally {
        setEquipmentLoading(false)
      }
    },
    [pageKey, equipmentType, monthStatus, expiryStatus, equipmentKeyword, equipmentPageNo]
  )

  const loadRecords = useCallback(
    async (page = recordPageNo) => {
      setRecordsLoading(true)
      try {
        const res = await getFireInspectionRecords({
          pageKey,
          page,
          pageSize: 20,
          equipmentType: recordType === 'all' ? null : recordType,
          result: recordResult === 'all' ? null : recordResult,
          keyword: recordKeyword.trim() || null,
        })
        if (res.code === 200 && res.data) {
          setRecordsPage(res.data)
        }
      } finally {
        setRecordsLoading(false)
      }
    },
    [pageKey, recordType, recordResult, recordKeyword, recordPageNo]
  )

  const handleSync = async () => {
    setSyncing(true)
    try {
      const res = await syncFireEquipment({ pageKey })
      if (res.code === 200 && res.data) {
        setStats(res.data)
        await Promise.all([loadEquipment(1), loadRecords(1)])
        setEquipmentPageNo(1)
        setRecordPageNo(1)
        message.success(
          `同步完成：灭火器 ${res.data.extinguisher_count} 台、消防栓 ${res.data.hydrant_count} 台`
        )
      } else {
        message.error(res.message || '同步失败，请检查飞书绑定')
      }
    } finally {
      setSyncing(false)
    }
  }

  const handleInitWriteback = async () => {
    setInitingWriteback(true)
    try {
      const res = await initFireEquipmentWritebackTable({ pageKey })
      if (res.code === 200 && res.data) {
        await refreshStats()
        message.success(
          res.data.created
            ? `已在飞书表格创建「${res.data.table_name}」子表，点检记录将自动回写`
            : `已绑定飞书子表「${res.data.table_name}」，点检记录将自动回写`
        )
      } else {
        message.error(res.message || '创建点检记录回写表失败')
      }
    } finally {
      setInitingWriteback(false)
    }
  }

  const handleBatchPrint = async () => {
    setBatchPreparing(true)
    try {
      // 打印当前筛选下的全部器材（上限 200，覆盖常规车间规模）
      const res = await getFireEquipmentList({
        pageKey,
        page: 1,
        pageSize: 200,
        equipmentType: equipmentType === 'all' ? null : equipmentType,
        monthStatus: monthStatus === 'all' ? null : monthStatus,
        expiryStatus: expiryStatus === 'all' ? null : expiryStatus,
        keyword: equipmentKeyword.trim() || null,
      })
      if (res.code === 200 && res.data) {
        setQrItems(res.data.items.map(toQrItem))
      } else {
        message.error(res.message || '读取器材清单失败')
      }
    } finally {
      setBatchPreparing(false)
    }
  }

  const handleBatchDownload = async () => {
    setDownloadingQr(true)
    try {
      // 与批量打印同口径：当前筛选条件下的全部器材（上限 200）
      const res = await getFireEquipmentList({
        pageKey,
        page: 1,
        pageSize: 200,
        equipmentType: equipmentType === 'all' ? null : equipmentType,
        monthStatus: monthStatus === 'all' ? null : monthStatus,
        expiryStatus: expiryStatus === 'all' ? null : expiryStatus,
        keyword: equipmentKeyword.trim() || null,
      })
      if (res.code !== 200 || !res.data) {
        message.error(res.message || '读取器材清单失败')
        return
      }
      const items = res.data.items
      if (!items.length) {
        message.warning('当前筛选没有可下载的器材')
        return
      }
      const host = document.createElement('div')
      host.style.position = 'fixed'
      host.style.left = '-9999px'
      host.style.top = '0'
      document.body.appendChild(host)
      const root = createRoot(host)
      const entries: { name: string; bytes: ArrayBuffer }[] = []
      try {
        // createRoot 的首次挂载是异步的：先渲染占位并等提交完成；
        // 之后已挂载根的更新在 flushSync 内同步提交，可确定性读取画布。
        root.render(<div />)
        let mounted = false
        for (let attempt = 0; attempt < 20 && !mounted; attempt += 1) {
          await new Promise((resolve) => setTimeout(resolve, 0))
          mounted = host.hasChildNodes()
        }
        if (!mounted) {
          message.error('二维码生成失败，请重试')
          return
        }
        for (const [index, row] of items.entries()) {
          flushSync(() => {
            root.render(
              <QRCodeCanvas
                key={String(row.id)}
                value={fireEquipmentScanUrl(String(row.id))}
                size={240}
                level="M"
                marginSize={2}
              />
            )
          })
          const canvas = host.querySelector('canvas')
          if (!canvas) continue
          entries.push({
            name: qrFileName(row, index),
            bytes: dataUrlToBytes(canvas.toDataURL('image/png')),
          })
        }
      } finally {
        root.unmount()
        host.remove()
      }
      if (!entries.length) {
        message.error('二维码生成失败，请重试')
        return
      }
      await downloadZip(entries, `消防器材二维码_${dayjs().format('YYYYMMDD_HHmm')}`)
      message.success(
        items.length >= 200
          ? `已打包下载 ${entries.length} 张二维码（当前筛选超过 200 台，仅打包前 200 台；可缩小范围后再次下载）`
          : `已打包下载 ${entries.length} 张二维码`
      )
    } finally {
      setDownloadingQr(false)
    }
  }

  const openDetail = (row: FireEquipmentItem) => {
    setDetailId(String(row.id))
    setDetailOpen(true)
  }

  const baseEquipmentColumns: ColumnsType<FireEquipmentItem> = [
    {
      title: '器材编号',
      dataIndex: 'equipment_no',
      width: 150,
      render: (value: string, row) =>
        value ? (
          <Button type="link" size="small" onClick={() => openDetail(row)} style={{ padding: 0 }}>
            {value}
          </Button>
        ) : (
          <Tooltip title="飞书台账未填写编号，点击查看详情">
            <Button type="link" size="small" onClick={() => openDetail(row)} style={{ padding: 0 }}>
              （未填编号）
            </Button>
          </Tooltip>
        ),
    },
    {
      title: '类型',
      dataIndex: 'equipment_type_label',
      width: 90,
      render: (value: string) => <Tag>{value || '—'}</Tag>,
    },
    {
      title: '归属部门',
      dataIndex: 'department',
      width: 150,
      ellipsis: true,
      render: (v: string) => v || '—',
    },
    {
      title: '存放位置',
      dataIndex: 'location',
      width: 170,
      ellipsis: true,
      render: (v: string) => v || '—',
    },
    {
      title: '最近点检',
      dataIndex: 'last_inspected_at',
      width: 160,
      render: (value: string | null, row) =>
        value ? (
          <Space size={4}>
            <span>{formatDateTime(value)}</span>
            <Tag color={RESULT_TAG[row.last_inspection_result ?? '']?.color ?? 'default'}>
              {RESULT_TAG[row.last_inspection_result ?? '']?.label ?? '—'}
            </Tag>
          </Space>
        ) : (
          <Tag>尚未点检</Tag>
        ),
    },
    {
      title: '本月状态',
      dataIndex: 'month_status',
      width: 100,
      render: (value: string) =>
        value === 'inspected' ? (
          <Tag color="success">本月已检</Tag>
        ) : (
          <Tag color="warning">本月未检</Tag>
        ),
    },
    {
      title: '有效日期',
      dataIndex: 'expiry_date',
      width: 180,
      render: (value: string | null, row) => {
        if (!value) return '—'
        const days = row.expiry_days_left
        const label =
          days === null || days === undefined
            ? ''
            : days < 0
              ? `已过期${-days}天`
              : `${days}天后到期`
        const color =
          row.expiry_status === 'expired'
            ? 'error'
            : row.expiry_status === 'expiring'
              ? 'warning'
              : 'default'
        return (
          <Space size={4}>
            <span>{value}</span>
            {label ? <Tag color={color}>{label}</Tag> : null}
          </Space>
        )
      },
    },
  ]

  // 多维表格动态列：与飞书字段自动对齐（增删列后同步即生效）
  const bitableColumns: ColumnsType<FireEquipmentItem> = (
    equipmentPage?.columns ?? []
  ).map((column) => ({
    title: column.name,
    key: `field-${column.name}`,
    width: 150,
    ellipsis: true,
    render: (_, row) => displayFieldText(row.fields?.[column.name]) || '—',
  }))

  const actionColumn: ColumnsType<FireEquipmentItem> = [
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 150,
      render: (_, row) => (
        <Space size={4}>
          <Button
            type="link"
            size="small"
            icon={<QrcodeOutlined />}
            onClick={() => setQrItems([toQrItem(row)])}
          >
            二维码
          </Button>
          <Button type="link" size="small" onClick={() => openDetail(row)}>
            详情
          </Button>
        </Space>
      ),
    },
  ]

  const equipmentColumns: ColumnsType<FireEquipmentItem> = [
    ...baseEquipmentColumns,
    ...bitableColumns,
    ...actionColumn,
  ]

  const recordColumns: ColumnsType<FireInspectionRecordItem> = [
    {
      title: '点检时间',
      dataIndex: 'inspected_at',
      width: 150,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '器材编号',
      dataIndex: 'equipment_no',
      width: 130,
      render: (value: string) => value || '（未填编号）',
    },
    {
      title: '类型',
      dataIndex: 'equipment_type_label',
      width: 90,
      render: (value: string) => <Tag>{value || '—'}</Tag>,
    },
    { title: '归属部门', dataIndex: 'department', ellipsis: true, render: (v: string) => v || '—' },
    { title: '存放位置', dataIndex: 'location', ellipsis: true, render: (v: string) => v || '—' },
    {
      title: '结果',
      dataIndex: 'result',
      width: 90,
      render: (value: string) => (
        <Tag color={RESULT_TAG[value]?.color ?? 'default'}>
          {RESULT_TAG[value]?.label ?? value}
        </Tag>
      ),
    },
    {
      title: '点检人',
      dataIndex: 'inspector_name',
      width: 100,
      render: (v: string) => v || '—',
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 80,
      render: (value: string) => (value === 'scan' ? '扫码' : '网页'),
    },
    {
      title: '飞书回写',
      dataIndex: 'feishu_record_id',
      width: 90,
      render: (value: string | null) =>
        value ? (
          <Tag color="success">已回写</Tag>
        ) : (
          <Tooltip title="待回写：将在下次同步时自动补写到飞书点检记录表">
            <Tag>待回写</Tag>
          </Tooltip>
        ),
    },
    {
      title: '异常处理措施',
      dataIndex: 'abnormal_action',
      ellipsis: true,
      render: (v: string | null) => v || '—',
    },
  ]

  const statItems = useMemo(
    () => [
      { title: '器材总数', value: stats?.total ?? 0 },
      { title: '灭火器', value: stats?.extinguisher_count ?? 0 },
      { title: '消防栓', value: stats?.hydrant_count ?? 0 },
      { title: '本月已检', value: stats?.inspected_this_month ?? 0 },
      { title: '本月未检', value: stats?.uninspected_this_month ?? 0 },
      {
        title: '本月不合格',
        value: stats?.failed_this_month ?? 0,
        valueStyle: { color: (stats?.failed_this_month ?? 0) > 0 ? '#cf1322' : undefined },
      },
      {
        title: '30天内到期',
        value: stats?.expiring_in_30_count ?? 0,
        valueStyle: {
          color: (stats?.expiring_in_30_count ?? 0) > 0 ? '#d46b08' : undefined,
        },
      },
      {
        title: '已过期',
        value: stats?.expired_count ?? 0,
        valueStyle: { color: (stats?.expired_count ?? 0) > 0 ? '#cf1322' : undefined },
      },
    ],
    [stats]
  )

  const renderEquipmentTab = () => (
    <>
      <Space wrap style={{ marginBottom: 16 }}>
        <Segmented
          options={[{ value: 'all', label: '全部' }, ...TYPE_OPTIONS]}
          value={equipmentType}
          onChange={(value) => {
            setEquipmentType(String(value))
            setEquipmentPageNo(1)
          }}
        />
        <Segmented
          options={[{ value: 'all', label: '全部状态' }, ...MONTH_STATUS_OPTIONS]}
          value={monthStatus}
          onChange={(value) => {
            setMonthStatus(String(value))
            setEquipmentPageNo(1)
          }}
        />
        <Segmented
          options={[
            { value: 'all', label: '全部有效期' },
            { value: 'expiring', label: '30天内到期' },
            { value: 'expired', label: '已过期' },
          ]}
          value={expiryStatus}
          onChange={(value) => {
            setExpiryStatus(String(value))
            setEquipmentPageNo(1)
          }}
        />
        <Input.Search
          placeholder="编号 / 部门 / 位置"
          allowClear
          style={{ width: 220 }}
          value={equipmentKeyword}
          onChange={(event) => setEquipmentKeyword(event.target.value)}
          onSearch={() => {
            setEquipmentPageNo(1)
            void loadEquipment(1)
          }}
        />
        <Button
          type="primary"
          ghost
          icon={<QrcodeOutlined />}
          loading={batchPreparing}
          onClick={() => void handleBatchPrint()}
          disabled={!equipmentPage?.items.length}
        >
          批量打印二维码
        </Button>
        <Button
          icon={<DownloadOutlined />}
          loading={downloadingQr}
          onClick={() => void handleBatchDownload()}
          disabled={!equipmentPage?.items.length}
        >
          批量下载二维码
        </Button>
        <Button
          icon={<ReloadOutlined />}
          loading={equipmentLoading}
          onClick={() => void loadEquipment()}
        >
          刷新
        </Button>
      </Space>
      <Table
        rowKey="id"
        size="small"
        columns={equipmentColumns}
        dataSource={equipmentPage?.items ?? []}
        loading={equipmentLoading}
        pagination={{
          current: equipmentPage?.page ?? 1,
          pageSize: equipmentPage?.page_size ?? 20,
          total: equipmentPage?.total ?? 0,
          showSizeChanger: false,
          showTotal: (total) => `共 ${total} 台`,
          onChange: (page) => {
            setEquipmentPageNo(page)
            void loadEquipment(page)
          },
        }}
        scroll={{ x: 1000 + bitableColumns.length * 150 }}
      />
    </>
  )

  const renderRecordsTab = () => (
    <>
      <Space wrap style={{ marginBottom: 16 }}>
        <Segmented
          options={[{ value: 'all', label: '全部' }, ...TYPE_OPTIONS]}
          value={recordType}
          onChange={(value) => {
            setRecordType(String(value))
            setRecordPageNo(1)
          }}
        />
        <Segmented
          options={[{ value: 'all', label: '全部结果' }, ...RESULT_OPTIONS]}
          value={recordResult}
          onChange={(value) => {
            setRecordResult(String(value))
            setRecordPageNo(1)
          }}
        />
        <Input.Search
          placeholder="编号 / 部门 / 位置 / 点检人"
          allowClear
          style={{ width: 220 }}
          value={recordKeyword}
          onChange={(event) => setRecordKeyword(event.target.value)}
          onSearch={() => {
            setRecordPageNo(1)
            void loadRecords(1)
          }}
        />
        <Button
          icon={<ReloadOutlined />}
          loading={recordsLoading}
          onClick={() => void loadRecords()}
        >
          刷新
        </Button>
      </Space>
      <Table
        rowKey="id"
        size="small"
        columns={recordColumns}
        dataSource={recordsPage?.items ?? []}
        loading={recordsLoading}
        expandable={{
          expandedRowRender: (record) => (
            <div style={{ display: 'grid', gap: 4 }}>
              {(record.items ?? []).map((item, index) => (
                <div key={String(item.key ?? index)} style={{ display: 'flex', gap: 8 }}>
                  {item.result === 'ok' ? (
                    <Tag color="success">合格</Tag>
                  ) : (
                    <Tag color="error">不合格</Tag>
                  )}
                  <span>{String(item.label ?? '')}</span>
                  {item.remark ? (
                    <Text type="secondary">备注：{String(item.remark)}</Text>
                  ) : null}
                </div>
              ))}
            </div>
          ),
        }}
        pagination={{
          current: recordsPage?.page ?? 1,
          pageSize: recordsPage?.page_size ?? 20,
          total: recordsPage?.total ?? 0,
          showSizeChanger: false,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (page) => {
            setRecordPageNo(page)
            void loadRecords(page)
          },
        }}
        scroll={{ x: 1000 }}
        locale={{ emptyText: '暂无点检记录，扫码或网页提交后展示' }}
      />
    </>
  )

  if (loadError && !equipmentPage) {
    return (
      <PlatformNotice
        type="error"
        message="器材台账加载失败"
        description={loadError}
        action={
          <Button size="small" onClick={() => void refreshStats().then(() => void loadEquipment(1))}>
            重试
          </Button>
        }
      />
    )
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {!configured ? (
        <PlatformNotice
          type="warning"
          message="尚未绑定飞书多维表格"
          description="先到「安全管理 → 系统配置 → 飞书设置」为本页面粘贴各车间灭火器/消防栓表格链接并勾选子表页签，同步后即可生成二维码与点检记录。"
          showRulesLink={false}
        />
      ) : null}
      <Card size="small">
        <Row gutter={[16, 16]}>
          {statItems.map((item) => (
            <Col key={item.title} xs={12} sm={8} md={4}>
              <Statistic title={item.title} value={item.value} {...(item.valueStyle ? { valueStyle: item.valueStyle } : {})} />
            </Col>
          ))}
        </Row>
        <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <Text type="secondary">
            {stats?.last_synced_at
              ? `最近同步：${formatDateTime(stats.last_synced_at)}${
                  stats.last_sync_status === 'success'
                    ? ''
                    : `（${stats.last_sync_status === 'partial' ? '部分失败' : '失败'}${
                        stats.last_sync_error ? `：${stats.last_sync_error}` : ''
                      }）`
                }`
              : '尚未同步过飞书台账'}
          </Text>
          {configured && stats?.writeback_enabled ? (
            <Text type="success">点检记录自动回写飞书「点检记录」子表</Text>
          ) : null}
          {configured && !stats?.writeback_enabled && canOperate ? (
            <Button
              size="small"
              icon={<CloudUploadOutlined />}
              loading={initingWriteback}
              onClick={() => void handleInitWriteback()}
            >
              一键创建点检记录回写表
            </Button>
          ) : null}
        </div>
      </Card>
      <Card size="small">
        <Tabs
          defaultActiveKey="equipment"
          items={[
            { key: 'equipment', label: '器材台账', children: renderEquipmentTab() },
            { key: 'records', label: '点检记录', children: renderRecordsTab() },
          ]}
        />
      </Card>
      {canOperate ? (
        <Button
          type="primary"
          icon={<SyncOutlined />}
          loading={syncing}
          onClick={() => void handleSync()}
          style={{ width: 'fit-content' }}
        >
          立即同步飞书台账
        </Button>
      ) : null}
      <FireEquipmentQrSheet
        open={qrItems !== null}
        onClose={() => setQrItems(null)}
        items={qrItems ?? []}
      />
      <FireEquipmentDetailDrawer
        open={detailOpen}
        pageKey={pageKey}
        equipmentId={detailId}
        onClose={() => setDetailOpen(false)}
      />
    </div>
  )
}
