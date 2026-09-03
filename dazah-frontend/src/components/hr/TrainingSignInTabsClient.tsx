'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import { Tabs, Card, Segmented, Select, Space, Button, App, AutoComplete, Modal, Checkbox, Switch } from 'antd'
import { FormOutlined, CheckSquareOutlined, BellOutlined, SettingOutlined, BookOutlined, SaveOutlined, AuditOutlined, ToolOutlined, FileAddOutlined, FolderOpenOutlined, RobotOutlined, UserAddOutlined, PaperClipOutlined } from '@ant-design/icons'
import SignInSheetClient from './SignInSheetClient'
import TrainingEvaluationListClient from './TrainingEvaluationListClient'
import TrainingNotificationClient from './TrainingNotificationClient'
import TrainingPersonnelConfigModal from './TrainingPersonnelConfigModal'
import AttachmentContentModal, { type ContentEntry } from './AttachmentContentModal'
import DocumentCatalogPickerModal, { type DocumentCatalogPick } from './DocumentCatalogPickerModal'
import OralExamSheetClient from './OralExamSheetClient'
import PracticalExamSheetClient from './PracticalExamSheetClient'
import AiWrittenExamClient from './AiWrittenExamClient'
import TrainingAttachmentClient from './TrainingAttachmentClient'
import type { TrainingSessionData, TrainingDocExporter, AnnualTrainingPlan, AnnualTrainingPlanItem, TrainingPersonnelItem, PlanAttachmentSection, AiWrittenExamPayload } from '@/types/hr'
import {
  fetchAnnualTrainingPlans,
  fetchPlanItems,
  fetchPlanAttachmentSections,
  fetchUsedTrainingContent,
  fetchTrainingSession,
  fetchSessionDocuments,
  fetchNewHires,
} from '@/lib/api/client/hr'
import { resolveDocumentEntryContent } from '@/actions/quality'
import { fetchTrainingPersonnelConfigs, fetchTrainingDepartments } from '@/lib/api/client/hr'
import {
  createTrainingLedger,
  markTrainingContentUsed,
  upsertTrainingSession,
  upsertTrainingDocument,
  updateTrainingLedger,
} from '@/actions/hr'
import { downloadZip } from '@/lib/download'
import { with201SubDepts, unify201Dept, DEPT_201_MC, DEPT_201_DR, ensureDeptMappings, useDeptMappings } from './trainingDept'
import type { OralExamPayload } from './OralExamSheetClient'
import type { PracticalExamPayload } from './PracticalExamSheetClient'

const CURRENT_YEAR = new Date().getFullYear()

type TrainingAttachmentPayload = {
  items: { name: string; code: string | null }[]
}

// ── 培训类别自动识别（严格按桌面《培训类别.xlsx》八分类映射，未列出的不识别） ──
// 判定优先级：
// ① 文件编号优先——内容含文件编号（SOP/SMP/STP/KP 等代码+编号，如 SOP-PM-106/03、
//    SMP-QA-043/04）即判"管理类"（对应《培训类别.xlsx》第10行"岗位职责/SOP/STP/SMP"），
//    避免文件清单中的通用词（如"工作服"、"数据完整性"）误判其他分类；
// ② 无文件编号时，再按主题关键词匹配其余分类（数据安全/EHS/质量培训等）。
const TRAINING_TYPE_RULES: { type: string; keywords: string[] }[] = [
  // 无文件编号时的主题关键词分类（数据完整性/数据安全/隐私保护等）
  { type: '数据安全、隐私保护', keywords: ['数据完整性', '数据安全', '隐私保护'] },
  { type: 'EHS培训', keywords: ['安全生产', '三级安全', '消防安全', '火灾分类', '消防器材', '疏散逃生', '机械安全', '电气安全', '化工安全', '有毒有害', '劳保用品', '应急疏散', '特种作业', '起重吊装', '上锁挂牌', '受限空间', '脚手架作业', '风险辨识', '危险源', '危化品', '职业健康', '环保'] },
  { type: '质量培训', keywords: ['清真管理体系', '非转基因', 'ICH', 'ISO9001', 'ISO22000', '兽药', 'GMP', '微生物'] },
  { type: '管理类', keywords: ['岗位职责', '工艺规程', '质量标准', '管理制度', '管理程序'] },
  { type: '领导力培训', keywords: ['非人力资源经理', '人力资源管理沙盘', '领导力'] },
  { type: '多元化', keywords: ['用工管理制度', '用工管理'] },
  { type: '反贪腐类', keywords: ['反贪腐'] },
  { type: '负责任营销', keywords: ['负责任营销', '销售、宣传、法务合规'] },
]

// 文件编号模式：SOP/SMP/STP/KP/QP/QS 等文件代码 + 编号段（如 SOP-PM-106/03、KP-SC-MV-001/07）
const FILE_CODE_RE = /(?:SOP|SMP|STP|KP|QP|QS)[-–—－]?[A-Z0-9]{1,4}(?:[-–—－][A-Z0-9]{1,4})+(?:\/\d{1,3})?/i

export function matchTrainingType(topic: string, content: string): string | undefined {
  const fullText = `${topic || ''} ${content || ''}`
  // ① 文件编号优先：含文件编号即管理类
  if (FILE_CODE_RE.test(fullText)) return '管理类'
  // ② 无文件编号：按主题关键词匹配（主题优先，未命中再结合内容全文）
  const topicText = (topic || '').toUpperCase()
  for (const { type, keywords } of TRAINING_TYPE_RULES) {
    if (keywords.some((k) => topicText.includes(k.toUpperCase()))) return type
  }
  const upper = fullText.toUpperCase()
  for (const { type, keywords } of TRAINING_TYPE_RULES) {
    if (keywords.some((k) => upper.includes(k.toUpperCase()))) return type
  }
  return undefined
}

// ── 人药/兽药自动识别（按培训内容关键词匹配） ──
// 兽药关键词更具体，优先匹配；全部未命中返回 undefined
const DRUG_CATEGORY_RULES: { category: string; keywords: string[] }[] = [
  { category: '兽药', keywords: ['兽药', '多拉菌素', '林可霉素', '预混剂', '芬苯达唑', '氟苯尼考'] },
  { category: '人药', keywords: ['ICH', 'GMP', '药品'] },
]

export function matchDrugCategory(topic: string, content: string): string | undefined {
  const text = `${topic || ''} ${content || ''}`.toUpperCase()
  for (const { category, keywords } of DRUG_CATEGORY_RULES) {
    if (keywords.some((k) => text.includes(k.toUpperCase()))) return category
  }
  return undefined
}

// ── 签到表培训题目格式化：选中 ≤2 份显示全部；>2 份只显示前 2 份，剩余写"等N份文件详见附件"（附件完整清单见培训附件页）──
export function formatTopicForSignin(entries: { name: string; code?: string | null; resolvedCode?: string | null }[]): string {
  const fmt = (e: { name: string; code?: string | null; resolvedCode?: string | null }) =>
    e.resolvedCode || e.code ? `《${e.name}》（${e.resolvedCode || e.code}）` : `《${e.name}》`
  if (entries.length <= 2) return entries.map(fmt).join('、')
  return `${entries.slice(0, 2).map(fmt).join('、')}等${entries.length}份文件详见附件`
}

const YEAR_OPTIONS = [CURRENT_YEAR - 1, CURRENT_YEAR, CURRENT_YEAR + 1].map((y) => ({ value: y, label: `${y} 年` }))

// ── "附件X"引用提取（与后端 attachment_parser.normalize_annex_no 逻辑一致）──
const ANNEX_RE = /附件\s*([0-9０-９一二三四五六七八九十]+)/g
const CN_DIGIT: Record<string, number> = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 }

export function cnToInt(s: string): number | null {
  const half = s.replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0))
  if (/^\d+$/.test(half)) return parseInt(half, 10)
  if (!half.includes('十')) return CN_DIGIT[half] ?? null
  const idx = half.indexOf('十')
  const tens = half.slice(0, idx)
  const ones = half.slice(idx + 1)
  return (tens ? CN_DIGIT[tens] ?? 1 : 1) * 10 + (ones ? CN_DIGIT[ones] ?? 0 : 0)
}

/** 从项目文本提取所有"附件X"引用，归一化为"附件{n}"（去重保序） */
export function extractAnnexRefs(text: string): string[] {
  const refs: string[] = []
  for (const m of text.matchAll(ANNEX_RE)) {
    const n = cnToInt(m[1])
    const key = n ? `附件${n}` : ''
    if (key && !refs.includes(key)) refs.push(key)
  }
  return refs
}

export default function TrainingSignInTabsClient() {
  const { message, modal } = App.useApp()
  const [exportingAll, setExportingAll] = useState(false)
  const [addingLedger, setAddingLedger] = useState(false)
  const [ledgerPresented, setLedgerPresented] = useState(true)
  const [ledgerConfirmOpen, setLedgerConfirmOpen] = useState(false)
  const [docPickerOpen, setDocPickerOpen] = useState(false)
  const [fetchingNewHires, setFetchingNewHires] = useState(false)
  const [session, setSession] = useState<TrainingSessionData>({})
  const [configOpen, setConfigOpen] = useState(false)

  // ── 顶部"培训范围"控制 ──
  const [level, setLevel] = useState<'公司级' | '部门级'>('公司级')
  const [year, setYear] = useState<number>(CURRENT_YEAR)
  const [scopeDept, setScopeDept] = useState<string | undefined>()
  const [departments, setDepartments] = useState<{ value: string; label: string }[]>([])
  const [plans, setPlans] = useState<AnnualTrainingPlan[]>([])
  const [planItems, setPlanItems] = useState<AnnualTrainingPlanItem[]>([])
  const [selectedPlanId, setSelectedPlanId] = useState<string | undefined>()
  const [selectedItemId, setSelectedItemId] = useState<string | undefined>()

  // ── 计划附件内容选择（弹窗勾选文件清单 → 录入培训内容；已培训置灰）──
  const [planSections, setPlanSections] = useState<PlanAttachmentSection[]>([])
  // 弹窗实际展示的条目：按所选项目"附件X"引用过滤后的 section 子集
  const [modalSections, setModalSections] = useState<PlanAttachmentSection[]>([])
  const [contentModalOpen, setContentModalOpen] = useState(false)
  // entry_id：解析命中的文件管理条目 ID（勾选时锁定，AI 出题按此 ID 精确读取内容）
  const [checkedEntries, setCheckedEntries] = useState<(ContentEntry & { resolvedCode: string | null; entry_id?: string | null })[]>([])
  const [usedNames, setUsedNames] = useState<Set<string>>(new Set())

  useEffect(() => {
    fetchUsedTrainingContent()
      .then((list) => setUsedNames(new Set(list.map((x) => x.entry_name))))
      .catch(() => {})
  }, [])

  // 勾选内容 → 《文件名称》（最新编号）、…
  const contentFormatted = checkedEntries
    .map((e) => (e.resolvedCode ? `《${e.name}》（${e.resolvedCode}）` : `《${e.name}》`))
    .join('、')

  // ── 培训会话（保存历史 + 台账关联 + URL 恢复） ──
  const [sessionId, setSessionId] = useState<string | undefined>()
  // 会话 ID 同存 ref：同一次异步流程内（入台账→存资料）闭包 sessionId
  // 不会及时更新，曾导致一次点击创建两个会话；ref 保证流程内幂等
  const sessionIdRef = useRef<string | undefined>(undefined)
  const sessionInFlightRef = useRef<Promise<string> | null>(null)
  // ── 自动保存（10s 一次；培训有内容才保存；内容未变跳过）──
  const sessionRef = useRef<TrainingSessionData>({})
  const lastSavedSnapshotRef = useRef<string | undefined>(undefined)
  const autoSaveInFlightRef = useRef(false)
  const restoreFinishedRef = useRef(false)
  const [lastAutoSaveAt, setLastAutoSaveAt] = useState<string | undefined>()
  const [autoSaveFailed, setAutoSaveFailed] = useState(false)
  const assignSessionId = useCallback((id: string | undefined) => {
    sessionIdRef.current = id
    setSessionId(id)
  }, [])
  const [activeTab, setActiveTab] = useState('sign-in')

  // 新建培训资料：重置会话并强制重挂载全部子表单
  const [resetKey, setResetKey] = useState(0)
  const handleNewTraining = () => {
    modal.confirm({
      title: '新建培训资料',
      content: '将清空当前培训资料（签到/评估/通知/口试/实操/笔试）并开始新建一份，确定继续吗？',
      okText: '新建',
      cancelText: '取消',
      onOk: () => {
        setSession({})
        assignSessionId(undefined)
        sessionRef.current = {}
        lastSavedSnapshotRef.current = undefined
        setAutoSaveFailed(false)
        setLastAutoSaveAt(undefined)
        setOralPayload(null)
        setPracticalPayload(null)
        setAiWrittenPayload(null)
        setAttachmentPayload(null)
        setEvalDraft(null)
        setNotifyDraft(null)
        setCheckedEntries([])
        setSelectedPlanId(undefined)
        setSelectedItemId(undefined)
        setPlanSections([])
        setModalSections([])
        try { localStorage.removeItem('hr_training_last_session') } catch { /* ignore */ }
        setActiveTab('sign-in')
        setResetKey((k) => k + 1)
      },
    })
  }
  const [oralPayload, setOralPayload] = useState<OralExamPayload | null>(null)
  const [practicalPayload, setPracticalPayload] = useState<PracticalExamPayload | null>(null)
  const [aiWrittenPayload, setAiWrittenPayload] = useState<AiWrittenExamPayload | null>(null)
  const [attachmentPayload, setAttachmentPayload] = useState<TrainingAttachmentPayload | null>(null)
  const [evalDraft, setEvalDraft] = useState<Record<string, unknown> | null>(null)
  const [notifyDraft, setNotifyDraft] = useState<Record<string, unknown> | null>(null)

  const buildSessionUpsert = (s: TrainingSessionData) => ({
    training_level: s.training_level,
    plan_year: s.plan_year,
    department: s.department,
    trainee_departments: s.trainee_departments,
    topic: s.topic,
    training_date: s.training_date,
    time_start: s.training_time_start,
    time_end: s.training_time_end,
    training_method: s.training_method,
    instructor: s.instructor,
    actual_count: s.actual_count,
    employee_names: s.employee_names,
    employee_dept_map: s.employee_dept_map,
    checked_content: s.checked_content,
  })

  const ensureSession = async (): Promise<string> => {
    if (sessionIdRef.current) return sessionIdRef.current
    if (sessionInFlightRef.current) return sessionInFlightRef.current
    const p = (async () => {
      const id = await upsertTrainingSession(buildSessionUpsert(session))
      assignSessionId(id)
      try { localStorage.setItem('hr_training_last_session', id) } catch { /* ignore */ }
      return id
    })()
    sessionInFlightRef.current = p
    try {
      return await p
    } finally {
      sessionInFlightRef.current = null
    }
  }

  // 勾选的附件培训内容 → session.content（评估表"培训教材"自动录入来源）
  useEffect(() => {
    // 依赖变化时同步合并 session.content：仅 contentFormatted 变化触发，非每次渲染
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSession((prev) => (prev.content === contentFormatted ? prev : { ...prev, content: contentFormatted }))
  }, [contentFormatted])

  // 各 Tab 组件注册自己的草稿序列化函数（未访问的 Tab 无注册则跳过）
  const docBuildersRef = useRef<Record<string, () => Record<string, unknown> | null>>({})
  const registerDocBuilder = useCallback((type: string, fn: () => Record<string, unknown> | null) => {
    docBuildersRef.current[type] = fn
  }, [])

  // 各 Tab 组件注册自己的导出函数（返回生成文档列表，null 表示无内容跳过），供顶部"一键导出"聚合
  const exportersRef = useRef<Record<string, TrainingDocExporter>>({})
  const registerExporter = useCallback((type: string, fn: TrainingDocExporter) => {
    exportersRef.current[type] = fn
  }, [])

  // 保存全部五类资料草稿（签到/评估/通知/口试/实操，后两类有内容才存），返回保存条数
  const saveAllDocs = async (): Promise<number> => {
    const id = await ensureSession()
    // 同步会话头表字段（topic/人员/日期/级别等）：恢复流程从 sessions 表读这些，
    // 不更新会导致刷新后 topic/人员等被旧值覆盖
    if (id) {
      try {
        await upsertTrainingSession({ id, ...buildSessionUpsert(session) })
      } catch (e) {
        console.warn('[saveAllDocs] 会话头表同步失败（草稿仍会保存）', e)
      }
    }
    const entries: { type: string; payload: Record<string, unknown> }[] = [
      { type: 'sign_in', payload: { ...session } as unknown as Record<string, unknown> },
    ]
    for (const t of ['evaluation', 'notification', 'oral_exam', 'practical_exam', 'ai_written_exam', 'attachment']) {
      const p = docBuildersRef.current[t]?.()
      if (p) entries.push({ type: t, payload: p })
    }
    await Promise.all(
      entries.map((e) =>
        upsertTrainingDocument({ session_id: id, doc_type: e.type, title: session.topic || '', payload: e.payload }),
      ),
    )
    return entries.length
  }

  const [savingAll, setSavingAll] = useState(false)

  // ── 自动保存：10s 轮询；培训有内容（topic 非空/已选计划）才保存；内容未变跳过 ──
  // 会话/草稿的变化走 setSession 或 docBuildersRef，统一用"指纹"检测是否有新内容
  const saveAllDocsRef = useRef(saveAllDocs)
  saveAllDocsRef.current = saveAllDocs

  const computeContentFingerprint = useCallback((): string | null => {
    const s = sessionRef.current
    // 培训题目或内容概要有内容时才进入自动保存（避免建空会话）
    if (!(s.topic || '').trim()) return null
    try {
      const docs: Record<string, unknown> = {}
      for (const t of ['evaluation', 'notification', 'oral_exam', 'practical_exam', 'ai_written_exam', 'attachment']) {
        const p = docBuildersRef.current[t]?.()
        if (p) docs[t] = p
      }
      // session 全字段参与指纹（content/location/issuer 等虽不存 sessions 表，
      // 但会进 sign_in 草稿 payload，变化必须触发保存）
      return JSON.stringify({ session: { ...s }, docs })
    } catch {
      return null
    }
  }, [])

  const persistAutoSave = useCallback(async () => {
    if (autoSaveInFlightRef.current) return
    const fp = computeContentFingerprint()
    if (fp === null || fp === lastSavedSnapshotRef.current) return
    autoSaveInFlightRef.current = true
    try {
      await saveAllDocsRef.current()
      lastSavedSnapshotRef.current = fp
      setAutoSaveFailed(false)
      setLastAutoSaveAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
    } catch (e) {
      // 保存失败不更新指纹，下个周期自动重试；但必须让用户可见（DESIGN §7）
      setAutoSaveFailed(true)
      console.warn('[AutoSave] 自动保存失败，将在下个周期重试', e)
    } finally {
      autoSaveInFlightRef.current = false
    }
  }, [computeContentFingerprint])

  // session 同步进 ref（定时器/隐藏兜底读取最新值，避免闭包旧值）；
  // 恢复完成后把当前内容设为"已保存"基线，避免刷新恢复后立刻触发一次无意义自动保存
  // 该 effect 刻意不设依赖：ref 需在每次渲染后同步最新值（闭包兜底）
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    sessionRef.current = session
    if (restoreFinishedRef.current) {
      restoreFinishedRef.current = false
      const fp = computeContentFingerprint()
      if (fp !== null) lastSavedSnapshotRef.current = fp
      setLastAutoSaveAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
    }
  })

  // 10 秒轮询自动保存
  useEffect(() => {
    const timer = setInterval(() => {
      void persistAutoSave()
    }, 10_000)
    return () => clearInterval(timer)
  }, [persistAutoSave])

  // 页面隐藏（切走/刷新/关闭）前兜底保存一次，把丢失窗口从 10s 压到接近 0
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') void persistAutoSave()
    }
    window.addEventListener('visibilitychange', onVisibility)
    return () => window.removeEventListener('visibilitychange', onVisibility)
  }, [persistAutoSave])

  // 手动保存成功后同步指纹，避免紧接着被自动保存重复写一次
  const handleSaveAllDocsManual = async () => {
    setSavingAll(true)
    try {
      const n = await saveAllDocs()
      const fp = computeContentFingerprint()
      if (fp !== null) lastSavedSnapshotRef.current = fp
      setAutoSaveFailed(false)
      setLastAutoSaveAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
      message.success(`已保存 ${n} 类培训资料`)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '保存失败')
    } finally {
      setSavingAll(false)
    }
  }

  // 台账"做二级培训"入口：新二级会话入台账后，自动把源台账副本标记为已完成二级
  const parentRecordIdRef = useRef<string | undefined>(undefined)

  // 恢复（?session=xx&doc=yy 台账"打开编辑"跳转；否则恢复上次保存的会话，避免保存后刷新丢失）
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const sid = params.get('session') || localStorage.getItem('hr_training_last_session')
    const docType = params.get('doc')
    const parentRecord = params.get('parent_record')
    if (parentRecord) {
      parentRecordIdRef.current = parentRecord
    }
    if (!sid) return
    ;(async () => {
      try {
        const sess = await fetchTrainingSession(sid)
        assignSessionId(sid)
        setSession((prev) => ({
          ...prev,
          training_level: sess.training_level ?? prev.training_level,
          plan_year: sess.plan_year ?? prev.plan_year,
          department: sess.department ?? prev.department,
          trainee_departments: sess.trainee_departments ?? prev.trainee_departments,
          topic: sess.topic ?? prev.topic,
          training_date: sess.training_date ?? prev.training_date,
          training_time_start: sess.time_start ?? prev.training_time_start,
          training_time_end: sess.time_end ?? prev.training_time_end,
          training_method: sess.training_method ?? prev.training_method,
          instructor: sess.instructor ?? prev.instructor,
          actual_count: sess.actual_count ?? prev.actual_count,
          employee_names: sess.employee_names ?? prev.employee_names,
          employee_dept_map: sess.employee_dept_map ?? prev.employee_dept_map,
          checked_content: sess.checked_content ?? prev.checked_content,
        }))
        // 与部门级一致：恢复会话时优先按勾选锁定的条目 ID 解析编号（旧数据无 entry_id 才按名称匹配）
        // 批量解析一次请求完成（避免 N 个文件 N 次请求导致页面长时间空白）
        const entries = sess.checked_content ?? []
        if (entries.length) {
          const resolvedItems = await resolveDocumentEntryContent(
            entries.map((c) => ({ name: c.name, entry_id: c.entry_id ?? null })),
          ).catch(() => [])
          const resolved = entries.map((c) => {
            const item = resolvedItems.find((x) => x.name === c.name)
            const code = item?.code ?? c.code ?? null
            return { name: c.name, code, resolvedCode: code, entry_id: c.entry_id ?? item?.entry_id ?? null }
          })
          setCheckedEntries(resolved as (typeof checkedEntries)[number][])
          // 签到表题目：≤2 份显示全部，>2 份截断为前 2 份 + 详见附件（完整清单在培训附件页/台账）
          const formatted = formatTopicForSignin(resolved)
          setSession((prev) => ({
            ...prev,
            topic: formatted || prev.topic,
            checked_content: resolved.map((e) => ({
              name: e.name,
              code: e.resolvedCode,
              entry_id: e.entry_id ?? null,
            })),
          }))
        }
        // 恢复全部五类草稿（列表接口已带 payload）
        const docs = await fetchSessionDocuments(sid)
        for (const d of docs) {
          if (d.doc_type === 'oral_exam') setOralPayload(d.payload as unknown as OralExamPayload)
          else if (d.doc_type === 'practical_exam') setPracticalPayload(d.payload as unknown as PracticalExamPayload)
          else if (d.doc_type === 'ai_written_exam') setAiWrittenPayload(d.payload as unknown as AiWrittenExamPayload)
          else if (d.doc_type === 'attachment') setAttachmentPayload(d.payload as unknown as TrainingAttachmentPayload)
          else if (d.doc_type === 'evaluation') {
            const evaluationDraft = d.payload
            setEvalDraft(evaluationDraft)
            // 考核方式从评估表草稿恢复（AI 笔试/口试 Tab 联动依赖 session.assessment_method）
            if (typeof evaluationDraft.assessment_method === 'string') {
              setSession((prev) => ({
                ...prev,
                assessment_method: evaluationDraft.assessment_method as string,
              }))
            }
          } else if (d.doc_type === 'notification') setNotifyDraft(d.payload)
        }
        if (docType) setActiveTab(docType)
        // 恢复完成后标记：session 同步 effect 将当前内容设为"已保存"基线，
        // 避免刷新恢复后 10 秒内立刻触发一次无意义自动保存
        restoreFinishedRef.current = true
      } catch (err) {
        console.error('[TrainingTabs] restore session failed:', err)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── 人员配置下拉 ──
  const [personnelConfigs, setPersonnelConfigs] = useState<import('@/types/hr').TrainingPersonnelConfig[]>([])
  const [selectedConfigIds, setSelectedConfigIds] = useState<string[]>([])
  const [loadingConfigs, setLoadingConfigs] = useState(false)

  // 级别/部门变化时重载该部门人员配置列表
  const reloadPersonnelConfigs = useCallback(() => {
    if (level === '部门级' && !scopeDept) {
      setPersonnelConfigs([])
      return
    }
    setLoadingConfigs(true)
    fetchTrainingPersonnelConfigs({
      level,
      department: level === '部门级' ? scopeDept : undefined,
    })
      .then((res) => {
        setPersonnelConfigs(res.data || [])
        setSelectedConfigIds([])
      })
      .catch(() => setPersonnelConfigs([]))
      .finally(() => setLoadingConfigs(false))
  }, [level, scopeDept])

  useEffect(() => {
    queueMicrotask(reloadPersonnelConfigs)
  }, [reloadPersonnelConfigs])

  // 配置弹窗关闭后刷新下拉（新建/保存/删除配置后立即可选）
  useEffect(() => {
    // 依赖变化时同步刷新下拉：仅 configOpen 变化触发，非每次渲染
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (!configOpen) reloadPersonnelConfigs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configOpen])

  const { version: mappingVersion } = useDeptMappings()
  useEffect(() => {
    ensureDeptMappings().catch(() => {})
    fetchTrainingDepartments()
      .then((depts) => {
        setDepartments(with201SubDepts(depts).map((d) => ({ value: d, label: d })))
      })
      .catch(() => setDepartments([]))
    // 映射配置加载/变更后重新拉取部门列表（exclude/force_show 规则随配置生效）

  }, [mappingVersion])

  // 级别/年度/部门变化时，加载对应年度培训计划
  useEffect(() => {
    let cancelled = false
    // 公司级不传 department，部门级传具体部门
    const deptParam = level === '部门级' ? scopeDept : undefined
    fetchAnnualTrainingPlans({ year, department: deptParam, page_size: 100 })
      .then((res) => {
        if (cancelled) return
        // 严格按 plan_level 过滤，确保公司级只显示公司级计划
        const allPlans = res.data || []
        const list = allPlans.filter((p) => p.plan_level === level)
        setPlans(list)
        setSelectedPlanId(undefined)
        setPlanItems([])
        setSelectedItemId(undefined)
      })
      .catch((err) => {
        console.error('[TrainingTabs] fetch plans failed:', err)
        setPlans([])
      })
    return () => { cancelled = true }
  }, [level, year, scopeDept])

  const applyScope = (next: Partial<{ level: '公司级' | '部门级'; dept: string | undefined }>) => {
    const lv = next.level ?? level
    const dp = next.dept !== undefined ? next.dept : scopeDept
    setSession((prev) => ({
      ...prev,
      training_level: lv,
      plan_year: year,
      // 公司级培训落款部门固定为"人事行政部"（可在培训通知中修改 issuer_department）
      department: lv === '部门级' && dp ? dp : '人事行政部',
      trainee_departments: lv === '部门级' && dp ? [unify201Dept(dp)] : [],
    }))
  }

  // 切换级别/部门时立即清空计划选择，避免旧计划残留关联
  const resetPlanSelection = () => {
    setSelectedPlanId(undefined)
    setPlanItems([])
    setSelectedItemId(undefined)
    setPlanSections([])
    setModalSections([])
    setCheckedEntries([])
  }
  const handleLevelChange = (v: '公司级' | '部门级') => {
    setLevel(v)
    resetPlanSelection()
    applyScope({ level: v })
  }
  const handleDeptChange = (v: string) => {
    setScopeDept(v)
    resetPlanSelection()
    applyScope({ dept: v })
  }
  const handleYearChange = (v: number) => {
    setYear(v)
    setSession((prev) => ({ ...prev, plan_year: v }))
  }

  const handlePlanChange = (planId: string) => {
    setSelectedPlanId(planId)
    setSelectedItemId(undefined)
    setPlanItems([])
    setCheckedEntries([])
    setPlanSections([])
    setModalSections([])
    if (planId) {
      fetchPlanItems(planId).then((res) => setPlanItems(res.data || [])).catch(() => setPlanItems([]))
      fetchPlanAttachmentSections(planId).then((res) => setPlanSections(res.data || [])).catch(() => setPlanSections([]))
    } else {
      setPlanSections([])
    }
  }

  const handleItemChange = (itemId: string) => {
    setSelectedItemId(itemId)
    setCheckedEntries([])
    const item = planItems.find((i) => i.id === itemId)
    if (item) {
      const text = item.content_textbook || item.content_and_textbook || ''
      setSession((prev) => ({
        ...prev,
        topic: text || prev.topic,
        training_method: item.training_method || prev.training_method,
      }))
      // 计划有条目时弹出附件内容选择：按项目文本"附件X"引用在 section 级别过滤，仅展示对应条目
      if (planSections.length) {
        const refs = extractAnnexRefs(text)
        const matched = refs.length
          ? planSections.filter((s) => s.annex_no && refs.includes(s.annex_no))
          : []
        // 项目未引用附件或引用无对应条目时，回退展示全部条目
        setModalSections(matched.length ? matched : planSections)
        setContentModalOpen(true)
      } else {
        setModalSections([])
      }
    } else {
      setModalSections([])
    }
  }

  // 弹窗确认：按名称批量查最新编号后录入培训内容（同时写入结构化勾选数据供口试 AI 出题）
  const handleContentConfirm = async (selected: ContentEntry[]) => {
    // 批量解析一次请求完成（避免 N 个文件 N 次请求）
    const resolvedItems = await resolveDocumentEntryContent(selected.map((e) => e.name)).catch(
      () => [],
    )
    const resolved = selected.map((e) => {
      const item = resolvedItems.find((x) => x.name === e.name)
      return { ...e, resolvedCode: item?.code ?? e.code, entry_id: item?.entry_id ?? null }
    })
    setCheckedEntries(resolved)
    // 签到表题目：≤2 份显示全部，>2 份截断为前 2 份 + 详见附件（完整清单在培训附件页/台账）
    const formatted = formatTopicForSignin(resolved)
    if (resolved.length) {
      setSession((prev) => ({
        ...prev,
        topic: formatted,
        checked_content: resolved.map((e) => ({
          name: e.name,
          code: e.resolvedCode,
          entry_id: e.entry_id ?? null,
        })),
      }))
    }
    setContentModalOpen(false)
  }

  // 从文件管理选择确认：勾选条目 ID 直接锁定（出题按 ID 精确读取，不再按名称匹配最新版）
  const handleDocPickerConfirm = (items: DocumentCatalogPick[]) => {
    if (!items.length) {
      setDocPickerOpen(false)
      return
    }
    void (async () => {
      const resolvedItems = await resolveDocumentEntryContent(
        items.map((i) => ({ name: i.name, entry_id: i.entryId })),
      ).catch(() => [])
      setCheckedEntries((prev) => {
        const map = new Map(prev.map((e) => [e.name, e]))
        items.forEach((i) => {
          if (map.has(i.name)) return
          const item = resolvedItems.find((x) => x.name === i.name)
          const code = item?.code ?? i.code ?? null
          map.set(i.name, {
            key: `doc-${i.name}`,
            group: '文件管理',
            name: i.name,
            code,
            attachment_id: '',
            resolvedCode: code,
            entry_id: i.entryId,
          })
        })
        const merged = Array.from(map.values())
        // 与附件内容选择一致：签到表题目按勾选清单刷新
        const formatted = formatTopicForSignin(merged)
        setSession((prev) => ({
          ...prev,
          topic: formatted,
          checked_content: merged.map((e) => ({
            name: e.name,
            code: e.resolvedCode,
            entry_id: e.entry_id ?? null,
          })),
        }))
        return merged as (typeof checkedEntries)[number][]
      })
      setDocPickerOpen(false)
      message.success(`已从文件管理选择 ${items.length} 个文件条目`)
    })()
  }

  const handleSessionChange = useCallback((update: TrainingSessionData) => {
    setSession((prev) => ({ ...prev, ...update }))
  }, [])

  // 将人员名单应用到三个表单（同时带上姓名→部门映射，供签到表显示部门列）
  const applyPersonnel = (personnel: TrainingPersonnelItem[]) => {
    const names = personnel.map((p) => p.name)
    const depts = Array.from(new Set(personnel.map((p) => p.department).filter(Boolean))) as string[]
    const deptMap: Record<string, string> = {}
    personnel.forEach((p) => {
      if (p.name && p.department) deptMap[p.name] = p.department
    })
    setSession((prev) => ({
      ...prev,
      employee_names: names,
      employee_dept_map: deptMap,
      trainee_departments:
        level === '部门级' && scopeDept
          ? [unify201Dept(scopeDept)]
          : depts.length
            ? [...new Set(depts.map(unify201Dept))].filter(Boolean)
            : prev.trainee_departments,
    }))
  }

  // 选择配置后加载班组人员（支持多选：多个班组人员合并去重后一起加载）
  const handleSelectConfigs = (configIds: string[]) => {
    setSelectedConfigIds(configIds)
    const selected = personnelConfigs.filter((c) => configIds.includes(c.id))
    const seen = new Set<string>()
    const merged: TrainingPersonnelItem[] = []
    selected.forEach((cfg) => {
      ;(cfg.personnel || []).forEach((p) => {
        const key = `${p.name}|${p.department || ''}`
        if (!seen.has(key)) {
          seen.add(key)
          merged.push(p)
        }
      })
    })
    if (merged.length) {
      applyPersonnel(merged)
      const names = selected.map((c) => c.config_name).join('、')
      message.success(`已加载「${names}」共 ${merged.length} 人`)
    }
  }

  // 拉取入职一周内的新员工（按 factory_entry_date 判定，姓名+部门去重）
  const handleFetchNewHires = async () => {
    setFetchingNewHires(true)
    try {
      const res = await fetchNewHires(7)
      const newHires = res.data || []
      if (newHires.length === 0) {
        message.info('最近一周没有新入职员工')
        return
      }
      // 转为 TrainingPersonnelItem[]
      const newItems: TrainingPersonnelItem[] = newHires.map((h) => ({
        name: h.name,
        employee_number: h.employee_number || undefined,
        department: h.department,
      }))
      // 与已有人员合并去重（按姓名+部门）
      const existingNames = new Set(
        (session.employee_names || []).map((n) => n?.trim()).filter(Boolean)
      )
      const merged: TrainingPersonnelItem[] = [
        ...(session.employee_names || []).map((name) => ({
          name,
          department: (session.employee_dept_map || {})[name],
        })),
        ...newItems.filter(
          (item) => !existingNames.has(item.name)
        ),
      ]
      applyPersonnel(merged)
      const addedCount = merged.length - (session.employee_names || []).length
      message.success(`已拉取 ${addedCount} 位入职一周内的新员工（共 ${merged.length} 人）`)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '拉取新员工失败')
    } finally {
      setFetchingNewHires(false)
    }
  }

  // ── 顶部导出/操作（数据来自共享 session）──

  const ensureBase = () => {
    if (!session.training_date) {
      message.warning('请先在培训签到表选择培训日期')
      return false
    }
    if (!session.topic) {
      message.warning('请先关联计划项目或填写培训内容')
      return false
    }
    return true
  }

  const computeDurationHours = (): number | undefined => {
    if (!session.training_time_start || !session.training_time_end) return undefined
    const [h1, m1] = session.training_time_start.split(':').map(Number)
    const [h2, m2] = session.training_time_end.split(':').map(Number)
    const diff = h2 * 60 + m2 - (h1 * 60 + m1)
    if (diff <= 0) return undefined
    return Math.round(diff / 30) / 2
  }

  // 有效受训人员（签到表行内编辑可能留下空行，消费端统一过滤）
  const sessionNames = (session.employee_names || []).filter((n) => n && n.trim())

  // 一键导出：聚合各 Tab 注册的导出器，把已编辑的资料打包为 zip 一次下载
  const handleExportAll = async () => {
    if (!ensureBase()) return
    setExportingAll(true)
    try {
      const results = await Promise.all(
        Object.values(exportersRef.current).map((fn) => fn().catch((err) => {
          console.error('[TrainingTabs] export failed:', err)
          return null
        })),
      )
      const entries = results.filter((r): r is NonNullable<typeof r> => !!r).flat()
      if (entries.length === 0) {
        message.warning('没有可导出的培训资料')
        return
      }
      // 压缩包命名：日期-时间段-培训内容（如 20260812-09.00-11.00-《xx》等12份文件）
      const dateStr = (session.training_date || '').replace(/-/g, '') || 'nodate'
      const timeStr =
        [session.training_time_start, session.training_time_end]
          .filter(Boolean)
          .map((t) => (t || '').replace(/:/g, '.'))
          .join('-') || 'notime'
      // 培训内容：去除文件名非法字符并截断，避免文件系统限制
      const contentStr = (session.topic || '培训资料').replace(/[\\/:*?"<>|]/g, '').slice(0, 50)
      await downloadZip(entries, `${dateStr}-${timeStr}-${contentStr}`)
      message.success(`已打包导出 ${entries.length} 份资料`)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '导出失败')
    } finally {
      setExportingAll(false)
    }
  }

  // 台账=培训级记录：录入培训信息本身，不再要求工号；同一会话禁止重复入台账
  const handleAddToLedger = async () => {
    if (!ensureBase()) return
    if (!session.training_date || !session.topic) {
      message.warning('请先填写培训日期和培训题目')
      return
    }
    if (sessionId) {
      try {
        const res = await fetch(`/api/v1/hr/training-ledgers?session_id=${sessionId}&page_size=1`, { cache: 'no-store' })
        if (res.ok) {
          const json = await res.json()
          if ((json.meta?.total || 0) > 0) {
            message.warning('本次培训已添加到培训台账，请勿重复添加')
            return
          }
        }
      } catch { /* 检查失败不阻断 */ }
    }
    // 打开受控确认弹窗（"是否呈现"开关在弹窗内受控切换）
    setLedgerConfirmOpen(true)
  }

  const doAddToLedger = async () => {
    const timeStart = session.training_time_start || ''
    const timeEnd = session.training_time_end || ''
    setAddingLedger(true)
    try {
      // 确认后再复核：防并发/连点导致重复入台账
      if (sessionIdRef.current) {
        try {
          const chk = await fetch(
            `/api/v1/hr/training-ledgers?session_id=${sessionIdRef.current}&page_size=1`,
            { cache: 'no-store' },
          )
          if (chk.ok) {
            const json = await chk.json()
            if ((json.meta?.total || 0) > 0) {
              message.warning('本次培训已添加到培训台账，请勿重复添加')
              return
            }
          }
        } catch { /* 检查失败不阻断 */ }
      }
      const sid = await ensureSession().catch(() => undefined)
      // 落款部门：培训通知中修改过则用修改后的，否则公司级固定人事行政部、总经办归人事行政部
      const archiveDept =
        session.issuer_department ||
        (session.department === '总经办' ? '人事行政部' : session.department || '人事行政部')
      const trainerFull = session.instructor ? `${archiveDept}/${session.instructor}` : archiveDept

      // ── 公司级培训：主台账归落款部门，涉及部门=全部受训部门，培训对象=全部人员放一起 ──
      // ── 部门级培训：同公司级，构造单条主记录（培训对象=全部人员，内容全量一致），
      //     涉及部门=真实参训部门（人员→部门映射，支持跨部门参训），由后端按涉及部门拆内容一致的副本；
      //     主记录归属按参训人员判定：有 MC 人员归 MC、有 DR 人员归 DR（无对应人员不建记录） ──
      const deptMap = session.employee_dept_map || {}
      const groups: { teaching_dept: string; ledger_department: string; involved: string; names: string[] }[] = []

      if (level === '公司级' || !archiveDept) {
        // 公司级培训：只构造一条主记录（后端 create_record 按 involved_depts 为每个受训部门自动创建内容一致的副本）
        const traineeDepts = (session.trainee_departments || []).filter(Boolean)
        if (traineeDepts.length) {
          groups.push({
            teaching_dept: archiveDept,
            ledger_department: archiveDept,
            involved: traineeDepts.join('、'),
            names: sessionNames, // 全部受训人员，不按部门拆分
          })
        }
      } else {
        // 部门级培训：单条主记录，涉及部门=真实参训部门（人员映射中的部门，含跨部门参训）
        const realDepts = new Set<string>()
        ;(Object.values(deptMap || {}) as string[]).forEach((d) => d && realDepts.add(d))
        if (!realDepts.size) {
          // 无人员映射时回退受训部门（主办部门）
          ;(session.trainee_departments || []).filter(Boolean).forEach((d) => realDepts.add(d))
        }
        // 主记录归属：有 MC 人员→201二车间（MC），有 DR 人员→201二车间（DR），否则用落款部门
        const hasMc = sessionNames.some((n) => deptMap[n] === DEPT_201_MC)
        const hasDr = sessionNames.some((n) => deptMap[n] === DEPT_201_DR)
        const primaryDept = hasMc ? DEPT_201_MC : hasDr ? DEPT_201_DR : archiveDept
        groups.push({
          teaching_dept: archiveDept,
          ledger_department: primaryDept,
          involved: [...realDepts].join('、'),
          names: sessionNames, // 全部受训人员，不按部门拆分
        })
      }

      // 无分组时退化为单条（涉及部门保留受训部门）
      const records = groups.length ? groups : [{ teaching_dept: archiveDept, ledger_department: archiveDept, involved: (session.trainee_departments || []).join('、'), names: sessionNames }]

      // 整场培训涉及部门去重（含 201 二车间 MC/DR 各组）→ 多部门培训标 pending 待二级确认
      const allDeptSet = new Set<string>()
      for (const g of records) {
        g.involved.split('、').filter(Boolean).forEach((d) => allDeptSet.add(d))
      }
      const isMultiDept = allDeptSet.size >= 2

      // 台账培训内容写全：优先培训附件 Tab 完整清单（含手动添加的行），回退勾选文件，再回退培训题目
      const attachmentPayloadForLedger = docBuildersRef.current['attachment']?.() as
        | { items?: { name: string; code?: string | null }[] }
        | null
        | undefined
      const attachmentFullText = attachmentPayloadForLedger?.items?.length
        ? attachmentPayloadForLedger.items
            .map((e) => (e.code ? `《${e.name}》（${e.code}）` : `《${e.name}》`))
            .join('、')
        : ''
      const fullContent = attachmentFullText || contentFormatted || session.topic

      const basePayload = {
        training_date: session.training_date!,
        training_subject: session.topic!,
        training_method: session.training_method || '',
        duration_hours: computeDurationHours(),
        trainer: trainerFull,
        source_type: 'notification' as const,
        session_id: sid,
        // 台账"培训时间（日期+时间）"列格式：2026.01.06 09:00~10:00
        training_datetime: [session.training_date?.replace(/-/g, '.'), timeStart && timeEnd ? `${timeStart}~${timeEnd}` : ''].filter(Boolean).join(' '),
        training_content: fullContent,
        instructor: session.instructor,
        // 一级/二级：公司级培训或涉及部门≥3个 → 一级；否则（1~2个部门内部培训）→ 二级
        level_category:
          level === '公司级' || (session.trainee_departments || []).filter(Boolean).length >= 3
            ? '一级'
            : '二级',
        ledger_assessment_method: session.assessment_method,
        plan_source: level === '公司级' ? '公司计划' : '部门计划',
        // 培训类别：按桌面《培训类别.xlsx》关键词自动识别，未命中留空
        training_type: matchTrainingType(session.topic || '', fullContent || ''),
        // 人药/兽药：按培训内容关键词自动识别，未命中留空
        drug_category: matchDrugCategory(session.topic || '', fullContent || ''),
        // 考核方式为口试时，台账"考核成绩"直接记为合格、"成绩汇总"记为 /
        assessment_result: session.assessment_method === '口试' ? '合格' : undefined,
        score_summary: session.assessment_method === '口试' ? '/' : undefined,
        is_presented: ledgerPresented,
      }
      for (const g of records) {
        await createTrainingLedger({
          ...basePayload,
          ledger_department: g.ledger_department,
          second_level_status: isMultiDept ? 'pending' : undefined,
          teaching_dept: g.teaching_dept,
          involved_depts: g.involved,
          trainees: g.names.join('、') || g.involved,
        })
      }
      // 入台账同时自动保存全部资料，台账"资料"抽屉即可回看
      const savedCount = await saveAllDocs().catch(() => 0)
      message.success(savedCount ? `已添加到培训台账，并自动保存 ${savedCount} 类培训资料` : '已添加到培训台账')
      // 台账"做二级培训"入口闭环：二级会话入台账后，自动把源台账副本置为已完成二级
      if (parentRecordIdRef.current) {
        try {
          await updateTrainingLedger(parentRecordIdRef.current, { second_level_status: 'done' })
          parentRecordIdRef.current = undefined
        } catch {
          /* 闭环失败不阻断入台账，用户可在台账页手动确认 */
        }
      }
      // 同步自动保存指纹，避免紧接着被轮询重复写一次
      sessionRef.current = session
      const fpAfterLedger = computeContentFingerprint()
      if (fpAfterLedger !== null) lastSavedSnapshotRef.current = fpAfterLedger
      setAutoSaveFailed(false)
      setLastAutoSaveAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
      // 勾选的附件文件条目写入"已培训" → 下次置灰不可再选
      if (checkedEntries.length) {
        try {
          await markTrainingContentUsed(
            checkedEntries.map((e) => ({ name: e.name, code: e.resolvedCode, attachment_id: e.attachment_id || null })),
          )
          setUsedNames((prev) => new Set([...prev, ...checkedEntries.map((e) => e.name)]))
          setCheckedEntries([])
          const curItem = planItems.find((i) => i.id === selectedItemId)
          const base = curItem?.content_textbook || curItem?.content_and_textbook || ''
          if (base) setSession((prev) => ({ ...prev, topic: base }))
        } catch (err) {
          message.error((err instanceof Error ? err.message : '') || '标记文件条目已培训失败')
        }
      }
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '添加到培训台账失败')
    } finally {
      setAddingLedger(false)
      setLedgerConfirmOpen(false)
    }
  }





  const notifyInitialValues: Record<string, unknown> = {}
  if (session.department) notifyInitialValues.department = session.department
  if (session.training_date) notifyInitialValues.training_date = session.training_date
  if (session.topic) {
    notifyInitialValues.subject = session.topic
    notifyInitialValues.content = session.content || ''
  }
  if (session.training_method) notifyInitialValues.training_method = session.training_method
  if (session.instructor) notifyInitialValues.trainer = session.instructor
  if (session.location) notifyInitialValues.location = session.location
  if (session.training_time_start) {
    notifyInitialValues._training_time_start = session.training_time_start
    notifyInitialValues._training_time_end = session.training_time_end
  }
  if (session.trainee_departments) notifyInitialValues.trainee_departments = session.trainee_departments
  if (sessionNames.length) notifyInitialValues.employee_names = sessionNames

  // 切换级别/部门时让子表单重新挂载并按新范围预填
  const scopeKey = `${level}-${scopeDept || 'all'}`

  const tabItems = [
    {
      key: 'sign-in',
      label: (<span className="flex items-center gap-2"><FormOutlined />培训签到表</span>),
      children: (
        <SignInSheetClient key={`si-${scopeKey}-${resetKey}`} sessionData={session} onSessionChange={handleSessionChange} registerExporter={registerExporter} sessionId={sessionId} />
      ),
    },
    {
      key: 'evaluation',
      // forceRender：未访问的 Tab 也挂载，保证顶部"保存"/"一键导出"能覆盖全部五类
      forceRender: true,
      label: (<span className="flex items-center gap-2"><CheckSquareOutlined />培训评估表</span>),
      children: (<TrainingEvaluationListClient key={`ev-${scopeKey}`} sessionData={session} onSessionChange={handleSessionChange} registerDocBuilder={registerDocBuilder} registerExporter={registerExporter} initialDraft={evalDraft} />),
    },
    {
      key: 'notification',
      forceRender: true,
      label: (<span className="flex items-center gap-2"><BellOutlined />培训通知</span>),
      children: (
        <TrainingNotificationClient key={`nt-${scopeKey}`} sessionData={session} onSessionChange={handleSessionChange} notifyInitialValues={notifyInitialValues} registerDocBuilder={registerDocBuilder} registerExporter={registerExporter} draft={notifyDraft} />
      ),
    },
    {
      key: 'oral_exam',
      forceRender: true,
      label: (<span className="flex items-center gap-2"><AuditOutlined />口试评估表</span>),
      children: (
        <OralExamSheetClient
          key={`oe-${scopeKey}-${resetKey}`}
          sessionData={session}
          initialPayload={oralPayload}
          onSessionIdChange={assignSessionId}
          active={session.assessment_method === '口试'}
          assessmentMethod={session.assessment_method}
          registerDocBuilder={registerDocBuilder}
          registerExporter={registerExporter}
        />
      ),
    },
    {
      key: 'practical_exam',
      forceRender: true,
      label: (<span className="flex items-center gap-2"><ToolOutlined />实操评估表</span>),
      children: (
        <PracticalExamSheetClient
          key={`pe-${scopeKey}`}
          sessionData={session}
          initialPayload={practicalPayload}
          onSessionIdChange={assignSessionId}
          active={session.assessment_method === '实操'}
          assessmentMethod={session.assessment_method}
          registerDocBuilder={registerDocBuilder}
          registerExporter={registerExporter}
        />
      ),
    },
    {
      key: 'ai_written_exam',
      forceRender: true,
      label: (<span className="flex items-center gap-2"><RobotOutlined />AI 笔试</span>),
      children: (
        <AiWrittenExamClient
          key={`awe-${scopeKey}-${resetKey}`}
          sessionData={session}
          initialPayload={aiWrittenPayload}
          active={session.assessment_method === '笔试'}
          assessmentMethod={session.assessment_method}
          registerDocBuilder={registerDocBuilder}
          registerExporter={registerExporter}
        />
      ),
    },
    {
      key: 'attachment',
      forceRender: true,
      label: (<span className="flex items-center gap-2"><PaperClipOutlined />培训附件</span>),
      children: (
        <TrainingAttachmentClient
          key={`at-${scopeKey}-${resetKey}`}
          sessionData={session}
          checkedContent={session.checked_content}
          initialPayload={attachmentPayload}
          registerDocBuilder={registerDocBuilder}
          registerExporter={registerExporter}
        />
      ),
    },
  ]

  return (
    <div className="space-y-4">
      {/* 顶部：培训范围控制 */}
      <Card size="small" title="培训范围（公司级 / 部门级）">
        <Space wrap size={16} align="center">
          <Segmented
            value={level}
            onChange={(v) => handleLevelChange(v as '公司级' | '部门级')}
            options={[{ value: '公司级', label: '公司级培训' }, { value: '部门级', label: '部门级培训' }]}
          />
          <Space size={6}>
            <span className="text-sm text-gray-600">计划年度</span>
            <Select value={year} onChange={handleYearChange} options={YEAR_OPTIONS} style={{ width: 100 }} />
          </Space>
          {level === '部门级' && (
            <Space size={6}>
              <span className="text-sm text-gray-600">部门</span>
              <AutoComplete
                value={scopeDept}
                onChange={handleDeptChange}
                placeholder="选择或输入部门"
                options={departments.map((d) => ({ value: d.value }))}
                filterOption={(input, option) =>
                  (option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                }
                style={{ width: 180 }}
                allowClear
              />
            </Space>
          )}
          <Space size={6}>
            <span className="text-sm text-gray-600">关联年度计划</span>
            <Select
              value={selectedPlanId}
              onChange={handlePlanChange}
              placeholder={plans.length ? '选择计划' : '无匹配计划'}
              options={plans.map((p) => ({ value: p.id, label: `${p.department}（${p.year}）` }))}
              style={{ width: 200 }}
              allowClear
            />
          </Space>
          {selectedPlanId && (
            <Space size={6}>
              <span className="text-sm text-gray-600">计划项目</span>
              <Select
                value={selectedItemId}
                onChange={handleItemChange}
                placeholder="选择项目（自动带出内容）"
                options={planItems.map((i) => {
                  const month = i.training_month || i.month || ''
                  const content = i.content_textbook || i.content_and_textbook || `项目${i.sort_order + 1}`
                  const monthLabel = month.endsWith('月') ? month : (month ? `${month}月` : '')
                  return {
                    value: i.id,
                    label: monthLabel ? `${monthLabel} ${content}` : content,
                  }
                })}
                style={{ width: 260 }}
                allowClear
              />
            </Space>
          )}
        </Space>
        <div className="mt-2">
          <Space size={8} wrap align="center">
            {selectedItemId && planSections.length > 0 && (
              <Button size="small" onClick={() => setContentModalOpen(true)}>
                选择培训附件内容
              </Button>
            )}
            <Button size="small" onClick={() => setDocPickerOpen(true)}>
              从文件管理选择
            </Button>
            {contentFormatted && (
              <span className="text-xs text-gray-600">已录入：{contentFormatted}</span>
            )}
          </Space>
        </div>
        <div className="mt-3">
          <Space wrap size={12}>
            <Button icon={<SettingOutlined />} onClick={() => setConfigOpen(true)}>
              配置培训人员
            </Button>
            <Button
              icon={<UserAddOutlined />}
              onClick={handleFetchNewHires}
              loading={fetchingNewHires}
              disabled={level !== '公司级'}
              title="从员工档案中拉取入职一周内的新员工"
            >
              拉取新员工(入职一周)
            </Button>
            <Select
              mode="multiple"
              value={selectedConfigIds}
              onChange={handleSelectConfigs}
              placeholder={loadingConfigs ? '加载中...' : '加载班组人员（可多选）'}
              loading={loadingConfigs}
              options={personnelConfigs.map((c) => ({
                value: c.id,
                label: `${c.config_name}（${(c.personnel || []).length}人）`,
              }))}
              optionRender={(option) => (
                <div className="flex items-center gap-2">
                  <Checkbox
                    checked={selectedConfigIds.includes(String(option.value))}
                    style={{ pointerEvents: 'none' }}
                  />
                  <span>{option.label}</span>
                </div>
              )}
              maxTagCount={2}
              style={{ minWidth: 240 }}
              allowClear
              onClear={() => handleSelectConfigs([])}
            />
          </Space>
        </div>
        <div className="mt-3 blue-action-buttons doc-toolbar">
          <Space wrap size={12}>
            <Button
              type="primary"
              icon={<FolderOpenOutlined />}
              onClick={handleExportAll}
              loading={exportingAll}
              title="把签到/评估/通知/口试/实操/笔试/培训附件已编辑的资料打包成 zip 一次下载"
            >
              一键导出
            </Button>
            <Button type="primary" icon={<BookOutlined />} onClick={handleAddToLedger} loading={addingLedger}>
              添加到培训台账
            </Button>
            <Button type="primary" icon={<SaveOutlined />} loading={savingAll} title="一键保存签到/评估/通知/口试/实操/笔试/培训附件七类资料草稿" onClick={handleSaveAllDocsManual}>
                保存
              </Button>
            {autoSaveFailed ? (
              <span className="text-xs text-red-600">
                自动保存失败，将在下个周期自动重试；也可点击「保存」手动重试
              </span>
            ) : lastAutoSaveAt ? (
              <span className="text-xs text-green-600">
                已自动保存 {lastAutoSaveAt}
              </span>
            ) : null}
            <Button icon={<FileAddOutlined />} onClick={handleNewTraining} title="清空并开始新建一份培训资料">
              新建培训资料
            </Button>
          </Space>
        </div>
        <div className="mt-2 text-xs text-gray-500">
          {level === '公司级'
            ? '公司级培训：面向全公司（含公司级年度计划、新员工培训等），受训部门可多选。'
            : '部门级培训：面向所选部门（对应该部门年度计划及部门内部培训），受训部门自动锁定为该部门。'}
        </div>
      </Card>

      {/* 不使用 destroyOnHidden：切换 Tab 时保留各表已编辑内容（临时保存） */}
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} size="large" />

      <TrainingPersonnelConfigModal
        open={configOpen}
        level={level}
        scopeDept={scopeDept}
        onClose={() => setConfigOpen(false)}
        onApplied={applyPersonnel}
      />

      <AttachmentContentModal
        open={contentModalOpen}
        sections={modalSections}
        usedNames={usedNames}
        initialCheckedKeys={checkedEntries.map((e) => e.key)}
        onClose={() => setContentModalOpen(false)}
        onConfirm={handleContentConfirm}
      />

      {/* 添加到培训台账确认弹窗（受控：Switch 可正常切换） */}
      <Modal
        open={ledgerConfirmOpen}
        title="确认添加到培训台账"
        onCancel={() => setLedgerConfirmOpen(false)}
        onOk={doAddToLedger}
        confirmLoading={addingLedger}
        okText="确定"
        cancelText="取消"
      >
        <div>是否将本次培训信息（{session.topic}）录入培训台账？</div>
        <div style={{ marginTop: 12 }}>
          是否呈现（不呈现则不进入员工培训清单）：
          <Switch
            checked={ledgerPresented}
            onChange={setLedgerPresented}
            checkedChildren="是"
            unCheckedChildren="否"
            style={{ marginLeft: 8 }}
          />
        </div>
      </Modal>

      {/* 从质量管理-文件管理选择培训内容 */}
      <DocumentCatalogPickerModal
        open={docPickerOpen}
        onClose={() => setDocPickerOpen(false)}
        onConfirm={handleDocPickerConfirm}
        excludeNames={[
          ...checkedEntries.map((e) => e.name),
          ...Array.from(usedNames),
        ]}
      />

      <style jsx global>{`
        /* 签到页操作按钮统一蓝色（覆盖全局紫色主按钮） */
        .blue-action-buttons .ant-btn-primary { background: #1677ff; border-color: #1677ff; }
        .blue-action-buttons .ant-btn-primary:hover,
        .blue-action-buttons .ant-btn-primary:focus { background: #4096ff; border-color: #4096ff; }
        .blue-action-buttons .ant-btn-primary:active { background: #0958d9; border-color: #0958d9; }
      `}</style>
    </div>
  )
}
