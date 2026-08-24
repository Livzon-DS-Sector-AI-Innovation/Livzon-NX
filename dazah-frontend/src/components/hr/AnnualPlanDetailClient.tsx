'use client'

import { useEffect, useState } from 'react'
import { App, Button, Input, Spin, Space, Tag, Upload, Popconfirm } from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  SaveOutlined,
  ArrowLeftOutlined,
  DownloadOutlined,
  UploadOutlined,
  PaperClipOutlined
} from '@ant-design/icons'
import Link from 'next/link'
import { AnnualTrainingPlan, PlanAttachment, PlanAttachmentSection, AttachmentPreview } from '@/types/hr'
import { fetchPlanItems, fetchAnnualTrainingPlanById, fetchPlanAttachments, fetchPlanAttachmentSections, fetchSectionPreview, fetchAttachmentPreview, exportAnnualTrainingPlanWord } from '@/lib/api/client/hr'
import { batchUpdatePlanItems, uploadPlanAttachments, deletePlanAttachment } from '@/actions/hr'
import AttachmentPreviewModal from './AttachmentPreviewModal'

// ── 附件编号归一化（与后端 normalize_annex_no 同规则）──
const CN_DIGIT: Record<string, number> = { '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9 }

function cnToInt(s: string): number | null {
  if (!s) return null
  if (/^\d+$/.test(s)) return parseInt(s, 10)
  if (!s.includes('十')) return CN_DIGIT[s] ?? null
  const i = s.indexOf('十')
  const tensStr = s.slice(0, i)
  const onesStr = s.slice(i + 1)
  const t = tensStr ? (CN_DIGIT[tensStr] ?? 1) : 1
  const o = onesStr ? (CN_DIGIT[onesStr] ?? 0) : 0
  return t * 10 + o
}

function toHalfDigits(s: string): string {
  return s.replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xFEE0))
}

/** 从培训内容中提取所有"附件X"引用（归一化、去重、保序）. */
function extractAnnexRefs(text: string): string[] {
  const refs: string[] = []
  const re = /附件\s*([0-9０-９一二三四五六七八九十]+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text || ''))) {
    const n = cnToInt(toHalfDigits(m[1]))
    const key = n ? `附件${n}` : ''
    if (key && !refs.includes(key)) refs.push(key)
  }
  return refs
}

interface AnnualPlanDetailClientProps {
  planId: string
  plan: AnnualTrainingPlan | null
}

interface PlanRow {
  id: string
  sort_order: number
  training_type: string        // 培训类型：内训/外训
  training_month: string       // 培训时间（月度）
  content_textbook: string     // 培训内容或使用教材
  target_audience: string      // 培训对象
  instructor: string           // 授课单位或人员
  assessment_method: string    // 考核方式
}

export default function AnnualPlanDetailClient({
  planId,
  plan: initialPlan
}: AnnualPlanDetailClientProps) {
  const { message } = App.useApp()
  const [plan, setPlan] = useState<AnnualTrainingPlan | null>(initialPlan)
  const [rows, setRows] = useState<PlanRow[]>([])
  const [attachments, setAttachments] = useState<PlanAttachment[]>([])
  const [sections, setSections] = useState<PlanAttachmentSection[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewData, setPreviewData] = useState<AttachmentPreview | null>(null)
  const [previewTitle, setPreviewTitle] = useState('附件预览')

  const loadAttachments = async () => {
    try {
      const [attRes, secRes] = await Promise.all([
        fetchPlanAttachments(planId),
        fetchPlanAttachmentSections(planId),
      ])
      setAttachments(attRes.data || [])
      setSections(secRes.data || [])
    } catch {
      // 附件加载失败不阻塞主表
    }
  }

  const openSectionPreview = async (section: PlanAttachmentSection) => {
    setPreviewOpen(true)
    setPreviewLoading(true)
    setPreviewTitle(`${section.annex_no}${section.title ? ` · ${section.title}` : ''}`)
    try {
      const res = await fetchSectionPreview(section.id)
      setPreviewData(res.data ?? null)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '预览失败')
      setPreviewData(null)
    } finally {
      setPreviewLoading(false)
    }
  }

  const openAttachmentPreview = async (att: PlanAttachment) => {
    setPreviewOpen(true)
    setPreviewLoading(true)
    setPreviewTitle(att.file_name)
    try {
      const res = await fetchAttachmentPreview(att.id)
      setPreviewData(res.data ?? null)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '预览失败')
      setPreviewData(null)
    } finally {
      setPreviewLoading(false)
    }
  }

  /** 行内"附件X"标签：优先匹配条目（可预览对应章节），否则匹配整文件附件. */
  const resolveAnnexRef = (ref: string): { section?: PlanAttachmentSection; attachment?: PlanAttachment } => {
    const section = sections.find((s) => s.annex_no === ref)
    if (section) return { section }
    const attachment = attachments.find((a) => a.annex_no === ref)
    return { attachment }
  }

  const loadData = async () => {
    setLoading(true)
    try {
      if (!initialPlan) {
        const res = await fetchAnnualTrainingPlanById(planId)
        setPlan(res.data)
      }
      const itemsRes = await fetchPlanItems(planId)
      const items = itemsRes.data || []
      const planRows: PlanRow[] = items.map((item: any, idx: number) => ({
        id: item.id,
        sort_order: item.sort_order ?? idx,
        training_type: item.training_type || '',
        training_month: item.training_month || item.month || '',
        content_textbook: item.content_textbook || item.content_and_textbook || '',
        target_audience: item.target_audience || item.target_audience_new || '',
        instructor: item.instructor || '',
        assessment_method: item.assessment_method || '',
      }))
      setRows(planRows)
      await loadAttachments()
    } catch (err) {
      message.error('加载失败: ' + ((err instanceof Error ? err.message : '') || ''))
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      await uploadPlanAttachments(planId, [file])
      message.success(`已上传 ${file.name}`)
      await loadAttachments()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '上传失败')
    } finally {
      setUploading(false)
    }
    return false
  }

  const handleDeleteAttachment = async (id: string) => {
    try {
      await deletePlanAttachment(id)
      message.success('附件已删除')
      await loadAttachments()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '删除失败')
    }
  }

  const downloadAttachment = (a: PlanAttachment) => {
    window.open(`/api/v1/hr/annual-training-plan-attachments/${a.id}/download`, '_blank')
  }

  useEffect(() => {
    queueMicrotask(loadData)
  }, [planId])

  const handleAddRow = () => {
    const newRow: PlanRow = {
      id: `new-${Date.now()}`,
      sort_order: rows.length,
      training_type: '',
      training_month: '',
      content_textbook: '',
      target_audience: '',
      instructor: '',
      assessment_method: '',
    }
    setRows([...rows, newRow])
  }

  const handleDeleteRow = (id: string) => {
    setRows(rows.filter((r) => r.id !== id))
  }

  const updateRow = (id: string, field: keyof PlanRow, value: string) => {
    setRows(rows.map((r) => (r.id === id ? { ...r, [field]: value } : r)))
  }

  const handleSaveAll = async () => {
    if (rows.length === 0) {
      message.warning('请先添加明细')
      return
    }

    const payloadItems = rows.map((row, idx) => ({
      sort_order: idx,
      training_type: row.training_type || undefined,
      training_month: row.training_month || undefined,
      content_textbook: row.content_textbook || undefined,
      target_audience_new: row.target_audience || undefined,
      instructor: row.instructor || undefined,
      assessment_method: row.assessment_method || undefined,
    }))

    setSaving(true)
    try {
      await batchUpdatePlanItems(planId, { items: payloadItems as any })
      message.success('保存成功')
      await loadData()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleExport = async () => {
    try {
      await exportAnnualTrainingPlanWord(planId, plan?.plan_level === '公司级')
      message.success('导出成功')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '导出失败')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spin size="large" description="加载中..." />
      </div>
    )
  }

  if (!plan) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-gray-400">
        <p>未找到该年度计划</p>
        <Link href="/hr/training/annual-plan">
          <Button type="link">返回列表</Button>
        </Link>
      </div>
    )
  }

  const isCompanyLevel = plan.plan_level === '公司级'

  return (
    <div className="space-y-4">
      {/* 控制栏 */}
      <div className="flex flex-wrap items-center gap-4 no-print">
        <Link href="/hr/training/annual-plan">
          <Button icon={<ArrowLeftOutlined />}>返回</Button>
        </Link>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAddRow}>
          添加行
        </Button>
        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSaveAll}>
          保存全部
        </Button>
        <Button icon={<DownloadOutlined />} onClick={handleExport}>
          {isCompanyLevel ? '导出公司级计划(APP2)' : '导出部门级计划(APP1)'}
        </Button>
      </div>

      <div id="print-area" className="print-area">
        <div className="text-center text-lg font-bold py-2">
          {plan.year}年度{isCompanyLevel ? '公司' : '部门'}培训计划表
        </div>
        <div className="flex justify-between text-sm py-1">
          {!isCompanyLevel ? (
            <span>部门：{plan.department}</span>
          ) : (
            <span />
          )}
          {plan.version && (
            <span>版本：{plan.version}</span>
          )}
        </div>

        <table className="w-full border-collapse text-sm" style={{ tableLayout: 'fixed' }}>
          <colgroup>
            <col style={{ width: '4%' }} />
            <col style={{ width: '7%' }} />
            <col style={{ width: '7%' }} />
            <col style={{ width: '18%' }} />
            <col style={{ width: '26%' }} />
            <col style={{ width: '10%' }} />
            <col style={{ width: '8%' }} />
            <col style={{ width: '8%' }} />
            <col style={{ width: '4%' }} />
          </colgroup>
          <thead>
            <tr>
              <th className="border border-gray-400 px-1 py-2 text-center bg-gray-50">序号</th>
              <th className="border border-gray-400 px-1 py-2 text-center bg-gray-50">培训类型</th>
              <th className="border border-gray-400 px-1 py-2 text-center bg-gray-50">培训时间（月度）</th>
              <th className="border border-gray-400 px-1 py-2 text-center bg-gray-50">培训内容或使用教材</th>
              <th className="border border-gray-400 px-1 py-2 text-center bg-gray-50">培训对象</th>
              <th className="border border-gray-400 px-1 py-2 text-center bg-gray-50">授课单位或人员</th>
              <th className="border border-gray-400 px-1 py-2 text-center bg-gray-50">考核方式</th>
              <th className="border border-gray-400 px-1 py-2 text-center bg-gray-50">附件</th>
              <th className="border border-gray-400 px-1 py-2 text-center bg-gray-50 no-print">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="border border-gray-400 px-2 py-4 text-center text-gray-400">
                  暂无明细，点击“添加行”开始编辑
                </td>
              </tr>
            ) : (
              rows.map((row, idx) => (
                <tr key={row.id}>
                  <td className="border border-gray-400 px-1 py-1 text-center align-top">
                    {idx + 1}
                  </td>
                  <td className="border border-gray-400 px-1 py-1 text-center align-top">
                    <Space orientation="vertical" size="small" className="text-xs">
                      <label className="cursor-pointer">
                        <input
                          type="checkbox"
                          checked={row.training_type.includes('内训')}
                          onChange={(e) => {
                            const isInner = e.target.checked
                            const isOuter = row.training_type.includes('外训')
                            let val = ''
                            if (isInner && isOuter) val = '内训 外训'
                            else if (isInner) val = '内训'
                            else if (isOuter) val = '外训'
                            else val = ''
                            updateRow(row.id, 'training_type', val)
                          }}
                          className="mr-1"
                        />
                        内训
                      </label>
                      <label className="cursor-pointer">
                        <input
                          type="checkbox"
                          checked={row.training_type.includes('外训')}
                          onChange={(e) => {
                            const isOuter = e.target.checked
                            const isInner = row.training_type.includes('内训')
                            let val = ''
                            if (isInner && isOuter) val = '内训 外训'
                            else if (isInner) val = '内训'
                            else if (isOuter) val = '外训'
                            else val = ''
                            updateRow(row.id, 'training_type', val)
                          }}
                          className="mr-1"
                        />
                        外训
                      </label>
                    </Space>
                  </td>
                  <td className="border border-gray-400 px-1 py-1 align-top">
                    <Input
                      size="small"
                      className="w-full"
                      value={row.training_month}
                      onChange={(e) => updateRow(row.id, 'training_month', e.target.value)}
                      placeholder="如：3月"
                    />
                  </td>
                  <td className="border border-gray-400 px-1 py-1 align-top">
                    <Input.TextArea
                      size="small"
                      autoSize={{ minRows: 1, maxRows: 3 }}
                      className="w-full"
                      value={row.content_textbook}
                      onChange={(e) => updateRow(row.id, 'content_textbook', e.target.value)}
                      placeholder="培训内容或使用教材"
                    />
                  </td>
                  <td className="border border-gray-400 px-1 py-1 align-top">
                    <Input.TextArea
                      size="small"
                      autoSize={{ minRows: 1, maxRows: 3 }}
                      className="w-full"
                      value={row.target_audience}
                      onChange={(e) => updateRow(row.id, 'target_audience', e.target.value)}
                      placeholder="培训对象"
                    />
                  </td>
                  <td className="border border-gray-400 px-1 py-1 align-top">
                    <Input
                      size="small"
                      className="w-full"
                      value={row.instructor}
                      onChange={(e) => updateRow(row.id, 'instructor', e.target.value)}
                      placeholder="授课单位或人员"
                    />
                  </td>
                  <td className="border border-gray-400 px-1 py-1 align-top">
                    <Input
                      size="small"
                      className="w-full"
                      value={row.assessment_method}
                      onChange={(e) => updateRow(row.id, 'assessment_method', e.target.value)}
                      placeholder="考核方式"
                    />
                  </td>
                  <td className="border border-gray-400 px-1 py-1 text-center align-top">
                    <div className="flex flex-wrap gap-1 justify-center">
                      {extractAnnexRefs(row.content_textbook).map((ref) => {
                        const { section, attachment } = resolveAnnexRef(ref)
                        if (section) {
                          return (
                            <Tag
                              key={ref}
                              color="blue"
                              className="cursor-pointer m-0 text-xs"
                              onClick={() => openSectionPreview(section)}
                              title={`${section.title || ref}（点击预览）`}
                            >
                              <PaperClipOutlined /> {ref}
                            </Tag>
                          )
                        }
                        if (attachment) {
                          return (
                            <Tag
                              key={ref}
                              color="blue"
                              className="cursor-pointer m-0 text-xs"
                              onClick={() => openAttachmentPreview(attachment)}
                              title={`${attachment.file_name}（点击预览）`}
                            >
                              <PaperClipOutlined /> {ref}
                            </Tag>
                          )
                        }
                        return (
                          <Tag key={ref} className="m-0 text-xs opacity-60" title="附件尚未上传">
                            {ref} 未上传
                          </Tag>
                        )
                      })}
                    </div>
                  </td>
                  <td className="border border-gray-400 px-1 py-1 text-center align-top no-print">
                    <Button
                      type="link"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => handleDeleteRow(row.id)}
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
          {plan.remarks && (
            <tfoot>
              <tr>
                <td className="border border-gray-400 px-1 py-1 text-center font-medium" colSpan={2}>
                  备注
                </td>
                <td className="border border-gray-400 px-1 py-1" colSpan={7}>
                  {plan.remarks}
                </td>
              </tr>
            </tfoot>
          )}
        </table>
        {/* 审批栏不显示在页面上，只在导出的 Word 模板中体现 */}
      </div>

      {/* 附件清单（计划级） */}
      <div className="no-print space-y-2 border border-gray-200 rounded-lg p-3 bg-white">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold m-0">
            <PaperClipOutlined className="mr-1" />
            附件清单
            <span className="ml-2 text-xs text-gray-400 font-normal">
              文件名含“附件X”自动编号；明细行引用同名附件时可点击下载
            </span>
          </h3>
          <Upload multiple showUploadList={false} beforeUpload={handleUpload}>
            <Button size="small" icon={<UploadOutlined />} loading={uploading}>
              批量上传附件
            </Button>
          </Upload>
        </div>
        {attachments.length === 0 ? (
          <p className="text-xs text-gray-400 m-0">
            暂无附件。导入计划后，可在此批量上传支撑文件；含“附件X”的 sheet/标题段会自动拆成可索引条目。
          </p>
        ) : (
          <div className="space-y-2">
            {attachments.map((a) => {
              const fileSections = sections.filter((s) => s.attachment_id === a.id)
              return (
                <div key={a.id} className="flex flex-wrap items-center gap-2">
                  <Tag className="m-0 py-0.5">
                    <span className="cursor-pointer" onClick={() => downloadAttachment(a)} title="点击下载">
                      <PaperClipOutlined className="mr-1" />
                      {a.file_name}
                    </span>
                    <span
                      className="ml-2 text-blue-500 cursor-pointer"
                      onClick={() => openAttachmentPreview(a)}
                      title="预览整文件"
                    >
                      预览
                    </span>
                    <Popconfirm title="删除该附件？" onConfirm={() => handleDeleteAttachment(a.id)}>
                      <DeleteOutlined className="ml-2 text-red-400 cursor-pointer" />
                    </Popconfirm>
                  </Tag>
                  {fileSections.map((s) => (
                    <Tag
                      key={s.id}
                      color="blue"
                      className="m-0 cursor-pointer"
                      onClick={() => openSectionPreview(s)}
                      title={`${s.title || s.annex_no}（点击预览）`}
                    >
                      {s.annex_no}
                      {s.title && s.title !== s.annex_no ? ` · ${s.title}` : ''}
                    </Tag>
                  ))}
                </div>
              )
            })}
          </div>
        )}
      </div>

      <AttachmentPreviewModal
        open={previewOpen}
        title={previewTitle}
        loading={previewLoading}
        preview={previewData}
        onClose={() => setPreviewOpen(false)}
      />
    </div>
  )
}
