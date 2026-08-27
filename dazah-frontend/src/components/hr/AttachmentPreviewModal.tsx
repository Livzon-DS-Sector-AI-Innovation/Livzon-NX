'use client'

import { Modal, Spin, Empty } from 'antd'
import { FileTextOutlined, TableOutlined } from '@ant-design/icons'
import type { AttachmentPreview, AttachmentPreviewTable } from '@/types/hr'

/** 按内容长度估算列宽（百分比），序号类窄列、长文本列自适应. */
function colWidths(header: string[] | undefined, rows: string[][]): string[] {
  const n = Math.max(header?.length || 0, ...(rows.slice(0, 60).map((r) => r.length) || [0]), 1)
  const lens = Array(n).fill(2) as number[]
  const scan = (cells: string[]) => {
    for (let i = 0; i < n; i++) {
      const len = Math.min(String(cells[i] ?? '').length, 30)
      if (len > lens[i]) lens[i] = len
    }
  }
  if (header) scan(header)
  rows
    .slice(0, 60)
    .filter((r) => !isRemarkRow(r))
    .forEach(scan)
  const total = lens.reduce((a, b) => a + b, 0) || n
  return lens.map((l) => `${Math.max(8, Math.round((l / total) * 100))}%`)
}

/** 备注行（首格以"备注"开头、其余为空）→ 整行合并显示. */
function isRemarkRow(cells: string[]): boolean {
  const first = String(cells[0] ?? '').trim()
  return first.startsWith('备注') && cells.slice(1).every((c) => !String(c ?? '').trim())
}

function GridTable({ header, rows }: { header?: string[]; rows?: string[][] }) {
  const body = rows || []
  const head = header && header.length ? header : null
  const widths = colWidths(head || undefined, body)
  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden mb-4">
      <table className="w-full border-collapse text-xs" style={{ tableLayout: 'fixed' }}>
        <colgroup>
          {widths.map((w, i) => (
            <col key={i} style={{ width: w }} />
          ))}
        </colgroup>
        {head && (
          <thead>
            <tr className="bg-blue-50/70">
              {head.map((h, i) => (
                <th
                  key={i}
                  className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold text-[var(--color-charcoal)] whitespace-nowrap overflow-hidden text-ellipsis"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {body.map((r, i) =>
            isRemarkRow(r) ? (
              <tr key={i} className="bg-amber-50/60">
                <td colSpan={widths.length} className="border-t border-gray-100 px-2 py-1.5 text-gray-600">
                  {r[0]}
                </td>
              </tr>
            ) : (
              <tr key={i} className={i % 2 === 1 ? 'bg-gray-50/60' : 'bg-white'}>
                {r.map((c, j) => (
                  <td
                    key={j}
                    className="border-t border-gray-100 px-2 py-1.5 align-top text-gray-700 break-words"
                  >
                    {c}
                  </td>
                ))}
              </tr>
            )
          )}
        </tbody>
      </table>
    </div>
  )
}

function TableBlock({ table }: { table: AttachmentPreviewTable }) {
  return (
    <div className="mb-4">
      {table.title && (
        <h4 className="text-sm font-semibold mb-2 flex items-center gap-1">
          <TableOutlined className="text-blue-500" />
          {table.title}
        </h4>
      )}
      <GridTable header={table.header} rows={table.rows} />
    </div>
  )
}

interface Props {
  open: boolean
  title: string
  loading: boolean
  preview: AttachmentPreview | null
  onClose: () => void
}

/** 附件预览 Modal：渲染后端结构化的 table/doc/tables 三种形态. */
export default function AttachmentPreviewModal({ open, title, loading, preview, onClose }: Props) {
  // 内容首块若与标题重复（如"附件五"标题段），跳过避免重复展示
  const blocks = (preview?.blocks || []).filter(
    (b, i) => !(i === 0 && b.type === 'p' && (title || '').includes((b.text || '').trim()) && (b.text || '').trim().length <= 30)
  )

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={960}
      title={
        <span className="flex items-center gap-2">
          <FileTextOutlined className="text-blue-500" />
          {title}
        </span>
      }
      destroyOnHidden
    >
      <Spin spinning={loading}>
        <div className="max-h-[70vh] overflow-auto pr-2 pt-2">
          {!preview ? (
            !loading && <Empty description="暂无预览内容" />
          ) : preview.kind === 'table' ? (
            <GridTable header={preview.header} rows={preview.rows} />
          ) : preview.kind === 'tables' ? (
            (preview.tables || []).map((t, i) => <TableBlock key={i} table={t} />)
          ) : blocks.length === 0 ? (
            <Empty description="暂无预览内容" />
          ) : (
            blocks.map((b, i) =>
              b.type === 'p' ? (
                <p key={i} className="text-sm my-1.5 whitespace-pre-wrap text-gray-700">
                  {b.text || ''}
                </p>
              ) : (
                <GridTable key={i} rows={b.rows || []} />
              )
            )
          )}
        </div>
      </Spin>
    </Modal>
  )
}
