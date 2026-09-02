'use client'

import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { Alert, App, Button, Input, InputNumber, Space, Spin, Tag } from 'antd'
import {
  RobotOutlined,
  DownloadOutlined,
  DeleteOutlined,
  PlusOutlined,
  UploadOutlined,
  FileTextOutlined,
  LoadingOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons'
import type {
  AiWrittenExamPayload,
  ChoiceOption,
  ChoiceQuestion,
  ExportedDoc,
  FillBlankQuestion,
  TrueFalseQuestion,
  TrainingDocExporter,
  TrainingSessionData,
} from '@/types/hr'
import { resolveDocumentEntryContent } from '@/actions/quality'
import { pollWrittenExamGenerate, submitWrittenExamGenerate, exportWrittenExam, extractExamDocumentText } from '@/lib/api/ai'
import { downloadBytes } from '@/lib/download'

/** 单文件内容截断上限（后端总素材另有 12 万字封顶兜底） */
const CONTENT_MAX_LEN = 30000

/** 试卷满分固定 100 分，按总题数均分（与后端导出规则一致） */
function calcQuestionScores(total: number): number[] {
  if (total <= 0) return []
  const base = Math.floor(100 / total)
  const rem = 100 - base * total
  return [...new Array(rem).fill(base + 1), ...new Array(total - rem).fill(base)]
}

/** 大题分值描述：共 X 分（分值统一时追加每题 Y 分） */
function sectionScoreText(scores: number[]): string {
  if (!scores.length) return '共 0 分'
  const total = scores.reduce((a, b) => a + b, 0)
  const uniform = scores.every((s) => s === scores[0])
  return uniform ? `共 ${total} 分，每题 ${scores[0]} 分` : `共 ${total} 分`
}

interface Props {
  sessionData: TrainingSessionData
  initialPayload?: AiWrittenExamPayload | null
  /** 评估表考核方式为"笔试"时才自动填写 */
  active?: boolean
  assessmentMethod?: string
  registerDocBuilder?: (type: string, fn: () => Record<string, unknown> | null) => void
  registerExporter?: (type: string, fn: TrainingDocExporter) => void
}

interface ResolvedFile {
  name: string
  code?: string | null
  content: string
  matched: boolean
}

/** 上传文件条目（后端解析状态） */
interface UploadedFileItem {
  uid: string
  name: string
  status: 'parsing' | 'parsed' | 'error'
  text: string
  error?: string
}

export default function AiWrittenExamClient({ sessionData, initialPayload, active = true, assessmentMethod, registerDocBuilder, registerExporter }: Props) {
  const { message } = App.useApp()

  // ── 试卷标题（可编辑，默认取培训内容） ──
  const [examTitle, setExamTitle] = useState('')
  const titleEditedRef = useRef(false)

  // ── 内容来源 ──
  const [resolvedFiles, setResolvedFiles] = useState<ResolvedFile[]>([])
  const [resolving, setResolving] = useState(false)
  const [manualContent, setManualContent] = useState('')
  const [uploadedItems, setUploadedItems] = useState<UploadedFileItem[]>([])
  // 显式 file input（避开 antd Upload 隐藏 input 在部分浏览器/Tab 场景点击不弹对话框的问题）
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── 出题配置 ──
  const [singleChoiceCount, setSingleChoiceCount] = useState(5)
  const [multipleChoiceCount, setMultipleChoiceCount] = useState(0)
  const [trueFalseCount, setTrueFalseCount] = useState(0)
  const [fillBlankCount, setFillBlankCount] = useState(5)

  // ── 题目数据 ──
  const [choiceQuestions, setChoiceQuestions] = useState<ChoiceQuestion[]>([])
  const [trueFalseQuestions, setTrueFalseQuestions] = useState<TrueFalseQuestion[]>([])
  const [fillBlankQuestions, setFillBlankQuestions] = useState<FillBlankQuestion[]>([])
  const [generating, setGenerating] = useState(false)
  const [generatingProgress, setGeneratingProgress] = useState('')
  const [exporting, setExporting] = useState(false)

  // ── 试卷标题：由勾选文件生成《第一份》等 N 份文件笔试题（不含"详见附件"；用户手动修改后不再覆盖） ──
  useEffect(() => {
    if (!active) return
    if (titleEditedRef.current) return
    const entries = sessionData.checked_content || []
    if (entries.length) {
      const first = entries[0]
      const label = first.code ? `《${first.name}》（${first.code}）` : `《${first.name}》`
      setExamTitle(entries.length > 1 ? `${label}等${entries.length}份文件笔试题` : `${label}笔试题`)
    } else if (sessionData.topic) {
      setExamTitle(sessionData.topic)
    }
  }, [sessionData.topic, sessionData.checked_content, active])

  // ── 初始化：从 initialPayload 恢复 ──
  useEffect(() => {
    if (!initialPayload) return
    if (initialPayload.title) {
      setExamTitle(initialPayload.title)
      titleEditedRef.current = true
    }
    if (initialPayload.files?.length) {
      setResolvedFiles(initialPayload.files.map((f) => ({
        name: f.name,
        code: f.code,
        content: f.content,
        matched: !!f.content,
      })))
    }
    setManualContent(initialPayload.manual_content || '')
    // 上传内容草稿恢复为单个已解析条目
    if (initialPayload.uploaded_content) {
      setUploadedItems([{ uid: 'draft', name: '已恢复的上传内容', status: 'parsed', text: initialPayload.uploaded_content }])
    }
    // 旧版草稿（choice_count/choice_type）兼容映射
    if (initialPayload.single_choice_count === undefined && initialPayload.choice_count !== undefined) {
      const legacyCount = initialPayload.choice_count
      if (initialPayload.choice_type === 'multiple') {
        setSingleChoiceCount(0)
        setMultipleChoiceCount(legacyCount)
      } else {
        setSingleChoiceCount(legacyCount)
        setMultipleChoiceCount(0)
      }
    } else {
      setSingleChoiceCount(initialPayload.single_choice_count ?? 5)
      setMultipleChoiceCount(initialPayload.multiple_choice_count ?? 0)
    }
    setTrueFalseCount(initialPayload.true_false_count ?? 0)
    setFillBlankCount(initialPayload.fill_blank_count || 5)
    setChoiceQuestions(initialPayload.choice_questions || [])
    setTrueFalseQuestions(initialPayload.true_false_questions || [])
    setFillBlankQuestions(initialPayload.fill_blank_questions || [])
  }, [initialPayload])

  // ── 自动解析 checked_content（勾选锁定的条目按 ID 精确读取，不按名称匹配） ──
  useEffect(() => {
    if (!active) return
    const entries = sessionData.checked_content || []
    if (!entries.length) {
      setResolvedFiles([])
      return
    }
    // 如果已有 initialPayload 恢复的文件则不重复解析
    if (initialPayload?.files?.length) return
    setResolving(true)
    resolveDocumentEntryContent(entries.map((f) => ({ name: f.name, entry_id: f.entry_id ?? null })))
      .then((items) => {
        const resolved: ResolvedFile[] = entries.map((f) => {
          const item = items.find((x) => x.name === f.name)
          if (!item || !item.matched) {
            return { name: f.name, code: item?.code ?? null, content: '', matched: false }
          }
          const mdText = (item.attachments || [])
            .map((a) => a.md_text)
            .filter(Boolean)
            .join('\n\n')
          return { name: f.name, code: item.code, content: mdText || '', matched: !!mdText }
        })
        setResolvedFiles(resolved)
      })
      .catch(() => {
        setResolvedFiles(entries.map((f) => ({ name: f.name, content: '', matched: false })))
      })
      .finally(() => setResolving(false))

  }, [sessionData.checked_content, active, initialPayload])

  // ── 上传文件：统一发送到后端解析全文 ──
  const parseUploadedFile = async (uid: string, file: File) => {
    try {
      const res = await extractExamDocumentText(file)
      setUploadedItems((prev) => prev.map((it) =>
        it.uid === uid ? { ...it, status: 'parsed', text: res.text } : it,
      ))
    } catch (err) {
      setUploadedItems((prev) => prev.map((it) =>
        it.uid === uid ? { ...it, status: 'error', error: (err instanceof Error ? err.message : '') || '解析失败' } : it,
      ))
    }
  }

  // 显式 file input 变更处理：逐文件解析全文，完成后清空 value 允许重复选择同一文件
  const handleFileInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []) as File[]
    e.target.value = ''
    for (const file of files) {
      const uid = `up-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      setUploadedItems((prev) => [...prev.slice(-2), { uid, name: file.name, status: 'parsing', text: '' }])
      parseUploadedFile(uid, file)
    }
  }

  const removeUploadedItem = (uid: string) => {
    setUploadedItems((prev) => prev.filter((it) => it.uid !== uid))
  }

  const updateUploadedText = (uid: string, value: string) => {
    setUploadedItems((prev) => prev.map((it) => (it.uid === uid ? { ...it, text: value } : it)))
  }

  // 上传文件合并文本（解析成功的全文 + 解析失败后手动粘贴的兜底文本）
  const uploadedContent = uploadedItems
    .filter((it) => it.text.trim())
    .map((it) => `${it.name}：\n${it.text}`)
    .join('\n\n---\n\n')

  // ── 构建出题素材 ──
  const buildGeneratePayload = () => {
    const files = resolvedFiles
      .filter((f) => f.content.trim())
      .map((f) => ({
        name: f.name,
        code: f.code ?? null,
        content: f.content.slice(0, CONTENT_MAX_LEN),
      }))
    const totalContent = (files.map((f) => f.content).join('') + uploadedContent + manualContent).trim()
    if (!totalContent) {
      message.warning('请至少提供一份培训内容（勾选文件/上传文档/粘贴文本）')
      return null
    }
    if (uploadedItems.some((it) => it.status === 'parsing')) {
      message.warning('文档正在解析中，请稍候再出题')
      return null
    }
    return {
      files,
      uploaded_content: uploadedContent.slice(0, CONTENT_MAX_LEN * 4),
      manual_content: manualContent.slice(0, CONTENT_MAX_LEN),
      single_choice_count: singleChoiceCount,
      multiple_choice_count: multipleChoiceCount,
      true_false_count: trueFalseCount,
      fill_blank_count: fillBlankCount,
    }
  }

  // ── AI 出题（提交后台任务 → 轮询进度 → 渲染结果） ──
  const handleGenerate = async () => {
    const payload = buildGeneratePayload()
    if (!payload) return
    setGenerating(true)
    setGeneratingProgress('正在提交出题任务…')
    try {
      const jobId = await submitWrittenExamGenerate(payload)
      const res = await pollWrittenExamGenerate(jobId, (progress) => {
        setGeneratingProgress(progress || '正在生成题目…')
      })
      const choices = res.choice_questions || []
      const tfs = res.true_false_questions || []
      const fills = res.fill_blank_questions || []
      setChoiceQuestions(choices)
      setTrueFalseQuestions(tfs)
      setFillBlankQuestions(fills)
      const total = choices.length + tfs.length + fills.length
      const reqChoice = singleChoiceCount + multipleChoiceCount
      if (res.shortfall || choices.length < reqChoice || tfs.length < trueFalseCount || fills.length < fillBlankCount) {
        message.warning(
          `已生成 ${choices.length} 道选择题、${tfs.length} 道判断题、${fills.length} 道填空题（少于配置数量），可手动补充或重新出题`,
          6,
        )
      } else {
        message.success(`已生成 ${total} 道题目`)
      }
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || 'AI 出题失败，请重试')
    } finally {
      setGenerating(false)
      setGeneratingProgress('')
    }
  }

  // ── 草稿序列化（供保存体系使用） ──
  const buildPayload = (): AiWrittenExamPayload => ({
    title: examTitle,
    files: resolvedFiles.map((f) => ({ name: f.name, code: f.code ?? undefined, content: f.content })),
    uploaded_content: uploadedContent,
    manual_content: manualContent,
    single_choice_count: singleChoiceCount,
    multiple_choice_count: multipleChoiceCount,
    true_false_count: trueFalseCount,
    fill_blank_count: fillBlankCount,
    choice_questions: choiceQuestions,
    true_false_questions: trueFalseQuestions,
    fill_blank_questions: fillBlankQuestions,
  })

  // ── 注册草稿 builder ──
  useEffect(() => {
    registerDocBuilder?.('ai_written_exam', () => {
      const p = buildPayload()
      const hasContent =
        p.files.some((f) => f.content) ||
        p.uploaded_content ||
        p.manual_content ||
        p.choice_questions.length > 0 ||
        p.true_false_questions.length > 0 ||
        p.fill_blank_questions.length > 0
      return hasContent ? (p as unknown as Record<string, unknown>) : null
    })
  })

  // ── 导出 zip（试卷 + 答案分离） ──
  const buildExportEntries = async (): Promise<ExportedDoc[] | null> => {
    if (!choiceQuestions.length && !trueFalseQuestions.length && !fillBlankQuestions.length) return null
    const title = (examTitle || sessionData.topic || 'AI笔试').trim() || 'AI笔试'
    const data: Record<string, unknown> = {
      title,
      examiner: sessionData.instructor || '',
      exam_date: sessionData.training_date || '',
      assessment_date: sessionData.training_date || '',
      choice_questions: choiceQuestions,
      true_false_questions: trueFalseQuestions,
      fill_blank_questions: fillBlankQuestions,
    }
    const blob = await exportWrittenExam(data)
    const safeTitle = title.replace(/[\\/:*?"<>|]/g, '_')
    const bytes = await blob.arrayBuffer()
    return [{ name: `${safeTitle}_试卷与答案.zip`, bytes }]
  }

  // ── 注册导出器 ──
  useEffect(() => {
    registerExporter?.('ai_written_exam', async () => {
      if (!active) return null
      const p = buildPayload()
      if (!p.choice_questions.length && !p.true_false_questions.length && !p.fill_blank_questions.length) return null
      return buildExportEntries()
    })
  })

  const handleExport = async () => {
    if (!choiceQuestions.length && !trueFalseQuestions.length && !fillBlankQuestions.length) {
      message.warning('请先生成题目')
      return
    }
    setExporting(true)
    try {
      const entries = await buildExportEntries()
      if (!entries) return
      for (const e of entries) downloadBytes(e.bytes, e.name)
      message.success('试卷与答案导出成功（zip 内含两份 Word：试卷卷 + 答案卷）')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '导出失败')
    } finally {
      setExporting(false)
    }
  }

  // ── 题目编辑 ──
  const updateChoiceQuestion = (index: number, field: keyof ChoiceQuestion, value: any) => {
    setChoiceQuestions((prev) => prev.map((q, i) => (i === index ? { ...q, [field]: value } : q)))
  }
  const updateChoiceOption = (qIndex: number, oIndex: number, field: keyof ChoiceOption, value: string) => {
    setChoiceQuestions((prev) => {
      const next = [...prev]
      const options = [...next[qIndex].options]
      options[oIndex] = { ...options[oIndex], [field]: value }
      next[qIndex] = { ...next[qIndex], options }
      return next
    })
  }
  const updateFillBlank = (index: number, field: keyof FillBlankQuestion, value: any) => {
    setFillBlankQuestions((prev) => prev.map((q, i) => (i === index ? { ...q, [field]: value } : q)))
  }
  const updateTrueFalse = (index: number, field: keyof TrueFalseQuestion, value: any) => {
    setTrueFalseQuestions((prev) => prev.map((q, i) => (i === index ? { ...q, [field]: value } : q)))
  }

  const hasMaterial =
    resolvedFiles.some((f) => f.content.trim()) ||
    !!uploadedContent.trim() ||
    !!manualContent.trim()

  // 预览区分值显示：满分 100 分按总题数均分（与后端导出规则一致）
  const allScores = calcQuestionScores(choiceQuestions.length + trueFalseQuestions.length + fillBlankQuestions.length)
  const choiceScores = allScores.slice(0, choiceQuestions.length)
  const tfScores = allScores.slice(choiceQuestions.length, choiceQuestions.length + trueFalseQuestions.length)
  const fillScores = allScores.slice(choiceQuestions.length + trueFalseQuestions.length)

  return (
    <div className="space-y-4">
      {!active && (
        <Alert
          type="info"
          showIcon
          className="mb-3"
          title={`评估表当前考核方式为“${assessmentMethod || '未选择'}”，AI 笔试仅在考核方式选择“笔试”时自动填写培训信息。`}
        />
      )}

      {/* ─── 0. 试题题目（试卷标题，大字号突出显示） ─── */}
      <div className="border border-gray-200 rounded p-4">
        <div className="text-[13px] text-gray-500 mb-2">试题题目（试卷标题）：</div>
        <Input
          placeholder="导入文档或关联培训内容后自动带出，可编辑"
          value={examTitle}
          onChange={(e) => {
            titleEditedRef.current = true
            setExamTitle(e.target.value)
          }}
          maxLength={200}
          size="large"
          className="text-[18px] font-semibold"
          style={{ padding: '10px 16px' }}
        />
      </div>

      {/* ─── 1. 内容来源区 ─── */}
      <div className="border border-gray-200 rounded p-3">
        <div className="text-[14px] font-semibold mb-2">培训文件内容</div>

        {/* 1a. 自动解析区（签到表勾选的培训文件） */}
        <Spin spinning={resolving}>
          {resolvedFiles.length > 0 && (
            <div className="space-y-2 mb-3">
              <div className="text-[13px] text-gray-500">从签到表勾选的培训文件自动解析：</div>
              {resolvedFiles.map((f, i) => (
                <div key={`${f.name}-${i}`} className="border border-gray-200 rounded p-2">
                  <div className="flex items-center gap-2 mb-1">
                    <FileTextOutlined className="text-gray-400" />
                    <span className="text-[13px] font-medium">{f.name}</span>
                    {f.code && <span className="text-[12px] text-gray-400">（{f.code}）</span>}
                    {f.matched && f.content ? (
                      <Tag color="success">已解析</Tag>
                    ) : (
                      <Tag color="warning">未找到内容</Tag>
                    )}
                  </div>
                  {f.matched && f.content ? (
                    <div className="text-[12px] text-gray-500 max-h-16 overflow-auto bg-gray-50 rounded px-2 py-1">
                      {f.content.length > 120 ? `${f.content.slice(0, 120)}…` : f.content}
                    </div>
                  ) : (
                    <Input.TextArea
                      placeholder="未匹配到文件内容，可在此手动粘贴文本"
                      value={f.content}
                      onChange={(e) => setResolvedFiles((prev) => prev.map((x, j) => (j === i ? { ...x, content: e.target.value } : x)))}
                      autoSize={{ minRows: 2, maxRows: 4 }}
                      className="text-[13px]"
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </Spin>

        {/* 1b. 文件上传区（后端自动解析全文） */}
        <div className="mb-3">
          <div className="text-[13px] text-gray-500 mb-1">上传培训文档：</div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.docx,.doc,.wps,.pdf"
            multiple
            className="hidden"
            onChange={handleFileInputChange}
          />
          <Button icon={<UploadOutlined />} size="small" onClick={() => fileInputRef.current?.click()}>
            选择文件
          </Button>
          <div className="text-[12px] text-gray-400 mt-1">支持 .docx/.doc/.wps/.pdf/.txt/.md，上传后自动解析全文</div>

          {uploadedItems.length > 0 && (
            <div className="space-y-2 mt-2">
              {uploadedItems.map((it) => (
                <div key={it.uid} className="border border-gray-200 rounded p-2">
                  <div className="flex items-center gap-2 mb-1">
                    {it.status === 'parsing' ? (
                      <LoadingOutlined className="text-blue-500" />
                    ) : it.status === 'parsed' ? (
                      <FileTextOutlined className="text-gray-400" />
                    ) : (
                      <CloseCircleOutlined className="text-red-400" />
                    )}
                    <span className="text-[13px] font-medium">{it.name}</span>
                    {it.status === 'parsing' && <Tag color="processing">解析中…</Tag>}
                    {it.status === 'parsed' && <Tag color="success">已解析（{it.text.length} 字）</Tag>}
                    {it.status === 'error' && <Tag color="error">解析失败</Tag>}
                    <Button
                      type="text"
                      danger
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={() => removeUploadedItem(it.uid)}
                      className="ml-auto"
                    />
                  </div>
                  {it.status === 'parsed' && (
                    <div className="text-[12px] text-gray-500 max-h-16 overflow-auto bg-gray-50 rounded px-2 py-1">
                      {it.text.length > 120 ? `${it.text.slice(0, 120)}…` : it.text}
                    </div>
                  )}
                  {it.status === 'error' && (
                    <>
                      <div className="text-[12px] text-red-500 mb-1">{it.error}</div>
                      <Input.TextArea
                        placeholder="解析失败兜底：可在此手动粘贴该文档的文本内容"
                        value={it.text}
                        onChange={(e) => updateUploadedText(it.uid, e.target.value)}
                        autoSize={{ minRows: 2, maxRows: 4 }}
                        className="text-[13px]"
                      />
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 1c. 手动粘贴区（可选补充） */}
        <div>
          <div className="text-[13px] text-gray-500 mb-1">可选：补充粘贴文本</div>
          <Input.TextArea
            placeholder="可在此粘贴额外的培训文本内容（一般无需填写）"
            value={manualContent}
            onChange={(e) => setManualContent(e.target.value)}
            autoSize={{ minRows: 2, maxRows: 6 }}
          />
        </div>
      </div>

      {/* ─── 2. 出题配置区 ─── */}
      <div className="border border-gray-200 rounded p-3">
        <div className="text-[14px] font-semibold mb-2">出题配置</div>
        <Space wrap size={16}>
          <Space size={4}>
            <span className="text-[13px]">单选题数量</span>
            <InputNumber min={0} max={20} value={singleChoiceCount} onChange={(v) => setSingleChoiceCount(v || 0)} style={{ width: 70 }} />
          </Space>
          <Space size={4}>
            <span className="text-[13px]">多选题数量</span>
            <InputNumber min={0} max={20} value={multipleChoiceCount} onChange={(v) => setMultipleChoiceCount(v || 0)} style={{ width: 70 }} />
          </Space>
          <Space size={4}>
            <span className="text-[13px]">判断题数量</span>
            <InputNumber min={0} max={20} value={trueFalseCount} onChange={(v) => setTrueFalseCount(v || 0)} style={{ width: 70 }} />
          </Space>
          <Space size={4}>
            <span className="text-[13px]">填空题数量</span>
            <InputNumber min={0} max={20} value={fillBlankCount} onChange={(v) => setFillBlankCount(v || 0)} style={{ width: 70 }} />
          </Space>
        </Space>
        <div className="text-[12px] text-gray-400 mt-2">
          提示：题目按文件分批并行生成（受并发上限保护），题量越多耗时越长，一般需 1~3 分钟。生成过程可查看实时进度，不怕页面超时。
        </div>
      </div>

      {/* ─── 3. 操作按钮 ─── */}
      <Space>
        <Button
          type="primary"
          icon={<RobotOutlined />}
          onClick={handleGenerate}
          loading={generating}
          disabled={!hasMaterial || !active}
        >
          {generating ? 'AI 正在出题...' : 'AI 出题'}
        </Button>
        <Button
          icon={<DownloadOutlined />}
          onClick={handleExport}
          loading={exporting}
          disabled={!choiceQuestions.length && !trueFalseQuestions.length && !fillBlankQuestions.length}
        >
          导出试卷与答案
        </Button>
      </Space>

      {/* 出题进度提示（异步任务轮询期间显示） */}
      {generating && (
        <div className="flex items-center gap-2 text-[13px] text-blue-600">
          <LoadingOutlined />
          <span>{generatingProgress || '正在生成题目…'}</span>
        </div>
      )}

      {/* ─── 4. 题目预览编辑区 ─── */}
      {(choiceQuestions.length > 0 || trueFalseQuestions.length > 0 || fillBlankQuestions.length > 0) && (
        <div className="border border-gray-200 rounded p-3">
          <div className="text-[14px] font-semibold mb-2">
            题目预览（可直接编辑）
          </div>
          <Spin spinning={generating}>
            {/* 选择题 */}
            {choiceQuestions.length > 0 && (
              <>
                <div className="text-[13px] font-medium text-gray-600 mb-2">
                  选择题（共 {choiceQuestions.length} 题，{sectionScoreText(choiceScores)}）
                </div>
                <div className="space-y-3 mb-4">
                  {choiceQuestions.map((q, index) => (
                    <div key={q.number} className="border border-gray-200 rounded p-2 bg-gray-50">
                      <div className="flex items-start gap-2">
                        <span className="font-bold text-[13px] mt-1 whitespace-nowrap">{index + 1}.</span>
                        <Input.TextArea
                          value={q.question}
                          onChange={(e) => updateChoiceQuestion(index, 'question', e.target.value)}
                          autoSize={{ minRows: 1, maxRows: 4 }}
                          className="flex-1"
                        />
                        <Button
                          type="text"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                          onClick={() => setChoiceQuestions((prev) => prev.filter((_, i) => i !== index))}
                        />
                      </div>
                      <div className="pl-6 space-y-1 mt-1">
                        {q.options.map((opt, oIndex) => (
                          <div key={opt.label} className="flex items-center gap-2">
                            <span className="w-6 text-right text-[13px]">{opt.label}.</span>
                            <Input
                              value={opt.text}
                              onChange={(e) => updateChoiceOption(index, oIndex, 'text', e.target.value)}
                              className="flex-1"
                            />
                          </div>
                        ))}
                        <div className="flex items-center gap-2 pt-1">
                          <span className="text-[13px] whitespace-nowrap">答案：</span>
                          <Input
                            value={q.answer || ''}
                            onChange={(e) => updateChoiceQuestion(index, 'answer', e.target.value)}
                            placeholder="如 A / AB"
                            style={{ width: 120 }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <Button
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={() => setChoiceQuestions((prev) => [
                    ...prev,
                    {
                      number: prev.length + 1,
                      question: '',
                      options: [
                        { label: 'A', text: '' },
                        { label: 'B', text: '' },
                        { label: 'C', text: '' },
                        { label: 'D', text: '' },
                      ],
                      answer: '',
                    },
                  ])}
                  className="mb-4"
                >
                  添加选择题
                </Button>
              </>
            )}

            {/* 判断题 */}
            {trueFalseQuestions.length > 0 && (
              <>
                <div className="text-[13px] font-medium text-gray-600 mb-2">
                  判断题（共 {trueFalseQuestions.length} 题，{sectionScoreText(tfScores)}）
                </div>
                <div className="space-y-2 mb-4">
                  {trueFalseQuestions.map((q, index) => (
                    <div key={q.number} className="border border-gray-200 rounded p-2 bg-gray-50">
                      <div className="flex items-start gap-2">
                        <span className="font-bold text-[13px] mt-1 whitespace-nowrap">{index + 1}.</span>
                        <Input.TextArea
                          value={q.question}
                          onChange={(e) => updateTrueFalse(index, 'question', e.target.value)}
                          autoSize={{ minRows: 1, maxRows: 3 }}
                          className="flex-1"
                          placeholder="题目内容"
                        />
                        <Button
                          type="text"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                          onClick={() => setTrueFalseQuestions((prev) => prev.filter((_, i) => i !== index))}
                        />
                      </div>
                      <div className="pl-6 mt-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[13px] whitespace-nowrap">答案：</span>
                          <Input
                            value={q.answer || ''}
                            onChange={(e) => updateTrueFalse(index, 'answer', e.target.value)}
                            placeholder="√ 或 ×"
                            style={{ width: 120 }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <Button
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={() => setTrueFalseQuestions((prev) => [
                    ...prev,
                    { number: prev.length + 1, question: '', answer: '' },
                  ])}
                  className="mb-4"
                >
                  添加判断题
                </Button>
              </>
            )}

            {/* 填空题 */}
            {fillBlankQuestions.length > 0 && (
              <>
                <div className="text-[13px] font-medium text-gray-600 mb-2">
                  填空题（共 {fillBlankQuestions.length} 题，{sectionScoreText(fillScores)}）
                </div>
                <div className="space-y-2 mb-4">
                  {fillBlankQuestions.map((q, index) => (
                    <div key={q.number} className="border border-gray-200 rounded p-2 bg-gray-50">
                      <div className="flex items-start gap-2">
                        <span className="font-bold text-[13px] mt-1 whitespace-nowrap">{index + 1}.</span>
                        <Input.TextArea
                          value={q.question}
                          onChange={(e) => updateFillBlank(index, 'question', e.target.value)}
                          autoSize={{ minRows: 1, maxRows: 3 }}
                          className="flex-1"
                          placeholder="题目内容（填空处用______表示）"
                        />
                        <Button
                          type="text"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                          onClick={() => setFillBlankQuestions((prev) => prev.filter((_, i) => i !== index))}
                        />
                      </div>
                      <div className="pl-6 mt-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[13px] whitespace-nowrap">答案：</span>
                          <Input
                            value={q.answer || ''}
                            onChange={(e) => updateFillBlank(index, 'answer', e.target.value)}
                            placeholder="填空答案"
                            style={{ width: 240 }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <Button
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={() => setFillBlankQuestions((prev) => [
                    ...prev,
                    { number: prev.length + 1, question: '', answer: '' },
                  ])}
                >
                  添加填空题
                </Button>
              </>
            )}
          </Spin>
        </div>
      )}

      {/* ─── 空状态 ─── */}
      {!choiceQuestions.length && !trueFalseQuestions.length && !fillBlankQuestions.length && !generating && (
        <div className="flex flex-col items-center justify-center py-12 text-gray-400">
          <FileTextOutlined className="text-4xl mb-3" />
          <p className="text-[14px]">上传培训文档或关联培训内容后，点击「AI 出题」生成笔试试卷</p>
        </div>
      )}
    </div>
  )
}
