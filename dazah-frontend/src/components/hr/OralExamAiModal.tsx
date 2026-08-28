'use client'

import { useEffect, useState } from 'react'
import { App, Button, Input, InputNumber, Modal, Space, Spin, Tag } from 'antd'
import {
  RobotOutlined,
  DeleteOutlined,
  CheckOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import type { OralExamFile, OralExamQuestion, OralExamSourceFile } from '@/types/hr'
import { resolveDocumentEntryContent } from '@/actions/quality'
import { generateOralExamQuestions } from '@/lib/api/ai'

/** 单文件内容截断上限（防止 prompt 超长） */
const CONTENT_MAX_LEN = 8000

interface OralExamAiModalProps {
  open: boolean
  onClose: () => void
  /** 结构化勾选文件（优先来源，来自签到表 checked_content） */
  sourceFiles?: { name: string; code: string | null }[]
  /** 培训内容字符串（回退来源，解析《文件名称》） */
  contentText?: string
  /** 确认回填：返回要追加的口试问答题 */
  onConfirm: (questions: OralExamQuestion[]) => void
}

/** 解析培训内容字符串中的《文件名称》 */
function parseContentFileNames(text: string): string[] {
  const names: string[] = []
  const re = /《([^》]+)》/g
  let match: RegExpExecArray | null
  while ((match = re.exec(text || ''))) names.push(match[1])
  return names
}

/** 口试 AI 出题弹窗：文件解析结果（可手动补充）→ AI 生成 → 预览编辑 → 确认回填 */
export default function OralExamAiModal({
  open,
  onClose,
  sourceFiles,
  contentText,
  onConfirm,
}: OralExamAiModalProps) {
  const { message } = App.useApp()
  const [files, setFiles] = useState<OralExamSourceFile[]>([])
  const [resolving, setResolving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [questions, setQuestions] = useState<OralExamQuestion[]>([])
  const [questionCount, setQuestionCount] = useState<number | null>(null)

  // 打开弹窗时：收集文件名 → 解析质量文件管理中的附件内容
  useEffect(() => {
    if (!open) return
    setQuestions([])
    const names = sourceFiles?.length
      ? sourceFiles.map((f) => f.name)
      : parseContentFileNames(contentText || '')
    if (!names.length) {
      setFiles([])
      return
    }
    setResolving(true)
    resolveDocumentEntryContent(names)
      .then((items) => {
        const resolved: OralExamSourceFile[] = names.map((name) => {
          const item = items.find((x) => x.name === name)
          if (!item || !item.matched) {
            return { name, code: null, matched: false, attachmentCount: 0 }
          }
          const mdText = (item.attachments || [])
            .map((a) => a.md_text)
            .filter(Boolean)
            .join('\n\n')
          return {
            name,
            code: item.code,
            matched: true,
            attachmentCount: (item.attachments || []).length,
            resolvedContent: mdText || undefined,
          }
        })
        setFiles(resolved)
      })
      .catch((err: any) => {
        message.error((err instanceof Error ? err.message : '') || '解析文件内容失败')
        setFiles(names.map((name) => ({ name, code: null, matched: false, attachmentCount: 0 })))
      })
      .finally(() => setResolving(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const updateManualText = (index: number, value: string) => {
    setFiles((prev) => prev.map((f, i) => (i === index ? { ...f, manualText: value } : f)))
  }

  // 有效材料 = 附件内容 或 手动补充文本（截断防超长）
  const buildFiles = (): OralExamFile[] => {
    const list: OralExamFile[] = []
    for (const f of files) {
      const content = (f.resolvedContent || f.manualText || '').trim()
      if (!content) continue
      list.push({
        name: f.name,
        code: f.code ?? null,
        content: content.slice(0, CONTENT_MAX_LEN),
      })
    }
    return list
  }

  const handleGenerate = async () => {
    const list = buildFiles()
    if (!list.length) {
      message.warning('请至少为一份文件提供内容（已匹配附件或手动粘贴）')
      return
    }
    setGenerating(true)
    try {
      const res = await generateOralExamQuestions(list, questionCount)
      const qs = res.questions || []
      setQuestions(qs)
      message.success(`已生成 ${qs.length} 道口试问答题`)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || 'AI 出题失败，请重试')
    } finally {
      setGenerating(false)
    }
  }

  const updateQuestion = (index: number, field: keyof OralExamQuestion, value: string) => {
    setQuestions((prev) => prev.map((q, i) => (i === index ? { ...q, [field]: value } : q)))
  }

  const removeQuestion = (index: number) => {
    setQuestions((prev) => prev.filter((_, i) => i !== index))
  }

  const handleConfirm = () => {
    const valid = questions.filter((q) => (q.question || '').trim())
    if (!valid.length) {
      message.warning('没有可回填的题目，请先生成题目')
      return
    }
    onConfirm(valid)
    onClose()
  }

  const hasValidMaterial = files.some(
    (f) => (f.resolvedContent || f.manualText || '').trim().length > 0,
  )

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={
        <span>
          <RobotOutlined className="mr-2 text-[var(--color-primary)]" />
          口试 AI 出题
        </span>
      }
      width={860}
      footer={null}
      destroyOnHidden
    >
      {/* ─── 文件解析结果 ─── */}
      <div className="mb-3">
        <div className="text-[14px] font-semibold text-[var(--color-charcoal)] mb-2">
          培训文件（{files.length}）
        </div>
        <Spin spinning={resolving}>
          {files.length === 0 ? (
            <div className="text-[13px] text-gray-400">
              未找到培训文件信息。请在签到表勾选培训内容，或手动填写。
            </div>
          ) : (
            <div className="space-y-2">
              {files.map((f, i) => (
                <div key={`${f.name}-${i}`} className="border border-gray-200 rounded p-2">
                  <div className="flex items-center gap-2 mb-1">
                    <FileTextOutlined className="text-gray-400" />
                    <span className="text-[13px] font-medium text-[var(--color-charcoal)]">
                      {f.name}
                    </span>
                    {f.code && <span className="text-[12px] text-gray-400">（{f.code}）</span>}
                    {f.matched && f.attachmentCount > 0 ? (
                      <Tag color="success">已匹配 {f.attachmentCount} 个附件</Tag>
                    ) : (
                      <Tag color="warning">未找到可读内容</Tag>
                    )}
                  </div>
                  {f.matched && f.resolvedContent ? (
                    <div className="text-[12px] text-gray-500 max-h-16 overflow-auto bg-gray-50 rounded px-2 py-1">
                      {f.resolvedContent.length > 120
                        ? `${f.resolvedContent.slice(0, 120)}…`
                        : f.resolvedContent}
                    </div>
                  ) : (
                    <Input.TextArea
                      placeholder={
                        f.matched
                          ? '该文件无附件内容，可在此手动粘贴文件文本用于出题'
                          : '未在质量文件管理中匹配到该文件，可手动粘贴文件文本用于出题'
                      }
                      value={f.manualText || ''}
                      onChange={(e) => updateManualText(i, e.target.value)}
                      autoSize={{ minRows: 2, maxRows: 4 }}
                      className="text-[13px]"
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </Spin>
      </div>

      <Space className="mb-3" wrap>
        <span className="text-[13px] text-gray-600">总题数（可选）：</span>
        <InputNumber
          min={1}
          max={100}
          value={questionCount ?? undefined}
          onChange={(v) => setQuestionCount(v ?? null)}
          placeholder="默认按每份 2~3 题"
          style={{ width: 130 }}
        />
        <Button
          type="primary"
          icon={<RobotOutlined />}
          onClick={handleGenerate}
          loading={generating}
          disabled={!hasValidMaterial}
        >
          {generating ? 'AI 正在出题...' : 'AI 出题'}
        </Button>
      </Space>

      {/* ─── 题目预览编辑 ─── */}
      {questions.length > 0 && (
        <div className="border border-gray-200 rounded p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[14px] font-semibold text-[var(--color-charcoal)]">
              生成题目（{questions.length} 道，可直接编辑）
            </span>
            <Button type="primary" icon={<CheckOutlined />} onClick={handleConfirm}>
              确认回填到口试表
            </Button>
          </div>
          <div className="space-y-2 max-h-80 overflow-auto pr-1">
            {questions.map((q, i) => (
              <div key={i} className="border border-gray-200 rounded p-2 bg-gray-50">
                <div className="flex items-start gap-2">
                  <span className="font-bold text-[13px] mt-1 whitespace-nowrap">{i + 1}.</span>
                  <div className="flex-1 space-y-1">
                    <Input.TextArea
                      placeholder="考核问题"
                      value={q.question || ''}
                      onChange={(e) => updateQuestion(i, 'question', e.target.value)}
                      autoSize={{ minRows: 1, maxRows: 3 }}
                      className="text-[13px]"
                    />
                    <Input.TextArea
                      placeholder="参考答案要点"
                      value={q.answer || ''}
                      onChange={(e) => updateQuestion(i, 'answer', e.target.value)}
                      autoSize={{ minRows: 1, maxRows: 3 }}
                      className="text-[13px]"
                    />
                  </div>
                  <Button
                    type="text"
                    danger
                    size="small"
                    icon={<DeleteOutlined />}
                    onClick={() => removeQuestion(i)}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Modal>
  )
}
