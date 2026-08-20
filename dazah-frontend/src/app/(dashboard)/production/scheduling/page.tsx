'use client'

import { useState } from 'react'
import {Card, Typography, Upload, Table, App, Row, Col,} from 'antd'
import {ScheduleOutlined, InboxOutlined,} from '@ant-design/icons'
import * as XLSX from 'xlsx'

const { Title, Text } = Typography
const { Dragger } = Upload

// ─── 合并单元格信息 ───
interface MergedCell {
  s: { r: number; c: number }; e: { r: number; c: number }
}

export default function SchedulingPage() {
  const { message } = App.useApp()
  const [sheetName, setSheetName] = useState('')
  const [headers, setHeaders] = useState<string[]>([])
  const [data, setData] = useState<any[]>([])
  const [merges, setMerges] = useState<MergedCell[]>([])
  const [, setColWidths] = useState<number[]>([])
  const [loading, setLoading] = useState(false)

  const handleUpload = (file: File) => {
    setLoading(true)
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const wb = XLSX.read(e.target?.result, { type: 'binary', cellDates: false })
        const wsname = wb.SheetNames[0]
        const ws = wb.Sheets[wsname]
        setSheetName(wsname)

        // 获取合并单元格
        const sheetMerges: MergedCell[] = ws['!merges'] || []
        setMerges(sheetMerges)

        // 转为二维数组，保留所有空格
        const rows: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '', blankrows: true })

        // 确定实际列数
        const maxCols = Math.max(...rows.map(r => r.length), 1)
        const colWidthsArr: number[] = ws['!cols']?.map((c: any) => c.wch || 80) || Array(maxCols).fill(80)

        // 补齐每行到相同列数
        const padded = rows.map(r => {
          const arr = [...r]
          while (arr.length < maxCols) arr.push('')
          return arr
        })

        // 取前 100 行（避免过大）
        const displayRows = padded.slice(0, 250)

        // 生成列标题 (A, B, C, ...)
        const headerLabels = Array.from({ length: maxCols }, (_, i) => {
          let label = ''; let n = i
          do { label = String.fromCharCode(65 + (n % 26)) + label; n = Math.floor(n / 26) - 1 } while (n >= 0)
          return label
        })
        setHeaders(headerLabels)
        setColWidths(colWidthsArr)

        // 转为 Table 数据
        const tableData = displayRows.map((row, ri) => {
          const item: any = { key: `r${ri}`, _row: ri }
          headerLabels.forEach((col, ci) => {
            item[col] = { value: row[ci] ?? '', row: ri, col: ci }
          })
          return item
        })
        setData(tableData)

        message.success(`已加载: ${wsname}，${displayRows.length} 行 × ${maxCols} 列`)
      } catch (err: any) {
        message.error('文件解析失败: ' + (err.message || ''))
      } finally {
        setLoading(false)
      }
    }
    reader.onerror = () => { message.error('文件读取失败'); setLoading(false) }
    reader.readAsBinaryString(file)
    return false
  }

  // ─── 检查单元格是否是合并区域的左上角 ───
  const getMergeSpan = (rowIdx: number, colIdx: number): { rowSpan: number; colSpan: number } | null => {
    for (const m of merges) {
      if (m.s.r === rowIdx && m.s.c === colIdx) {
        return { rowSpan: m.e.r - m.s.r + 1, colSpan: m.e.c - m.s.c + 1 }
      }
      // 在合并区域内但不是左上角 → 隐藏
      if (rowIdx >= m.s.r && rowIdx <= m.e.r && colIdx >= m.s.c && colIdx <= m.e.c) {
        if (rowIdx !== m.s.r || colIdx !== m.s.c) {
          return { rowSpan: 0, colSpan: 0 } // 隐藏
        }
      }
    }
    return null
  }

  const isDayNumber = (val: any): boolean => {
    const s = String(val ?? '').trim()
    const n = Number(s)
    return /^\d{1,2}$/.test(s) && n >= 1 && n <= 31
  }

  // 判断是否为标题行（含"排产"或跨月日期范围）
  const isTitleRow = (val: any): boolean => {
    const s = String(val ?? '').trim()
    return /排产/.test(s) && /\d+月\d+日/.test(s) && s.length > 20
  }

  // ─── 表格列 ───
  const columns = headers.map((col, ci) => ({
    title: col,
    dataIndex: col,
    key: col,
    width: 80,
    render: (cell: { value: any; row: number; col: number }) => {
      if (!cell) return ''
      const span = getMergeSpan(cell.row, cell.col)
      if (span && span.rowSpan === 0 && span.colSpan === 0) {
        return { children: '', props: { colSpan: 0 } }
      }
      const val = cell.value; const display = val != null && val !== '' ? String(val) : ''
      const cellProps: any = { style: {} }

      if (span && (span.rowSpan > 1 || span.colSpan > 1)) {
        if (span.rowSpan > 1) cellProps.rowSpan = span.rowSpan
        if (span.colSpan > 1) cellProps.colSpan = span.colSpan
      }

      // 日期数字居中
      if (isDayNumber(val)) {
        cellProps.style.textAlign = 'center'
        cellProps.style.fontWeight = 500
      }

      // 标题行：居中、大字、加宽
      if (isTitleRow(val)) {
        cellProps.style.textAlign = 'center'
        cellProps.style.fontSize = '15px'
        cellProps.style.fontWeight = 700
        cellProps.style.padding = '10px 8px'
        cellProps.style.whiteSpace = 'nowrap'
      }

      return { children: display, props: cellProps }
    },
  }))

  return (
    <div className="p-6">
      <style>{`
        .scheduling-table .ant-table-cell {
          padding: 6px 8px !important;
          font-size: 12px;
          line-height: 1.6;
          background: transparent !important;
        }
        .scheduling-table .ant-table-row {
          height: 34px;
        }
      `}</style>
      <div className="mb-6">
        <Title level={4} style={{ margin: 0 }}><ScheduleOutlined className="mr-2" />排产计划</Title>
        <Text type="secondary">上传排产 Excel，原样展示（保留合并单元格与原始排版）</Text>
      </div>

      {/* 上传 */}
      <Row gutter={16} className="mb-6">
        <Col span={18}>
          <Dragger accept=".xlsx,.xls" multiple={false} showUploadList={false} beforeUpload={handleUpload}>
            <p className="text-4xl mb-2"><InboxOutlined /></p>
            <p className="text-base">上传排产计划 Excel 文件</p>
            <p className="text-sm text-gray-400">保持原始格式展示，不转换字段</p>
          </Dragger>
        </Col>
        <Col span={6}>
          <Card size="small" styles={{ body: { padding: 14 } }}>
            <div className="text-xs text-gray-500">
              <p className="mb-1 font-bold text-gray-300">使用说明</p>
              <p>上传 .xlsx / .xls 文件</p>
              <p>保留原始行列表格结构</p>
              <p>合并单元格自动还原</p>
              <p>最大显示 100 行</p>
            </div>
          </Card>
        </Col>
      </Row>

      {/* 表格展示 */}
      {data.length > 0 && (
        <Card
          title={<span>{sheetName}</span>}
          styles={{ body: { padding: 4, overflow: 'auto' } }}
        >
          <Table
            columns={columns}
            dataSource={data}
            loading={loading}
            scroll={{ x: headers.length * 80, y: 600 }}
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
