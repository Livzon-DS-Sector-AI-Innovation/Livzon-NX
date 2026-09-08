'use client'

import { useCallback, useEffect, useState } from 'react'
import { Card, Typography, Upload, Table, App, Row, Col, Button, Popconfirm, Space } from 'antd'
import { ScheduleOutlined, InboxOutlined, ReloadOutlined, DownloadOutlined, DeleteOutlined, EyeOutlined } from '@ant-design/icons'
import {
  deleteScheduleExcelArchive,
  getScheduleExcelArchive,
  getScheduleExcelArchives,
  uploadScheduleExcel,
} from '@/actions/production'
import type { ScheduleExcelArchive } from '@/types/production'

const { Title, Text } = Typography
const { Dragger } = Upload

interface MergedCell {
  s: { r: number; c: number }
  e: { r: number; c: number }
}

/** 单元格渲染值：后端子端统一为 string */
type CellValue = string

export default function SchedulingPage() {
  const { message } = App.useApp()
  const [archives, setArchives] = useState<ScheduleExcelArchive[]>([])
  const [loadingList, setLoadingList] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [active, setActive] = useState<ScheduleExcelArchive | null>(null)
  const [loadingActive, setLoadingActive] = useState(false)

  const reloadList = useCallback(async () => {
    setLoadingList(true)
    try {
      const res = await getScheduleExcelArchives(1, 50)
      if (res.code === 200) setArchives(res.data || [])
    } catch {
      message.error('加载历史存档失败')
    } finally {
      setLoadingList(false)
    }
  }, [message])

  useEffect(() => {
    void reloadList()
  }, [reloadList])

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await uploadScheduleExcel(formData)
      if (res.code === 200 && res.data?.id) {
        message.success(`已存档：${res.data.file_name}`)
        setActive(res.data)
        await reloadList()
      } else {
        message.error(res.message || '上传失败')
      }
    } catch {
      message.error('上传失败')
    } finally {
      setUploading(false)
    }
    return false
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

  const fileDownloadUrl = (archiveId: string) =>
    `/api/v1/production/schedule-excel/${archiveId}/file`

  // ─── 当前存档渲染（与后端解析协议一致：rows 二维数组 + 0-based merges）───

  const activeMerges: MergedCell[] = (active?.merges as MergedCell[] | undefined) || []
  const activeRows: CellValue[][] = (active?.rows as CellValue[][] | undefined) || []
  const maxCols = active?.col_count || 0
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
    width: active?.col_widths?.[ci] || 80,
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

  const listColumns = [
    { title: '文件名', dataIndex: 'file_name', key: 'file_name', ellipsis: true },
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
          <Button size="small" icon={<DownloadOutlined />} href={fileDownloadUrl(record.id)}>
            下载原件
          </Button>
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
        </Space>
      ),
    },
  ]

  return (
    <div className="p-6">
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
            disabled={uploading}
            beforeUpload={handleUpload}
          >
            <p className="text-4xl mb-2"><InboxOutlined /></p>
            <p className="text-base">
              上传排产计划 Excel 文件（{uploading ? '上传中…' : '点击或拖拽'}）
            </p>
            <p className="text-sm text-gray-400">
              保持原始格式展示，不转换字段；上传后自动存入系统
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
        title="历史存档"
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
      {active && (
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
              <Button size="small" icon={<DownloadOutlined />} href={fileDownloadUrl(active.id)}>
                下载原件
              </Button>
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
      )}
    </div>
  )
}
