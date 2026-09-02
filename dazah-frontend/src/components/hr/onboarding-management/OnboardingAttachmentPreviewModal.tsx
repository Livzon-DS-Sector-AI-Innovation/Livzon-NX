'use client'

import { useState } from 'react'
import { App, Modal, Spin, Table, Typography } from 'antd'
import * as XLSX from 'xlsx'
import mammoth from 'mammoth/mammoth.browser.js'

interface Props {
  open: boolean
  fileName: string
  blob: Blob | null
  onClose: () => void
}

const DOCX_EXT = /\.(docx|doc)$/i
const XLSX_EXT = /\.(xlsx|xls|csv)$/i
const MAX_SHEET_ROWS = 500

interface SheetRow {
  key: number
  [col: number]: unknown
}

export default function OnboardingAttachmentPreviewModal({ open, fileName, blob, onClose }: Props) {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [sheetData, setSheetData] = useState<{ columns: Array<{ key: string; title: string }>; rows: SheetRow[] } | null>(null)
  const [docxHtml, setDocxHtml] = useState<string | null>(null)
  const [previewType, setPreviewType] = useState<'pdf' | 'docx' | 'xlsx' | 'other'>('other')

  const doRender = async () => {
    if (!blob) return
    setLoading(true)
    setSheetData(null)
    setDocxHtml(null)
    setPreviewType('other')
    try {
      if (DOCX_EXT.test(fileName)) {
        setPreviewType('docx')
        if (/\.docx$/i.test(fileName)) {
          // mammoth 浏览器版（主入口 lib/index.js 为 Node API，浏览器打包会卡死）
          const { value } = await mammoth.convertToHtml({
            arrayBuffer: await blob.arrayBuffer(),
          })
          setDocxHtml(
            '<style>table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px 8px;font-size:13px}</style>' +
              value,
          )
        } else {
          // 老 .doc 二进制格式：mammoth 不支持，降级提示
          setPreviewType('other')
        }
      } else if (XLSX_EXT.test(fileName)) {
        setPreviewType('xlsx')
        const buf = await blob.arrayBuffer()
        // CSV 常见 GBK 编码：UTF-8 解码出现替换符时改用 GBK
        let wb: XLSX.WorkBook
        if (/\.csv$/i.test(fileName)) {
          const utf8Text = new TextDecoder('utf-8').decode(buf)
          const content = utf8Text.includes('\uFFFD')
            ? new TextDecoder('gbk').decode(buf)
            : utf8Text
          wb = XLSX.read(content, { type: 'string' })
        } else {
          wb = XLSX.read(buf)
        }
        const ws = wb.Sheets[wb.SheetNames[0]]
        const raw: unknown[][] = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' })
        const header = raw[0] || []
        const body = raw.slice(1, MAX_SHEET_ROWS + 1)
        setSheetData({
          columns: header.map((h: unknown, i: number) => ({
            title: String(h ?? `列${i + 1}`),
            dataIndex: String(i),
            key: String(i),
            ellipsis: true,
            width: 140,
          })),
          rows: body.map((r, i) => {
            const row: SheetRow = { key: i }
            r.forEach((v, j) => { row[j] = v })
            return row
          }),
        })
      } else if (fileName.toLowerCase().endsWith('.pdf')) {
        setPreviewType('pdf')
      }
    } catch (e) {
      console.error('附件预览渲染失败:', e)
      message.error(e?.message || '预览失败')
      setPreviewType('other')
    } finally {
      setLoading(false)
    }
  }

  const pdfUrl = previewType === 'pdf' && blob ? URL.createObjectURL(blob) : null

  return (
    <Modal
      title={`预览 - ${fileName}`}
      open={open}
      onCancel={onClose}
      afterOpenChange={(isOpen) => {
        // Modal 内容挂载完成后再渲染，避免容器时序问题
        if (isOpen) void doRender()
      }}
      footer={null}
      width={900}
      destroyOnHidden
      styles={{ body: { height: '70vh', overflow: 'auto' } }}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}>
          <Spin description="文档较大，正在渲染..." />
        </div>
      ) : (
        <>
          {previewType === 'pdf' && pdfUrl && (
            <iframe src={pdfUrl} style={{ width: '100%', height: '100%', border: 'none' }} title={fileName} />
          )}
          {previewType === 'docx' && docxHtml && (
            <div
              className="docx-preview"
              style={{ width: '100%', minHeight: '60vh', background: '#fff', overflow: 'auto' }}
              dangerouslySetInnerHTML={{ __html: docxHtml }}
            />
          )}
          {previewType === 'xlsx' && sheetData && (
            <Table
              rowKey="key"
              size="small"
              columns={sheetData.columns}
              dataSource={sheetData.rows}
              pagination={false}
              scroll={{ x: 'max-content', y: '60vh' }}
            />
          )}
          {previewType === 'other' && (
            <Typography.Text type="secondary">
              该文件类型暂不支持在线预览，可下载后查看：{fileName}
            </Typography.Text>
          )}
        </>
      )}
    </Modal>
  )
}