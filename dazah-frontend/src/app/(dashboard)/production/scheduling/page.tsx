'use client'

import { memo, useCallback, useEffect, useMemo, useState } from 'react'
import { Card, Typography, Upload, Table, App, Row, Col, Button, Popconfirm, Space, Modal, Input, Alert, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ScheduleOutlined, InboxOutlined, ReloadOutlined, DownloadOutlined, DeleteOutlined, EyeOutlined, HistoryOutlined } from '@ant-design/icons'
import {
  deleteScheduleExcelArchive,
  getScheduleExcelArchive,
  getScheduleExcelArchives,
  uploadScheduleExcel,
} from '@/actions/production'
import type {
  ScheduleExcelArchive,
  ScheduleHistoryFix,
  ScheduleMergeChange,
  ScheduleMergeReport,
} from '@/types/production'
import BoardNavBlocks from '@/components/production/board-nav-blocks'
import { useProductContextStore } from '@/stores/product-context'
import { usePermission } from '@/hooks/usePermission'
import { PRODUCTION_PAGE_KEYS, useProductionPermissions } from '@/components/production/useProductionPermissions'

const { Title, Text } = Typography
const { Dragger } = Upload
const { TextArea } = Input

// 排产按产品存档,汇总(五产线聚合)没有排产数据,本页隐藏该入口
const SCHEDULING_HIDE_CODES: readonly string[] = ['SUMMARY']

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

function fileDownloadUrl(archiveId: string) {
  return `/api/v1/production/schedule-excel/${archiveId}/file`
}

export default function SchedulingPage() {
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
  const { has } = usePermission()
  const canFixHistory = has('production:schedule-archive')
  const { canDelete, canBulkImport, canExport } = useProductionPermissions(
    PRODUCTION_PAGE_KEYS.scheduling,
  )

  const productCode = useProductContextStore((s) => s.productCode)

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
      render: (cell: CellValue, _record: unknown, rowIndex: number) => {
        const span = getMergeSpan(rowIndex, ci)
        if (span?.hide === 'row') {
          // 被上方合并覆盖：该格并入上一行，标记 rowSpan:0
          return { children: '', props: { rowSpan: 0 } }
        }
        if (span?.hide === 'col') {
          // 被左侧合并覆盖：不占列
          return { children: '', props: { colSpan: 0 } }
        }
        if (!cell) return ''
        const display = cell !== '' ? String(cell) : ''
        const cellProps: Record<string, unknown> = { style: {} as Record<string, unknown> }
        const style = cellProps.style as Record<string, unknown>

        if (span && (span.rowSpan > 1 || span.colSpan > 1)) {
          if (span.rowSpan > 1) cellProps.rowSpan = span.rowSpan
          if (span.colSpan > 1) cellProps.colSpan = span.colSpan
        }

        if (isDayNumber(cell)) {
          style.textAlign = 'center'
          style.fontWeight = 500
        }

        if (isTitleRow(cell)) {
          // 标题行仅加粗居中，不放大字号/内边距，保持行高与数据行一致
          style.textAlign = 'center'
          style.fontWeight = 700
        }

        return { children: display, props: cellProps }
      },
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
  }, [active, loadingActive])

  const listColumns = [
    {
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
      title: '操作', key: 'actions', width: 210,
      render: (_: unknown, record: ScheduleExcelArchive) => (
        <Space size={4} onClick={(e) => e.stopPropagation()}>
          <Button size="small" icon={<EyeOutlined />} onClick={() => openArchive(record.id)}>
            查看
          </Button>
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
      <BoardNavBlocks hideCodes={SCHEDULING_HIDE_CODES} />
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
          message="重复存档默认冻结历史列，以下改动已被放弃、原存档保持不变。确认为有意修正时，请填写原因后提交（将写入审计日志）。"
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
    </div>
  )
}
