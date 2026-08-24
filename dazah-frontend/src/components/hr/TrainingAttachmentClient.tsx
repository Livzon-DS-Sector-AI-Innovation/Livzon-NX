'use client'

import { useState, useEffect, useRef } from 'react'
import { Button, Card, Input, Table, App, Tag } from 'antd'
import { PlusOutlined, DeleteOutlined, DownloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { TrainingSessionData, TrainingDocExporter, ExportedDoc } from '@/types/hr'
import { generateTrainingAttachment } from '@/actions/hr'
import { downloadBytes } from '@/lib/download'

/** 培训附件行（UI 类型：表格行编辑状态，非后端 API 类型） */
interface TrainingAttachmentRow {
  uid: string
  name: string
  code: string | null
}

let uidCounter = 0
const nextUid = () => `at-${++uidCounter}-${Date.now()}`

interface Props {
  sessionData: TrainingSessionData
  /** 勾选的附件培训内容（session.checked_content），变化时自动同步 */
  checkedContent?: { name: string; code: string | null }[] | null
  /** 恢复已保存的附件草稿 */
  initialPayload?: { items: TrainingAttachmentRow[] } | null
  registerDocBuilder?: (type: string, fn: () => Record<string, unknown> | null) => void
  registerExporter?: (type: string, fn: TrainingDocExporter) => void
}

export default function TrainingAttachmentClient({
  sessionData,
  checkedContent,
  initialPayload,
  registerDocBuilder,
  registerExporter,
}: Props) {
  const { message } = App.useApp()
  const [rows, setRows] = useState<TrainingAttachmentRow[]>(() =>
    initialPayload?.items?.length
      ? initialPayload.items.map((r) => ({ uid: nextUid(), name: r.name, code: r.code }))
      : (checkedContent || []).map((c) => ({ uid: nextUid(), name: c.name, code: c.code })),
  )
  const [exporting, setExporting] = useState(false)
  // 已自动同步的内容标识：有已存草稿时首次不覆盖；之后勾选内容变化才整体替换
  const lastAppliedRef = useRef(
    initialPayload?.items?.length ? JSON.stringify(checkedContent || []) : '',
  )

  // 勾选附件/新员工教材后自动录入（内容变化时整体替换；用户手动编辑不触发）
  useEffect(() => {
    const key = JSON.stringify(checkedContent || [])
    if (!key || key === lastAppliedRef.current) return
    lastAppliedRef.current = key
    setRows((checkedContent || []).map((c) => ({ uid: nextUid(), name: c.name, code: c.code })))
  }, [checkedContent])

  // 异步恢复已保存草稿（会话恢复完成后 initialPayload 才到达，此时以保存内容为准）
  useEffect(() => {
    if (!initialPayload?.items?.length) return
    const key = JSON.stringify(initialPayload.items)
    if (key === lastAppliedRef.current) return
    lastAppliedRef.current = key
    setRows(initialPayload.items.map((r) => ({ uid: nextUid(), name: r.name, code: r.code })))
  }, [initialPayload])

  // 有效行：名称非空（空行不参与保存/导出）
  const validRows = rows.filter((r) => r.name.trim())

  const handleNameChange = (idx: number, value: string) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, name: value } : r)))
  }
  const handleCodeChange = (idx: number, value: string) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, code: value } : r)))
  }
  const handleAdd = () => setRows((prev) => [...prev, { uid: nextUid(), name: '', code: null }])
  const handleRemove = (idx: number) => setRows((prev) => prev.filter((_, i) => i !== idx))

  // 注册草稿 builder（纳入顶部"保存"统一保存/恢复）
  useEffect(() => {
    registerDocBuilder?.('attachment', () =>
      validRows.length
        ? { items: validRows.map((r) => ({ name: r.name.trim(), code: r.code?.trim() || null })) }
        : null,
    )
  })

  // 导出培训附件 Word（模板保真：附件： + 序号/文件名称/文件编号表格）
  const buildExportEntries = async (): Promise<ExportedDoc[] | null> => {
    if (!validRows.length) return null
    const { bytes } = await generateTrainingAttachment({
      items: validRows.map((r) => ({ name: r.name.trim(), code: r.code?.trim() || null })),
    })
    const dateStr = (sessionData.training_date || '').replace(/-/g, '')
    return [{ name: `培训附件_${dateStr || 'nodate'}.docx`, bytes }]
  }

  // 注册导出器（纳入顶部"一键导出"聚合）
  useEffect(() => {
    registerExporter?.('attachment', async () => {
      if (!validRows.length) return null
      return buildExportEntries()
    })
  })

  const handleExport = async () => {
    if (!validRows.length) {
      message.warning('请先添加培训附件文件')
      return
    }
    setExporting(true)
    try {
      const entries = await buildExportEntries()
      if (!entries) return
      for (const e of entries) downloadBytes(e.bytes, e.name)
      message.success('培训附件已生成')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '生成失败')
    } finally {
      setExporting(false)
    }
  }

  const columns: ColumnsType<TrainingAttachmentRow> = [
    {
      title: '序号',
      width: 64,
      align: 'center',
      render: (_v, _r, idx) => idx + 1,
    },
    {
      title: '文件名称',
      dataIndex: 'name',
      render: (v: string, _r, idx) => (
        <Input value={v} onChange={(e) => handleNameChange(idx, e.target.value)} placeholder="文件名称" />
      ),
    },
    {
      title: '文件编号',
      dataIndex: 'code',
      render: (v: string | null, _r, idx) => (
        <Input value={v || ''} onChange={(e) => handleCodeChange(idx, e.target.value)} placeholder="文件编号" />
      ),
    },
    {
      title: '操作',
      width: 72,
      align: 'center',
      render: (_v, _r, idx) => (
        <Button type="text" danger icon={<DeleteOutlined />} onClick={() => handleRemove(idx)} />
      ),
    },
  ]

  return (
    <Card size="small" title="培训附件">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          添加文件
        </Button>
        <Button icon={<DownloadOutlined />} onClick={handleExport} loading={exporting} disabled={!validRows.length}>
          导出
        </Button>
        {validRows.length > 0 && (
          <Tag color="blue">共 {validRows.length} 份文件</Tag>
        )}
      </div>
      <Table<TrainingAttachmentRow>
        rowKey={(r) => r.uid}
        columns={columns}
        dataSource={rows}
        pagination={false}
        size="middle"
        locale={{ emptyText: '暂无培训附件文件，请点击「添加文件」录入' }}
      />
      <div className="mt-2 text-xs text-gray-500">
        提示：勾选培训附件内容或新员工培训教材后自动录入全部文件（超 2 份时签到表仅显示前 2 份，本页记录完整清单），也可手动添加、修改、删除；导出的 Word 与培训附件模板格式一致。
      </div>
    </Card>
  )
}
