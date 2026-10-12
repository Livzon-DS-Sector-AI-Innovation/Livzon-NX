'use client'

import { memo, useCallback, useEffect, useMemo, useState } from 'react'
import type { CSSProperties, TdHTMLAttributes } from 'react'
import { Card, Typography, Upload, Table, App, Row, Col, Button, Popconfirm, Space, Modal, Input, InputNumber, Tag } from 'antd'
import Alert from '@/components/shared/PlatformNotice'
import type { ColumnsType } from 'antd/es/table'
import { ScheduleOutlined, InboxOutlined, ReloadOutlined, DownloadOutlined, DeleteOutlined, EyeOutlined, HistoryOutlined, FileSearchOutlined, EditOutlined } from '@ant-design/icons'
import {
  deleteScheduleExcelArchive,
  getScheduleExcelArchive,
  getScheduleExcelArchives,
  getScheduleConstraints,
  getScheduleValidation,
  saveScheduleConstraints,
  uploadScheduleExcel,
} from '@/actions/production'
import type {
  ScheduleConstraintSettings,
  ScheduleExcelArchive,
  ScheduleHistoryFix,
  ScheduleMergeChange,
  ScheduleMergeReport,
  ScheduleValidationIssue,
  ScheduleValidationReport,
} from '@/types/production'
import BoardNavBlocks from '@/components/production/board-nav-blocks'
import { useProductContextStore } from '@/stores/product-context'
import { useAuthStore } from '@/stores/auth'
import { PRODUCTION_SCHEDULING_SECTIONS } from '@/lib/production-overview-sections'
import { usePermission } from '@/hooks/usePermission'
import {
  hasProductionSchedulingProduct,
  PRODUCTION_PAGE_KEYS,
  useProductionPermissions,
} from '@/components/production/useProductionPermissions'

const { Title, Text } = Typography
const { Dragger } = Upload
const { TextArea } = Input

// 排产按产品存档,汇总(五产线聚合)没有排产数据,本页隐藏该入口
// 汇总无排产存档；FL 氟苯尼考为合成预混工艺，无发酵排产表（批次数据走飞书月表同步）
const SCHEDULING_HIDE_CODES: readonly string[] = ['SUMMARY', 'FL']

interface MergedCell {
  s: { r: number; c: number }
  e: { r: number; c: number }
}

/** 长提示（格式错误/冻结告警等）的停留秒数,antd 默认 3s 读不完 */
const TIP_SECONDS = 8

/** 排产 Excel 上传大小上限（与后端 schedule_excel_api 同步：1MB） */
const SCHEDULE_UPLOAD_MAX_BYTES = 1024 * 1024

/** 单元格渲染值：后端子端统一为 string */
type CellValue = string

const EMPTY_CHANGES: ScheduleMergeChange[] = []

const changeColumns: ColumnsType<ScheduleMergeChange> = [
  { title: '周期块', dataIndex: 'block', width: 90 },
  { title: '日期', dataIndex: 'date', width: 110 },
  { title: '行', dataIndex: 'row', width: 110 },
  {
    title: '原存档值',
    dataIndex: 'old',
    width: 140,
    render: (v: string) => v || '（空）',
  },
  {
    title: '本次上传值',
    dataIndex: 'new',
    width: 140,
    render: (v: string) => v || '（空）',
  },
]

/** 历史改动明细表：memo 组件 + 分页，原因输入的高频重渲染不再波及明细行 */
const MergeChangeTable = memo(function MergeChangeTable({
  changes,
}: {
  changes: ScheduleMergeChange[]
}) {
  const rows = useMemo(() => changes.slice(0, 200), [changes])
  return (
    <Table
      size="small"
      pagination={{ pageSize: 10, showSizeChanger: false, hideOnSinglePage: true }}
      dataSource={rows}
      rowKey={(_: ScheduleMergeChange, index?: number) => String(index)}
      columns={changeColumns}
    />
  )
})

const issueColumns: ColumnsType<ScheduleValidationIssue> = [
  {
    title: '级别',
    dataIndex: 'level',
    key: 'level',
    width: 76,
    render: (level: ScheduleValidationIssue['level']) => (
      <Tag color={level === 'warn' ? 'orange' : 'blue'} style={{ marginRight: 0 }}>
        {level === 'warn' ? '需确认' : '提示'}
      </Tag>
    ),
  },
  {
    title: '日期',
    dataIndex: 'date',
    key: 'date',
    width: 90,
    render: (v?: string | null) => (v ? v.slice(5) : '—'),
  },
  {
    title: '罐号',
    dataIndex: 'tank_no',
    key: 'tank_no',
    width: 72,
    render: (v?: string | null) => v || '—',
  },
  {
    title: '批号',
    dataIndex: 'batch_no',
    key: 'batch_no',
    width: 104,
    render: (v?: string | null) => v || '—',
  },
  { title: '说明', dataIndex: 'text', key: 'text' },
]

/** 校验问题清单表：与 MergeChangeTable 同模式 */
const ValidationIssueTable = memo(function ValidationIssueTable({
  issues,
}: {
  issues: ScheduleValidationIssue[]
}) {
  return (
    <Table
      size="small"
      pagination={{ pageSize: 10, showSizeChanger: false, hideOnSinglePage: true }}
      dataSource={issues}
      rowKey={(_: ScheduleValidationIssue, index?: number) => String(index)}
      columns={issueColumns}
    />
  )
})

/** 约束展示值：未配置显示占位符 */
function constraintText(value: number | null | undefined, unit: string) {
  return value == null ? '未配置' : `${value}${unit}`
}

function fileDownloadUrl(archiveId: string) {
  return `/api/v1/production/schedule-excel/${archiveId}/file`
}

export default function SchedulingPage() {
  const user = useAuthStore((state) => state.user)
  const selectedProduct = useProductContextStore((state) => state.productCode)
  const { authorizationKey } = useProductionPermissions(PRODUCTION_PAGE_KEYS.scheduling)
  const visibleProducts = PRODUCTION_SCHEDULING_SECTIONS.filter(
    (item) => hasProductionSchedulingProduct(user, item.key),
  )
  const hideCodes = useMemo(() => [
    ...SCHEDULING_HIDE_CODES,
    ...PRODUCTION_SCHEDULING_SECTIONS.filter(
      (item) => !hasProductionSchedulingProduct(user, item.key),
    ).map((item) => item.key),
  ], [user])
  const productCode = visibleProducts.find((item) => item.key === selectedProduct)?.key
    ?? visibleProducts[0]?.key
  if (!productCode) return (
    <div className="p-6">
      <Alert type="warning" showIcon title="暂无可查看的排产产品，请联系管理员配置页面权限。" />
    </div>
  )
  return <SchedulingContent key={`${productCode}:${authorizationKey}`} productCode={productCode} hideCodes={hideCodes} />
}

function SchedulingContent({ productCode, hideCodes }: {
  productCode: string
  hideCodes: readonly string[]
}) {
  const { message } = App.useApp()
  const [archives, setArchives] = useState<ScheduleExcelArchive[]>([])
  const [loadingList, setLoadingList] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [active, setActive] = useState<ScheduleExcelArchive | null>(null)
  const [loadingActive, setLoadingActive] = useState(false)
  // 历史改动确认：默认冻结保留原存档；有权限者填原因后以新文件修正
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [mergeReport, setMergeReport] = useState<ScheduleMergeReport | null>(null)
  const [fixModalOpen, setFixModalOpen] = useState(false)
  const [fixReason, setFixReason] = useState('')
  const [fixSubmitting, setFixSubmitting] = useState(false)
  // 历史存档列表里的修正记录查看入口
  const [viewingFixes, setViewingFixes] = useState<ScheduleHistoryFix[] | null>(null)
  const [viewingFixesFile, setViewingFixesFile] = useState('')
  // 当前产品累计历史修正次数（audit 口径，随存档列表 meta 返回）
  const [fixTotal, setFixTotal] = useState(0)
  // 排产校验（当前仅 FA）：上传后自动弹报告，存档行可随时手动复查
  const [validation, setValidation] = useState<ScheduleValidationReport | null>(null)
  const [validationFile, setValidationFile] = useState('')
  const [validatingId, setValidatingId] = useState<string | null>(null)
  // 排产约束配置（校验与后续自动排产共用的工艺参数）
  const [constraints, setConstraints] = useState<ScheduleConstraintSettings | null>(null)
  const [constraintModalOpen, setConstraintModalOpen] = useState(false)
  const [constraintDraft, setConstraintDraft] = useState<ScheduleConstraintSettings | null>(null)
  const [savingConstraints, setSavingConstraints] = useState(false)
  const isFa = productCode === 'FA'
  const { has } = usePermission()
  const canFixHistory = has('production:schedule-archive')
  const { canDelete, canBulkImport, canExport, canSync } = useProductionPermissions(
    PRODUCTION_PAGE_KEYS.scheduling,
  )

  const reloadList = useCallback(async () => {
    setLoadingList(true)
    try {
      const res = await getScheduleExcelArchives(1, 50, productCode)
      if (res.code === 200) {
        setArchives(res.data || [])
        setFixTotal(res.meta?.history_fix_total ?? 0)
      }
    } catch {
      message.error('加载历史存档失败')
    } finally {
      setLoadingList(false)
    }
  }, [message, productCode])

  useEffect(() => {
    void reloadList()
    // 切换产品上下文后重新加载该产品的存档
  }, [reloadList, productCode])

  // 排产约束（仅 FA）：随产品上下文加载，供卡片展示与编辑预填
  const reloadConstraints = useCallback(async () => {
    try {
      const res = await getScheduleConstraints(productCode)
      if (res.code === 200) setConstraints(res.data)
    } catch {
      // 约束加载失败不阻断排产页；编辑弹窗打开时会重新拉取
    }
  }, [productCode])

  useEffect(() => {
    if (!isFa) {
      setConstraints(null)
      return
    }
    void reloadConstraints()
  }, [isFa, reloadConstraints])

  const openValidation = useCallback(
    async (archiveId: string, fileName: string) => {
      setValidatingId(archiveId)
      try {
        const res = await getScheduleValidation(archiveId)
        if (res.code === 200) {
          setValidation(res.data)
          setValidationFile(fileName)
        } else {
          message.error(res.message || '排产校验失败', TIP_SECONDS)
        }
      } catch {
        message.error('排产校验请求失败')
      } finally {
        setValidatingId(null)
      }
    },
    [message],
  )

  const openConstraintModal = useCallback(async () => {
    // 打开时重拉一次，避免展示过期配置
    try {
      const res = await getScheduleConstraints(productCode)
      if (res.code === 200) {
        setConstraints(res.data)
        setConstraintDraft({ ...res.data })
      }
    } catch {
      setConstraintDraft(constraints ? { ...constraints } : null)
      message.error('加载排产约束失败', TIP_SECONDS)
    }
    setConstraintModalOpen(true)
  }, [constraints, message, productCode])

  const submitConstraints = useCallback(async () => {
    if (!constraintDraft) return
    if (
      constraintDraft.standard_cycle_hours != null &&
      constraintDraft.max_cycle_hours != null &&
      constraintDraft.max_cycle_hours < constraintDraft.standard_cycle_hours
    ) {
      message.error('最大培养周期不能小于标准培养周期', TIP_SECONDS)
      return
    }
    setSavingConstraints(true)
    try {
      const res = await saveScheduleConstraints(constraintDraft, productCode)
      if (res.code === 200) {
        setConstraints(res.data)
        setConstraintModalOpen(false)
        message.success('排产约束已保存')
      } else {
        message.error(res.message || '保存失败', TIP_SECONDS)
      }
    } catch {
      message.error('保存排产约束失败', TIP_SECONDS)
    } finally {
      setSavingConstraints(false)
    }
  }, [constraintDraft, message, productCode])

  const handleUpload = async (file: File) => {
    if (!canBulkImport) return false
    if (file.size > SCHEDULE_UPLOAD_MAX_BYTES) {
      message.error(
        `文件大小不能超过 1MB（当前 ${(file.size / 1024 / 1024).toFixed(1)}MB）`,
        TIP_SECONDS,
      )
      return false
    }
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await uploadScheduleExcel(formData, productCode)
      if (res.code === 200 && res.data?.id) {
        message.success(`已存档：${res.data.file_name}`)
        setActive(res.data)
        await reloadList()
        // 上传后自动排产校验（仅 FA）：有问题才弹报告，干净则不打扰
        if (res.data.validation?.issues?.length) {
          setValidation(res.data.validation)
          setValidationFile(res.data.file_name)
        }
        const merge: ScheduleMergeReport | undefined = res.data.merge
        if (merge?.warning) {
          message.warning(merge.warning, TIP_SECONDS)
        }
        const changes = merge?.discarded_changes ?? []
        if (changes.length > 0 && !merge?.corrected) {
          if (canFixHistory) {
            setPendingFile(file)
            setMergeReport(merge ?? null)
            setFixReason('')
            setFixModalOpen(true)
          } else {
            message.info(
              `检测到 ${changes.length} 处「今天之前」的历史改动已被冻结保留；如需以新表修正历史，请联系管理员`,
              TIP_SECONDS,
            )
          }
        }
      } else {
        // 存档拒绝/格式错误提示较长,延长停留时间便于读完
        message.error(res.message || '上传失败', TIP_SECONDS)
      }
    } catch {
      message.error('上传失败', TIP_SECONDS)
    } finally {
      setUploading(false)
    }
    return false
  }

  const confirmHistoryFix = async () => {
    if (!pendingFile) return
    if (!fixReason.trim()) {
      message.warning('请填写历史修正原因')
      return
    }
    setFixSubmitting(true)
    try {
      const formData = new FormData()
      formData.append('file', pendingFile)
      const res = await uploadScheduleExcel(formData, productCode, {
        allowHistoryFix: true,
        historyFixReason: fixReason.trim(),
      })
      if (res.code === 200 && res.data?.id) {
        message.success(`已存档并按新文件修正历史：${res.data.file_name}`)
        setFixModalOpen(false)
        setPendingFile(null)
        setMergeReport(null)
        setActive(res.data)
        await reloadList()
      } else {
        message.error(res.message || '历史修正失败', TIP_SECONDS)
      }
    } catch {
      message.error('历史修正失败', TIP_SECONDS)
    } finally {
      setFixSubmitting(false)
    }
  }

  const openArchive = async (archiveId: string) => {
    setLoadingActive(true)
    try {
      const res = await getScheduleExcelArchive(archiveId)
      if (res.code === 200 && res.data) {
        setActive(res.data)
      } else {
        message.error(res.message || '打开存档失败')
      }
    } catch {
      message.error('打开存档失败')
    } finally {
      setLoadingActive(false)
    }
  }

  const removeArchive = async (archiveId: string) => {
    if (!canDelete) return
    try {
      const res = await deleteScheduleExcelArchive(archiveId)
      if (res.code === 200) {
        message.success('存档已删除')
        if (active?.id === archiveId) setActive(null)
        await reloadList()
      } else {
        message.error(res.message || '删除失败')
      }
    } catch {
      message.error('删除失败')
    }
  }

  // ─── 当前存档渲染（与后端解析协议一致：rows 二维数组 + 0-based merges）───
  // 大表（数百行 × 数十列）整块 useMemo：原因输入等高频 setState 时复用
  // 同一元素引用，React 跳过该子树协调，避免逐键重渲染整表造成卡顿
  const activePreview = useMemo(() => {
    if (!active) return null
    const activeMerges: MergedCell[] =
      (active.merges as MergedCell[] | undefined) || []
    const activeRows: CellValue[][] =
      (active.rows as CellValue[][] | undefined) || []
    const maxCols = active.col_count || 0
    const headerLabels = Array.from({ length: maxCols }, (_, i) => {
      let label = ''
      let n = i
      do {
        label = String.fromCharCode(65 + (n % 26)) + label
        n = Math.floor(n / 26) - 1
      } while (n >= 0)
      return label
    })

    /**
     * 合并信息：span>1 表示左上角需跨行/跨列；hide 表示被合并覆盖需隐藏。
     * antd 语义：被上方行合并覆盖的格用 rowSpan:0，被左侧列合并覆盖的格用
     * colSpan:0（两者混用会导致表格列错位，浏览器把无效 colspan=0 当 1 列）。
     */
    const getMergeSpan = (
      rowIdx: number,
      colIdx: number,
    ): { rowSpan: number; colSpan: number; hide?: 'row' | 'col' } | null => {
      for (const m of activeMerges) {
        if (m.s.r === rowIdx && m.s.c === colIdx) {
          return { rowSpan: m.e.r - m.s.r + 1, colSpan: m.e.c - m.s.c + 1 }
        }
        if (rowIdx >= m.s.r && rowIdx <= m.e.r && colIdx >= m.s.c && colIdx <= m.e.c) {
          if (rowIdx !== m.s.r || colIdx !== m.s.c) {
            // 纵向合并（来自上方行）→ rowSpan:0；横向合并（同行左侧）→ colSpan:0
            return rowIdx > m.s.r
              ? { rowSpan: 0, colSpan: 0, hide: 'row' }
              : { rowSpan: 0, colSpan: 0, hide: 'col' }
          }
        }
      }
      return null
    }

    const isDayNumber = (val: CellValue): boolean => {
      const s = String(val ?? '').trim()
      const n = Number(s)
      return /^\d{1,2}$/.test(s) && n >= 1 && n <= 31
    }

    const isTitleRow = (val: CellValue): boolean => {
      const s = String(val ?? '').trim()
      return /排产/.test(s) && /\d+月\d+日/.test(s) && s.length > 20
    }

    const activeColumns = headerLabels.map((col, ci) => ({
      title: col,
      dataIndex: col,
      key: col,
      // 源表里标签列可能极窄(Excel 靠文本溢出显示),预览 overflow:hidden
      // 会把它裁没,统一抬到最小 80 保证最左侧的行标题可见
      width: Math.max(active.col_widths?.[ci] || 0, 80),
      onCell: (_record: unknown, rowIndex?: number) => {
        const span = rowIndex === undefined ? undefined : getMergeSpan(rowIndex, ci)
        if (span?.hide === 'row') {
          // 被上方合并覆盖：该格并入上一行，不渲染
          return { rowSpan: 0 }
        }
        if (span?.hide === 'col') {
          // 被左侧合并覆盖：不占列
          return { colSpan: 0 }
        }
        const cellProps: TdHTMLAttributes<HTMLTableCellElement> = {}
        // 合并锚点（含空锚点）输出跨行/跨列占位：锚点不占位时，
        // 被覆盖格移除后整行会向左错位（如他汀表倒罐罐序行）
        if (span && (span.rowSpan > 1 || span.colSpan > 1)) {
          if (span.rowSpan > 1) cellProps.rowSpan = span.rowSpan
          if (span.colSpan > 1) cellProps.colSpan = span.colSpan
        }
        // 日期/标题行的居中加粗样式放在 td 上（onCell 可拿到整行记录取格值）
        const cell = (_record as Record<string, unknown> | undefined)?.[col]
        const style: CSSProperties = {}
        if (isDayNumber(cell as CellValue)) {
          style.textAlign = 'center'
          style.fontWeight = 500
        }
        if (isTitleRow(cell as CellValue)) {
          style.textAlign = 'center'
          style.fontWeight = 700
        }
        if (Object.keys(style).length) cellProps.style = style
        return cellProps
      },
      render: (cell: CellValue) => (cell ? String(cell) : ''),
    }))

    const tableData = activeRows.map((row, ri) => {
      const item: Record<string, unknown> & { key: string } = { key: `r${ri}` }
      headerLabels.forEach((col, ci) => {
        item[col] = row[ci] ?? ''
      })
      return item
    })

    return (
      <Card
        title={
          <Space>
            <span>{active.sheet_name}</span>
            <Text type="secondary" style={{ fontWeight: 400, fontSize: 12 }}>
              {active.file_name} · {active.row_count} 行 × {active.col_count} 列
            </Text>
          </Space>
        }
        extra={
          <Space size={4}>
            {canExport && (
              <Button size="small" icon={<DownloadOutlined />} href={fileDownloadUrl(active.id)}>
                下载原件
              </Button>
            )}
            <Button size="small" onClick={() => setActive(null)}>
              收起
            </Button>
          </Space>
        }
        styles={{ body: { padding: 4, overflow: 'auto' } }}
      >
        <Table
          columns={activeColumns}
          dataSource={tableData}
          loading={loadingActive}
          scroll={{ x: maxCols * 80, y: 600 }}
          pagination={false}
          size="small"
          bordered
          showHeader={false}
          className="scheduling-table"
        />
      </Card>
    )
  }, [active, loadingActive, canExport])

  const listColumns = [
    {
      // 弹性列：吸收剩余宽度，其余固定宽列贴表格右侧
      title: '文件名', dataIndex: 'file_name', key: 'file_name', ellipsis: true,
      render: (value: string, record: ScheduleExcelArchive) => (
        <Space size={6}>
          <span>{value}</span>
          {(record.history_fixes?.length ?? 0) > 0 && (
            <Tag
              color="orange"
              icon={<HistoryOutlined />}
              style={{ marginRight: 0, cursor: 'pointer' }}
              onClick={(e) => {
                e.stopPropagation()
                setViewingFixes(record.history_fixes ?? [])
                setViewingFixesFile(record.file_name)
              }}
            >
              历史修正
            </Tag>
          )}
        </Space>
      ),
    },
    { title: '工作表', dataIndex: 'sheet_name', key: 'sheet_name', width: 130 },
    {
      title: '规模', key: 'size', width: 120,
      render: (_: unknown, record: ScheduleExcelArchive) =>
        `${record.row_count} 行 × ${record.col_count} 列`,
    },
    {
      title: '编制人', dataIndex: 'created_by_name', key: 'created_by_name', width: 120,
      render: (value?: string | null) => value || '—',
    },
    {
      title: '上传时间', dataIndex: 'created_at', key: 'created_at', width: 170,
      render: (value?: string) =>
        value ? new Date(value).toLocaleString() : '',
    },
    {
      // 「查看+校验+下载原件+删除」四按钮合计约 270px，
      // 列宽不足会把删除按钮顶出单元格，留足余量
      title: '操作', key: 'actions', width: 310,
      render: (_: unknown, record: ScheduleExcelArchive) => (
        <Space size={4} onClick={(e) => e.stopPropagation()}>
          <Button size="small" icon={<EyeOutlined />} onClick={() => openArchive(record.id)}>
            查看
          </Button>
          {isFa && (
            <Button
              size="small"
              icon={<FileSearchOutlined />}
              loading={validatingId === record.id}
              onClick={() => void openValidation(record.id, record.file_name)}
            >
              校验
            </Button>
          )}
          {canExport && (
            <Button size="small" icon={<DownloadOutlined />} href={fileDownloadUrl(record.id)}>
              下载原件
            </Button>
          )}
          {canDelete && (
            <Popconfirm
              title="删除该排产存档？"
              description="删除后不可恢复，原件文件一并移除。"
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => removeArchive(record.id)}
            >
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div className="p-6">
      <BoardNavBlocks hideCodes={hideCodes} />
      <style>{`
        .scheduling-table .ant-table-cell {
          padding: 6px 8px !important;
          font-size: 12px;
          line-height: 1.6;
          background: transparent !important;
          white-space: nowrap;
          overflow: hidden;
        }
        .scheduling-table .ant-table-row {
          height: 34px;
        }
      `}</style>
      <div className="mb-6">
        <Title level={4} style={{ margin: 0 }}>
          <ScheduleOutlined className="mr-2" />排产计划
        </Title>
        <Text type="secondary">
          上传排产 Excel 存档至系统，保留合并单元格与原始排版，可回看历史与下载原件
        </Text>
      </div>

      {/* 上传 */}
      <Row gutter={16} className="mb-6">
        <Col span={18}>
          <Dragger
            accept=".xlsx,.xls"
            multiple={false}
            showUploadList={false}
            disabled={!canBulkImport || uploading}
            beforeUpload={handleUpload}
          >
            <p className="text-4xl mb-2"><InboxOutlined /></p>
            <p className="text-base">
              上传排产计划 Excel 文件（{uploading ? '上传中…' : '点击或拖拽'}）
            </p>
            <p className="text-sm text-gray-400">
              保持原始格式展示，不转换字段；上传后自动存入系统
            </p>
            <p className="text-sm text-gray-400">
              仅支持 .xlsx / .xls，文件大小不超过 1MB
            </p>
          </Dragger>
        </Col>
        <Col span={6}>
          <Card size="small" styles={{ body: { padding: 14 } }}>
            <div className="text-xs text-gray-500">
              <p className="mb-1 font-bold text-gray-300">使用说明</p>
              <p>上传 .xlsx / .xls 文件，不设行数上限</p>
              <p>展示第一个工作表，保留原始行列结构</p>
              <p>合并单元格自动还原，样式不还原</p>
              <p>存档可回看历史、下载原件</p>
            </div>
          </Card>
        </Col>
      </Row>

      {/* 排产约束（仅 FA）：校验与后续自动排产共用的工艺参数 */}
      {isFa && (
        <Card
          className="mb-6"
          size="small"
          title="排产约束"
          styles={{ body: { padding: 14 } }}
          extra={
            canSync ? (
              <Button size="small" icon={<EditOutlined />} onClick={() => void openConstraintModal()}>
                编辑
              </Button>
            ) : null
          }
        >
          <Space size={24} wrap className="mb-2">
            <Text>标准培养周期：<Text strong>{constraintText(constraints?.standard_cycle_hours, 'h')}</Text></Text>
            <Text>周期容差：<Text strong>{constraintText(constraints?.cycle_tolerance_hours, 'h')}</Text></Text>
            <Text>最大培养周期：<Text strong>{constraintText(constraints?.max_cycle_hours, 'h')}</Text></Text>
            <Text>罐周转时间：<Text strong>{constraintText(constraints?.turnaround_hours, 'h')}</Text></Text>
            <Text>月计划放罐：<Text strong>{constraintText(constraints?.monthly_dump_target, ' 批')}</Text></Text>
          </Space>
          <Text type="secondary" className="text-xs">
            排产校验与自动排产使用的工艺参数；未配置的项目对应检查自动跳过（培养周期超上限、周转不足、批数核对等）。
          </Text>
        </Card>
      )}

      {/* 历史存档列表 */}
      <Card
        className="mb-6"
        title={
          <Space size={8}>
            <span>历史存档</span>
            {fixTotal > 0 && (
              <Tag color="orange" icon={<HistoryOutlined />} style={{ fontWeight: 400 }}>
                本产品累计历史修正 {fixTotal} 次
              </Tag>
            )}
          </Space>
        }
        extra={
          <Button size="small" icon={<ReloadOutlined />} onClick={() => reloadList()}>
            刷新
          </Button>
        }
        styles={{ body: { padding: 8 } }}
      >
        <Table
          rowKey="id"
          size="small"
          loading={loadingList}
          columns={listColumns}
          dataSource={archives}
          pagination={{ pageSize: 8, showSizeChanger: false }}
          onRow={(record) => ({
            onClick: () => openArchive(record.id),
            style: { cursor: 'pointer' },
          })}
          locale={{ emptyText: '暂无存档，上传排产 Excel 后将在这里出现' }}
        />
      </Card>

      {/* 当前展示 */}
      {activePreview}
      {/* 历史改动确认：默认已冻结，有权限者可填原因以新文件修正 */}
      <Modal
        open={fixModalOpen}
        title="检测到「今天之前」的历史改动"
        onCancel={() => setFixModalOpen(false)}
        onOk={confirmHistoryFix}
        okText="确认修正历史"
        cancelText="保留历史"
        confirmLoading={fixSubmitting}
        okButtonProps={{ danger: true, disabled: !fixReason.trim() }}
        width={760}
      >
        <Alert
          type="warning"
          showIcon
          className="!mb-3"
          title="历史列已冻结，以下改动已放弃；填写原因后可提交修正并记录审计。"
          description="重复存档默认冻结历史列，以下改动已被放弃、原存档保持不变。确认为有意修正时，请填写原因后提交（将写入审计日志）。"
        />
        <MergeChangeTable changes={mergeReport?.discarded_changes ?? EMPTY_CHANGES} />
        {mergeReport?.truncated && (
          <Text type="secondary">历史改动超过 200 处，仅展示前 200 处。</Text>
        )}
        <TextArea
          className="mt-3"
          rows={2}
          value={fixReason}
          onChange={(e) => setFixReason(e.target.value)}
          placeholder="请填写历史修正原因（必填，例如：排产表笔误，DR-26013 实际进 B404）"
          maxLength={255}
        />
      </Modal>
      {/* 修正记录查看：从历史存档列表的"历史修正"标记进入 */}
      <Modal
        open={viewingFixes !== null}
        title={`历史修正记录：${viewingFixesFile}`}
        footer={null}
        onCancel={() => setViewingFixes(null)}
        width={760}
      >
        {(viewingFixes ?? []).map((fix, index) => (
          <div key={index} className={index > 0 ? 'mt-4' : ''}>
            <div className="mb-2 text-xs text-gray-500">
              {fix.fixed_at ? new Date(fix.fixed_at).toLocaleString() : '—'}
              {' · '}
              {fix.fixed_by_name || '未知用户'}
              {' · 原因：'}
              {fix.reason || '—'}
              {(fix.changes_total ?? 0) > (fix.changes?.length ?? 0) &&
                `（仅展示前 ${fix.changes?.length ?? 0} 处，共 ${fix.changes_total} 处）`}
            </div>
            <MergeChangeTable changes={fix.changes ?? EMPTY_CHANGES} />
          </div>
        ))}
      </Modal>
      {/* 排产校验报告：上传后自动弹出，或从存档行「校验」进入；只提醒不拦截 */}
      <Modal
        open={validation !== null}
        title={`排产校验：${validationFile}`}
        footer={null}
        onCancel={() => setValidation(null)}
        width={880}
      >
        {validation?.message ? (
          <Alert type="info" showIcon className="!mb-3" title={validation.message} />
        ) : (
          <div className="mb-3">
            <Space size={8} wrap>
              <Tag color="orange">需确认 {validation?.summary?.warn ?? 0} 项</Tag>
              <Tag color="blue">提示 {validation?.summary?.info ?? 0} 项</Tag>
              <Text type="secondary" className="text-xs">
                仅校验 {validation?.scope?.from ? validation.scope.from.slice(5) : '今天'} 及以后的排产；调整约束后重新点「校验」即可按新参数复查
              </Text>
            </Space>
          </div>
        )}
        <ValidationIssueTable issues={validation?.issues ?? []} />
      </Modal>
      {/* 排产约束编辑：canSync（sync_config 敏感操作）门控 */}
      <Modal
        open={constraintModalOpen}
        title="编辑排产约束"
        onCancel={() => setConstraintModalOpen(false)}
        onOk={() => void submitConstraints()}
        okText="保存"
        cancelText="取消"
        confirmLoading={savingConstraints}
        width={560}
      >
        <div className="mb-3">
          <Space size={16} wrap>
            <span>
              标准培养周期(h)：
              <InputNumber
                className="ml-1"
                min={0}
                max={10000}
                step={0.5}
                placeholder="未配置"
                value={constraintDraft?.standard_cycle_hours ?? null}
                onChange={(v) =>
                  setConstraintDraft((prev) =>
                    prev ? { ...prev, standard_cycle_hours: v } : prev,
                  )
                }
              />
            </span>
            <span>
              周期容差(h)：
              <InputNumber
                className="ml-1"
                min={0}
                max={1000}
                step={0.5}
                placeholder="未配置"
                value={constraintDraft?.cycle_tolerance_hours ?? null}
                onChange={(v) =>
                  setConstraintDraft((prev) =>
                    prev ? { ...prev, cycle_tolerance_hours: v } : prev,
                  )
                }
              />
            </span>
          </Space>
        </div>
        <div className="mb-3">
          <Space size={16} wrap>
            <span>
              最大培养周期(h)：
              <InputNumber
                className="ml-1"
                min={0}
                max={10000}
                step={0.5}
                placeholder="未配置"
                value={constraintDraft?.max_cycle_hours ?? null}
                onChange={(v) =>
                  setConstraintDraft((prev) =>
                    prev ? { ...prev, max_cycle_hours: v } : prev,
                  )
                }
              />
            </span>
            <span>
              罐周转时间(h)：
              <InputNumber
                className="ml-1"
                min={0}
                max={1000}
                step={0.5}
                placeholder="未配置"
                value={constraintDraft?.turnaround_hours ?? null}
                onChange={(v) =>
                  setConstraintDraft((prev) =>
                    prev ? { ...prev, turnaround_hours: v } : prev,
                  )
                }
              />
            </span>
          </Space>
        </div>
        <div className="mb-3">
          月计划放罐(批)：
          <InputNumber
            className="ml-1"
            min={0}
            max={1000}
            step={1}
            precision={0}
            placeholder="未配置"
            value={constraintDraft?.monthly_dump_target ?? null}
            onChange={(v) =>
              setConstraintDraft((prev) =>
                prev ? { ...prev, monthly_dump_target: v } : prev,
              )
            }
          />
        </div>
        <Alert
          type="info"
          showIcon
          title="留空的项目对应校验自动跳过；标准周期+容差用于识别有意延长培养，最大周期为工艺上限。"
        />
      </Modal>
    </div>
  )
}
