'use client'

import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { useRouter } from 'next/navigation'
import {
  Table,
  Button,
  Space,
  Input,
  Select,
  Modal,
  Form,
  Upload,
  Drawer,
  message,
  Card,
  Typography,
  Tabs,
  Divider,
  Spin,
  Switch,
  Tooltip,
  App,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { UploadProps } from 'antd'
import {
  PlusOutlined,
  SearchOutlined,
  EditOutlined,
  DeleteOutlined,
  UploadOutlined,
  FileTextOutlined,
  RobotOutlined,
  AimOutlined,
  EyeOutlined,
  ThunderboltOutlined,
  FileProtectOutlined,
  HistoryOutlined,
  CloudUploadOutlined,
  SafetyCertificateOutlined,
  SafetyOutlined,
  DownloadOutlined,
} from '@ant-design/icons'
import { useSafetyStore } from '@/stores/safety'
import {
  getRegulations,
  createRegulation,
  updateRegulation,
  deleteRegulation,
  uploadRegulationDocument,
  getRevisions,
  createRevision,
  deleteRevision,
  manualRevisionComplete,
  aiRevisionGenerate,
  aiRevisionConfirm,
  identifyRevisionScope,
  batchUploadRegulations,
  runComplianceReview,
  getRegulationReviews,
  getLatestRegulationReviews,
  getRegulationDocumentPreview,
  downloadRegulationDocument,
} from '@/actions/safety'
import type {
  OperationRegulation,
  OperationRegulationFormData,
  RegulationRevision,
  RegulationRevisionFormData,
  RegulationBatchUploadResponse,
  RegulationDocumentPreview,
  RegulationLatestReviewEntry,
  RegulationReview,
  RegulationReviewItem,
} from '@/types/safety'
import SopGeneratorModal from '@/components/safety/SopGeneratorModal'
import ReactMarkdown from 'react-markdown'
import {
  RevisionType,
  REVISION_TYPE_OPTIONS,
  REVISION_SCOPE_OPTIONS,
  REVIEW_OPINION_OPTIONS,
} from '@/types/safety'
import {
  actionLink,
  statusPill,
  pillSuccess,
  pillWarning,
  pillError,
  pillNeutral,
  pillInfo,
  pillPurple,
  pillDefault,
  T,
} from '@/components/safety/shared-styles'
import dayjs from 'dayjs'

const { Text } = Typography

// ── 操作链接预设 ──
const $link = actionLink('#0075de')
const $danger = actionLink('#e03131')
const $purple = actionLink('#5645d4')
const $muted = actionLink('#787671')

// ── 车间/部门预设（与各车间安全资料目录对应） ──
const WORKSHOP_OPTIONS = [
  '101一车间', '101二车间', '101-102车间', '102一车间', '102二车间',
  '103车间', '201一车间', '201二车间', '201三车间', '202车间', '203车间',
  '动力部', '热动站', '污水处理车间', '质量部', '仓储', '公司级',
].map((name) => ({ value: name, label: name }))

// 合规审核结论展示配置
const REVIEW_RESULT_META: Record<string, { label: string; color: string; bg: string }> = {
  pass: { label: '合规', color: '#52c41a', bg: '#d9f3e1' },
  conditional_pass: { label: '基本合规', color: '#d46b08', bg: '#ffe8d4' },
  fail: { label: '不合规', color: '#e03131', bg: '#fde0e0' },
}

const SEVERITY_COLOR: Record<string, CSSProperties> = {
  严重: pillError,
  一般: pillWarning,
  建议: pillInfo,
}

// 合规审核问题项表格列（缺失项 / 不合规项共用）
const reviewItemColumns: ColumnsType<RegulationReviewItem> = [
  {
    title: '问题项',
    dataIndex: 'item',
    width: 140,
    render: (item: string, record: RegulationReviewItem) => (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <span style={SEVERITY_COLOR[record.severity] || pillNeutral}>
          {record.severity || '建议'}
        </span>
        <span style={{ fontWeight: 500 }}>{item}</span>
      </span>
    ),
  },
  {
    title: '要求',
    dataIndex: 'requirement',
    ellipsis: true,
  },
  {
    title: '依据',
    dataIndex: 'basis',
    width: 170,
    ellipsis: true,
    render: (basis: string) => (
      <span style={{ color: T.slate, fontSize: 12 }}>{basis}</span>
    ),
  },
  {
    title: '整改建议',
    dataIndex: 'suggestion',
    width: 200,
    ellipsis: true,
  },
]

export default function RegulationPage() {
  const [activeTab, setActiveTab] = useState('regulations')
  const { modal } = App.useApp()

  // ========== Regulation States ==========
  const [regForm] = Form.useForm()
  const [regEditForm] = Form.useForm()
  const [regLoading, setRegLoading] = useState(false)
  const [regDrawerOpen, setRegDrawerOpen] = useState(false)
  const [editingRegulation, setEditingRegulation] = useState<OperationRegulation | null>(null)
  const [regSearchText, setRegSearchText] = useState('')
  const [positionFilter, setPositionFilter] = useState<string | undefined>()
  const [workshopFilter, setWorkshopFilter] = useState<string | undefined>()
  const [statusFilter, setStatusFilter] = useState<string | undefined>('reviewed,exported,draft')
  const [regSubmitting, setRegSubmitting] = useState(false)

  // ========== Batch Upload States ==========
  const [batchOpen, setBatchOpen] = useState(false)
  const [batchFiles, setBatchFiles] = useState<Array<{ file: File; uid: string }>>([])
  const [batchHintWorkshop, setBatchHintWorkshop] = useState<string | undefined>()
  const [batchUseAi, setBatchUseAi] = useState(true)
  const [batchUploading, setBatchUploading] = useState(false)
  const [batchResult, setBatchResult] = useState<RegulationBatchUploadResponse | null>(null)

  // ========== Compliance Review States ==========
  const [latestReviews, setLatestReviews] = useState<Record<string, RegulationLatestReviewEntry>>({})
  const [reviewTarget, setReviewTarget] = useState<OperationRegulation | null>(null)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [reviewRunning, setReviewRunning] = useState(false)
  const [reviewReport, setReviewReport] = useState<RegulationReview | null>(null)
  const [reviewHistory, setReviewHistory] = useState<RegulationReview[]>([])
  const [reviewHistoryLoading, setReviewHistoryLoading] = useState(false)

  // ========== Document Preview States ==========
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewTarget, setPreviewTarget] = useState<OperationRegulation | null>(null)
  const [previewData, setPreviewData] = useState<RegulationDocumentPreview | null>(null)
  const [previewDownloading, setPreviewDownloading] = useState(false)

  // ========== Revision States ==========
  const [revForm] = Form.useForm()
  const [revLoading, setRevLoading] = useState(false)
  const [revDrawerOpen, setRevDrawerOpen] = useState(false)
  const [revSearchText, setRevSearchText] = useState('')
  const [typeFilter, setTypeFilter] = useState<string | undefined>()
  const [scopeFilter, setScopeFilter] = useState<string | undefined>()
  const [opinionFilter, setOpinionFilter] = useState<string | undefined>()
  const [revSubmitting, setRevSubmitting] = useState(false)

  // AI revision states
  const [aiModalVisible, setAiModalVisible] = useState(false)
  const [aiGenerating, setAiGenerating] = useState(false)
  const [aiContent, setAiContent] = useState('')
  const [aiDocumentName, setAiDocumentName] = useState('')
  const [aiRevisionId, setAiRevisionId] = useState<string | null>(null)
  const [aiConfirming, setAiConfirming] = useState(false)
  const [scopeLoading, setScopeLoading] = useState<string | null>(null)

  const router = useRouter()

  // SOP Generator states
  const [generatorModalOpen, setGeneratorModalOpen] = useState(false)

  // Regulations cache for revision create form
  const [regulationsForSelect, setRegulationsForSelect] = useState<OperationRegulation[]>([])

  // ========== Store ==========
  const {
    regulations,
    regulationTotal,
    regulationQueryParams,
    setRegulations,
    setRegulationTotal,
    setRegulationQueryParams,
    addRegulation,
    updateRegulation: updateRegulationInStore,
    removeRegulation,

    revisions,
    revisionTotal,
    revisionQueryParams,
    setRevisions,
    setRevisionTotal,
    setRevisionQueryParams,
    addRevision,
    updateRevision: updateRevisionInStore,
    removeRevision,
  } = useSafetyStore()

  // ========== Regulation Handlers ==========

  const loadRegulations = async () => {
    setRegLoading(true)
    try {
      const response = await getRegulations({
        ...regulationQueryParams,
        keyword: regSearchText || undefined,
        position: positionFilter,
        workshop: workshopFilter,
        status: statusFilter,
      })
      if (response.code === 200) {
        setRegulations(response.data)
        setRegulationTotal(response.meta?.total || 0)
        void loadLatestReviews(response.data)
      }
    } catch {
      message.error('加载操规列表失败')
    } finally {
      setRegLoading(false)
    }
  }

  const loadLatestReviews = async (items: OperationRegulation[]) => {
    if (!items.length) {
      setLatestReviews({})
      return
    }
    try {
      const response = await getLatestRegulationReviews(items.map((item) => item.id))
      if (response.code === 200 && response.data) {
        const next: Record<string, RegulationLatestReviewEntry> = {}
        response.data.forEach((entry) => {
          next[entry.regulation_id] = entry
        })
        setLatestReviews(next)
      }
    } catch {
      // 审核状态列加载失败不影响台账主列表
    }
  }

  const loadRevisions = async () => {
    setRevLoading(true)
    try {
      const response = await getRevisions({
        ...revisionQueryParams,
        revision_type: typeFilter,
        revision_scope: scopeFilter,
        review_opinion: opinionFilter,
      })
      if (response.code === 200) {
        setRevisions(response.data)
        setRevisionTotal(response.meta?.total || 0)
      }
    } catch {
      message.error('加载修订记录失败')
    } finally {
      setRevLoading(false)
    }
  }

  const loadRegulationsForSelect = async () => {
    try {
      const response = await getRegulations({ page: 1, page_size: 500 })
      if (response.code === 200) {
        setRegulationsForSelect(response.data)
      }
    } catch {
      // silent
    }
  }

  useEffect(() => {
    if (activeTab === 'regulations') loadRegulations()
  }, [regulationQueryParams.page, regulationQueryParams.page_size, positionFilter, workshopFilter, statusFilter, activeTab])

  useEffect(() => {
    if (activeTab === 'revisions') loadRevisions()
  }, [revisionQueryParams.page, revisionQueryParams.page_size, typeFilter, scopeFilter, opinionFilter, activeTab])

  useEffect(() => {
    loadRegulationsForSelect()
  }, [])

  // ---- Regulation CRUD ----

  const handleAddRegulation = () => {
    setEditingRegulation(null)
    regForm.resetFields()
    setRegDrawerOpen(true)
  }

  const handleEditRegulation = (record: OperationRegulation) => {
    setEditingRegulation(record)
    regEditForm.setFieldsValue(record)
    setRegDrawerOpen(true)
  }

  const handleDeleteRegulation = (id: string) => {
    modal.confirm({
      title: '确认删除',
      content: '确定要删除这个操规文档吗？此操作不可撤销。',
      okText: '确认删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const response = await deleteRegulation(id)
          if (response.code === 200) {
            message.success('删除成功')
            removeRegulation(id)
          } else {
            message.error(response.message || '删除失败')
          }
        } catch {
          message.error('删除失败')
        }
      },
    })
  }

  // ── SOP Generator Handlers ──

  const handleOpenGenerator = () => {
    setGeneratorModalOpen(true)
  }

  const handleSopGenerated = (result: {
    regulation_id: string
    meta: Record<string, string>
    content: string
  }) => {
    setGeneratorModalOpen(false)
    loadRegulations()
    router.push(`/safety/regulation/generator/${result.regulation_id}`)
  }

  const handleOpenEditor = (record: OperationRegulation) => {
    if (!record.content) {
      message.warning('该操规尚未生成标准化内容，请先上传旧版操规进行生成')
      return
    }
    router.push(`/safety/regulation/generator/${record.id}`)
  }

  // ── Batch Upload Handlers ──

  const handleOpenBatchUpload = () => {
    setBatchFiles([])
    setBatchResult(null)
    setBatchOpen(true)
  }

  const handleBatchUpload = async () => {
    if (!batchFiles.length) {
      message.warning('请先选择要导入的操规文件')
      return
    }
    setBatchUploading(true)
    setBatchResult(null)
    try {
      const response = await batchUploadRegulations(
        batchFiles.map((entry) => entry.file),
        {
          hintWorkshop: batchHintWorkshop || undefined,
          useAi: batchUseAi,
        }
      )
      if (response.code === 200 && response.data) {
        setBatchResult(response.data)
        message.success(
          `导入完成：成功 ${response.data.success_count} 个，跳过/失败 ${response.data.fail_count} 个`
        )
        loadRegulations()
      } else {
        message.error(response.message || '批量导入失败')
      }
    } catch {
      message.error('批量导入失败')
    } finally {
      setBatchUploading(false)
    }
  }

  // ── Compliance Review Handlers ──

  const openReviewModal = (record: OperationRegulation) => {
    setReviewTarget(record)
    setReviewReport(null)
    setReviewHistory([])
    setReviewOpen(true)
  }

  const handleRunReview = async () => {
    if (!reviewTarget) return
    setReviewRunning(true)
    setReviewReport(null)
    try {
      const response = await runComplianceReview(reviewTarget.id)
      if (response.code === 200 && response.data) {
        setReviewReport(response.data)
        message.success('合规审核完成，结论供人工确认')
        void loadLatestReviews(regulations)
      } else {
        message.error(response.message || 'AI 审核失败')
      }
    } catch {
      message.error('AI 审核失败')
    } finally {
      setReviewRunning(false)
    }
  }

  const handleLoadReviewHistory = async () => {
    if (!reviewTarget) return
    setReviewHistoryLoading(true)
    try {
      const response = await getRegulationReviews(reviewTarget.id)
      if (response.code === 200 && response.data) {
        setReviewHistory(response.data.items)
      }
    } catch {
      // 历史加载失败保持空列表
    } finally {
      setReviewHistoryLoading(false)
    }
  }

  // ── Document Preview Handlers ──

  const handleOpenPreview = async (record: OperationRegulation) => {
    setPreviewTarget(record)
    setPreviewData(null)
    setPreviewOpen(true)
    setPreviewLoading(true)
    try {
      const response = await getRegulationDocumentPreview(record.id)
      if (response.code === 200 && response.data) {
        setPreviewData(response.data)
      } else {
        message.error(response.message || '文档内容加载失败')
        setPreviewOpen(false)
      }
    } catch {
      message.error('文档内容加载失败')
      setPreviewOpen(false)
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleDownloadDocument = async () => {
    if (!previewTarget) return
    setPreviewDownloading(true)
    try {
      await downloadRegulationDocument(
        previewTarget.id,
        previewData?.file_name || previewTarget.document_original_name
      )
    } catch (err) {
      message.error(err instanceof Error ? err.message : '下载失败')
    } finally {
      setPreviewDownloading(false)
    }
  }

  const handleRegSubmit = async () => {
    try {
      const values = editingRegulation
        ? await regEditForm.validateFields()
        : await regForm.validateFields()
      // 编号可选：空串按未填写处理
      if (!values.regulation_no) delete values.regulation_no
      setRegSubmitting(true)

      if (editingRegulation) {
        const response = await updateRegulation(editingRegulation.id, values)
        if (response.code === 200) {
          message.success('更新成功')
          updateRegulationInStore(editingRegulation.id, response.data)
          setRegDrawerOpen(false)
        } else {
          message.error(response.message || '更新失败')
        }
      } else {
        const response = await createRegulation(values as OperationRegulationFormData)
        if (response.code === 200) {
          message.success('创建成功')
          addRegulation(response.data)
          setRegDrawerOpen(false)
          regForm.resetFields()
        } else {
          message.error(response.message || '创建失败')
        }
      }
    } catch {
      // form validation error
    } finally {
      setRegSubmitting(false)
    }
  }

  const handleUploadDoc = async (id: string, file: File) => {
    try {
      const response = await uploadRegulationDocument(id, file)
      if (response.code === 200) {
        message.success('文档上传成功')
        loadRegulations()
      } else {
        message.error(response.message || '上传失败')
      }
    } catch {
      message.error('上传失败')
    }
  }

  const regulationUploadProps = (id: string): UploadProps => ({
    showUploadList: false,
    beforeUpload: async (file) => {
      await handleUploadDoc(id, file)
      return false
    },
  })

  // ---- Revision Handlers ----

  const handleAddRevision = () => {
    revForm.resetFields()
    setRevDrawerOpen(true)
  }

  const handleRevSubmit = async () => {
    try {
      const values = await revForm.validateFields()
      setRevSubmitting(true)
      const response = await createRevision(values as RegulationRevisionFormData)
      if (response.code === 200) {
        message.success('创建修订记录成功')
        addRevision(response.data)
        setRevDrawerOpen(false)
        revForm.resetFields()
      } else {
        message.error(response.message || '创建失败')
      }
    } catch {
      // form validation error
    } finally {
      setRevSubmitting(false)
    }
  }

  const handleDeleteRevision = (id: string) => {
    modal.confirm({
      title: '确认删除',
      content: '确定要删除这个修订记录吗？此操作不可撤销。',
      okText: '确认删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const response = await deleteRevision(id)
          if (response.code === 200) {
            message.success('删除成功')
            removeRevision(id)
          } else {
            message.error(response.message || '删除失败')
          }
        } catch {
          message.error('删除失败')
        }
      },
    })
  }

  // Manual revision upload
  const handleManualUpload = async (revisionId: string, file: File) => {
    try {
      const response = await manualRevisionComplete(revisionId, file)
      if (response.code === 200) {
        message.success('人工修订完成，已自动审核通过')
        loadRevisions()
        loadRegulations()
      } else {
        message.error(response.message || '修订失败')
      }
    } catch {
      message.error('修订失败')
    }
  }

  const manualUploadProps = (revisionId: string): UploadProps => ({
    showUploadList: false,
    beforeUpload: async (file) => {
      await handleManualUpload(revisionId, file)
      return false
    },
  })

  // AI revision generate
  const handleAIGenerate = async (revisionId: string) => {
    setAiRevisionId(revisionId)
    setAiModalVisible(true)
    setAiGenerating(true)
    setAiContent('')
    setAiDocumentName(`修订稿_${dayjs().format('YYYYMMDDHHmmss')}.docx`)
    try {
      const response = await aiRevisionGenerate(revisionId)
      if (response.code === 200) {
        setAiContent(response.data.generated_content)
      } else {
        message.error(response.message || 'AI生成失败')
        setAiModalVisible(false)
      }
    } catch {
      message.error('AI生成失败')
      setAiModalVisible(false)
    } finally {
      setAiGenerating(false)
    }
  }

  const handleAIConfirm = async () => {
    if (!aiRevisionId || !aiContent) return
    setAiConfirming(true)
    try {
      const response = await aiRevisionConfirm(aiRevisionId, aiContent, aiDocumentName || undefined)
      if (response.code === 200) {
        message.success('AI修订确认成功')
        setAiModalVisible(false)
        setAiContent('')
        setAiRevisionId(null)
        loadRevisions()
        loadRegulations()
      } else {
        message.error(response.message || '确认失败')
      }
    } catch {
      message.error('确认失败')
    } finally {
      setAiConfirming(false)
    }
  }

  // Scope identification
  const handleIdentifyScope = async (revisionId: string) => {
    setScopeLoading(revisionId)
    try {
      const response = await identifyRevisionScope(revisionId)
      if (response.code === 200) {
        message.success('修订范围识别完成')
        loadRevisions()
      } else {
        message.error(response.message || '识别失败')
      }
    } catch {
      message.error('识别失败')
    } finally {
      setScopeLoading(null)
    }
  }

  // ── Status rendering helpers ──

  const renderStandardizationStatus = (status: string | undefined, content: string | undefined) => {
    if (!content) return <span style={pillDefault}>未生成</span>
    if (status === 'reviewed') return <span style={pillPurple}>已审核</span>
    if (status === 'generated') return <span style={pillInfo}>已生成</span>
    if (status === 'exported') return <span style={pillSuccess}>已导出</span>
    return <span style={statusPill('#0891b2', '#cffafe')}>草稿</span>
    }

  // ========== Table Columns ==========

  const regulationColumns: ColumnsType<OperationRegulation> = [
    {
      title: '操规名称',
      dataIndex: 'regulation_name',
      key: 'regulation_name',
      width: 220,
      ellipsis: true,
    },
    {
      title: '车间/部门',
      dataIndex: 'workshop',
      key: 'workshop',
      width: 110,
      render: (workshop: string) => workshop ? (
        <span style={pillInfo}>{workshop}</span>
      ) : (
        <span style={pillDefault}>未分配</span>
      ),
    },
    {
      title: '所属岗位',
      dataIndex: 'position',
      key: 'position',
      width: 100,
      render: (pos: string) => pos || '-',
    },
    {
      title: '文档',
      dataIndex: 'document_path',
      key: 'document_path',
      width: 190,
      ellipsis: true,
      render: (path: string, record: OperationRegulation) => {
        if (!path) return <span style={pillDefault}>未上传</span>
        return (
          <span
            role="button"
            style={{ ...$link, display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13 }}
            onClick={() => handleOpenPreview(record)}
            title="点击在线预览"
          >
            <FileTextOutlined style={{ fontSize: 14 }} />
            <Text ellipsis style={{ maxWidth: 140 }}>{record.document_original_name || path}</Text>
          </span>
        )
      },
    },
    {
      title: '标准化',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string, record: OperationRegulation) =>
        renderStandardizationStatus(status, record.content),
    },
    {
      title: '合规审核',
      key: 'compliance',
      width: 100,
      render: (_, record: OperationRegulation) => {
        const latest = latestReviews[record.id]
        if (!latest) return <span style={pillDefault}>未审核</span>
        const meta = REVIEW_RESULT_META[latest.result]
        if (!meta) return <span style={pillDefault}>{latest.result}</span>
        return (
          <Tooltip title={`${meta.label} · 评分 ${latest.score} · ${dayjs(latest.reviewed_at).format('YYYY-MM-DD HH:mm')}`}>
            <span style={statusPill(meta.color, meta.bg)}>{meta.label} {latest.score}</span>
          </Tooltip>
        )
      },
    },
    {
      title: '备注',
      dataIndex: 'notes',
      key: 'notes',
      width: 120,
      ellipsis: true,
      render: (notes: string) => notes || '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 105,
      render: (date: string) => (date ? dayjs(date).format('YYYY-MM-DD') : '-'),
    },
    {
      title: '操作',
      key: 'action',
      width: 440,
      fixed: 'right',
      render: (_, record) => (
        <Space size={12}>
          <Upload {...regulationUploadProps(record.id)}>
            <span role="button" style={$muted}>
              <UploadOutlined />上传
            </span>
          </Upload>
          <span role="button" style={$link} onClick={() => handleEditRegulation(record)}>
            <EditOutlined />编辑
          </span>
          <span role="button" style={$purple} onClick={() => openReviewModal(record)}>
            <SafetyCertificateOutlined />合规审核
          </span>
          <Tooltip title="查看/新建修订记录">
            <span
              role="button"
              style={$link}
              onClick={() => {
                setActiveTab('revisions')
                setRevisionQueryParams({ page: 1 })
              }}
            >
              <AimOutlined />修订
            </span>
          </Tooltip>
          {record.content ? (
            <span role="button" style={$purple} onClick={() => handleOpenEditor(record)}>
              <EyeOutlined />查看内容
            </span>
          ) : (
            <span role="button" style={$purple} onClick={() => setGeneratorModalOpen(true)}>
              <ThunderboltOutlined />标准化生成
            </span>
          )}
          <span role="button" style={$danger} onClick={() => handleDeleteRegulation(record.id)}>
            <DeleteOutlined />删除
          </span>
        </Space>
      ),
    },
  ]

  const revisionColumns: ColumnsType<RegulationRevision> = [
    {
      title: '修订编号',
      dataIndex: 'revision_no',
      key: 'revision_no',
      width: 140,
      render: (no: string) => (
        <span style={{ fontFamily: '"JetBrains Mono", "SF Mono", monospace', fontSize: 13, color: T.slate }}>
          {no}
        </span>
      ),
    },
    {
      title: '操规名称',
      dataIndex: 'regulation_name',
      key: 'regulation_name',
      width: 180,
      ellipsis: true,
    },
    {
      title: '修订类型',
      dataIndex: 'revision_type',
      key: 'revision_type',
      width: 90,
      render: (type: RevisionType) => {
        const opt = REVISION_TYPE_OPTIONS.find((o) => o.value === type)
        return (
          <span style={type === RevisionType.AI ? pillPurple : pillInfo}>
            {opt?.label || type}
          </span>
        )
      },
    },
    {
      title: '修订人',
      dataIndex: 'reviser_name',
      key: 'reviser_name',
      width: 80,
      render: (name: string) => name || '-',
    },
    {
      title: '时间',
      dataIndex: 'revision_time',
      key: 'revision_time',
      width: 100,
      render: (date: string) => (date ? dayjs(date).format('YYYY-MM-DD') : '-'),
    },
    {
      title: '修订范围',
      dataIndex: 'revision_scope',
      key: 'revision_scope',
      width: 100,
      render: (scope: string) => {
        const opt = REVISION_SCOPE_OPTIONS.find((o) => o.value === scope)
        if (!scope) return <span style={pillDefault}>未识别</span>
        return (
          <span style={scope === 'process' ? pillWarning : pillSuccess}>
            {opt?.label || scope}
          </span>
        )
      },
    },
    {
      title: '审核',
      dataIndex: 'review_opinion',
      key: 'review_opinion',
      width: 75,
      render: (opinion: string) => {
        const opt = REVIEW_OPINION_OPTIONS.find((o) => o.value === opinion)
        if (!opinion) return <span style={pillDefault}>待审核</span>
        const color = opt?.color || '#787671'
        const bgMap: Record<string, string> = {
          '#52c41a': '#d9f3e1',
          '#faad14': '#ffe8d4',
          '#ff4d4f': '#fde0ec',
        }
        return <span style={statusPill(color, bgMap[color] || '#f0eeec')}>{opt?.label || opinion}</span>
      },
    },
    {
      title: '备注',
      dataIndex: 'notes',
      key: 'notes',
      width: 120,
      ellipsis: true,
      render: (notes: string) => notes || '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 300,
      fixed: 'right',
      render: (_, record) => (
        <Space size={12}>
          {record.revision_type === RevisionType.MANUAL && !record.new_document_path && (
            <Upload {...manualUploadProps(record.id)}>
              <span role="button" style={$muted}>
                <UploadOutlined />上传修订稿
              </span>
            </Upload>
          )}

          {record.revision_type === RevisionType.AI && !record.new_document_path && (
            <span role="button" style={$purple} onClick={() => handleAIGenerate(record.id)}>
              <RobotOutlined />AI生成
            </span>
          )}

          {!record.revision_scope && (
            <span
              role="button"
              style={$link}
              onClick={() => handleIdentifyScope(record.id)}
            >
              <AimOutlined />
              {scopeLoading === record.id ? '识别中...' : '识别范围'}
            </span>
          )}

          {record.new_document_path && (
            <span role="button" style={$link}>
              <EyeOutlined />查看文档
            </span>
          )}

          <span role="button" style={$danger} onClick={() => handleDeleteRevision(record.id)}>
            <DeleteOutlined />删除
          </span>
        </Space>
      ),
    },
  ]

  // ========== Tab Items ==========

  const tabItems = [
    {
      key: 'regulations',
      label: (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
          <FileProtectOutlined style={{ fontSize: 15 }} />
          操规列表
        </span>
      ),
      children: (
        <>
          {/* Search / Filter Bar */}
          <div
            style={{
              marginBottom: 16,
              display: 'flex',
              gap: 12,
              alignItems: 'center',
              flexShrink: 0,
            }}
          >
            <Select
              placeholder="车间/部门"
              allowClear
              showSearch
              style={{ width: 140 }}
              value={workshopFilter}
              onChange={(v) => {
                setWorkshopFilter(v)
                setRegulationQueryParams({ page: 1 })
              }}
              options={WORKSHOP_OPTIONS}
            />
            <Select
              placeholder="所属岗位"
              allowClear
              style={{ width: 130 }}
              value={positionFilter}
              onChange={(v) => {
                setPositionFilter(v)
                setRegulationQueryParams({ page: 1 })
              }}
              options={[
                { value: '操作工', label: '操作工' },
                { value: '班组长', label: '班组长' },
                { value: '技术员', label: '技术员' },
                { value: '安全员', label: '安全员' },
              ]}
            />
            <Select
              placeholder="内容状态"
              allowClear
              style={{ width: 150 }}
              value={statusFilter}
              onChange={(v) => {
                setStatusFilter(v)
                setRegulationQueryParams({ page: 1 })
              }}
              options={[
                { value: 'reviewed,exported,draft', label: '全部台账' },
                { value: 'reviewed', label: '已审核' },
                { value: 'exported', label: '已导出' },
                { value: 'draft', label: '草稿' },
                { value: 'generated', label: '已生成（未审核）' },
              ]}
            />
            <Input
              placeholder="搜索操规名称"
              prefix={<SearchOutlined style={{ color: '#a4a097' }} />}
              style={{ width: 240 }}
              value={regSearchText}
              onChange={(e) => setRegSearchText(e.target.value)}
              onPressEnter={loadRegulations}
              allowClear
            />
            <div style={{ flex: 1 }} />
            <Button
              icon={<CloudUploadOutlined />}
              onClick={handleOpenBatchUpload}
              style={{
                borderRadius: 8,
                height: 36,
                fontWeight: 600,
                fontSize: 13,
                boxShadow: 'none',
                borderColor: '#5645d4',
                color: '#5645d4',
              }}
            >
              批量导入
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleAddRegulation}
              style={{
                borderRadius: 8,
                height: 36,
                background: '#5645d4',
                borderColor: '#5645d4',
                fontWeight: 600,
                fontSize: 13,
                boxShadow: 'none',
              }}
            >
              新建操规
            </Button>
          </div>

          <Table
            columns={regulationColumns}
            dataSource={regulations}
            rowKey="id"
            size="small"
            loading={regLoading}
            scroll={{ x: 1180 }}
            pagination={{
              current: regulationQueryParams.page,
              pageSize: regulationQueryParams.page_size,
              total: regulationTotal,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total) => `共 ${total} 条`,
              onChange: (page, pageSize) => setRegulationQueryParams({ page, page_size: pageSize }),
            }}
          />
        </>
      ),
    },
    {
      key: 'revisions',
      label: (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
          <HistoryOutlined style={{ fontSize: 15 }} />
          修订记录
        </span>
      ),
      children: (
        <>
          {/* Search / Filter Bar */}
          <div
            style={{
              marginBottom: 16,
              display: 'flex',
              gap: 12,
              alignItems: 'center',
              flexShrink: 0,
            }}
          >
            <Select
              placeholder="修订类型"
              allowClear
              style={{ width: 120 }}
              value={typeFilter}
              onChange={(v) => {
                setTypeFilter(v)
                setRevisionQueryParams({ page: 1 })
              }}
              options={REVISION_TYPE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            />
            <Select
              placeholder="修订范围"
              allowClear
              style={{ width: 120 }}
              value={scopeFilter}
              onChange={(v) => {
                setScopeFilter(v)
                setRevisionQueryParams({ page: 1 })
              }}
              options={REVISION_SCOPE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            />
            <Select
              placeholder="审核状态"
              allowClear
              style={{ width: 120 }}
              value={opinionFilter}
              onChange={(v) => {
                setOpinionFilter(v)
                setRevisionQueryParams({ page: 1 })
              }}
              options={REVIEW_OPINION_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            />
            <Input
              placeholder="搜索修订编号或操规名称"
              prefix={<SearchOutlined style={{ color: '#a4a097' }} />}
              style={{ width: 240 }}
              value={revSearchText}
              onChange={(e) => setRevSearchText(e.target.value)}
              onPressEnter={loadRevisions}
              allowClear
            />
            <div style={{ flex: 1 }} />
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleAddRevision}
              style={{
                borderRadius: 8,
                height: 36,
                background: '#5645d4',
                borderColor: '#5645d4',
                fontWeight: 600,
                fontSize: 13,
                boxShadow: 'none',
              }}
            >
              新建修订
            </Button>
          </div>

          <Table
            columns={revisionColumns}
            dataSource={revisions}
            rowKey="id"
            size="small"
            loading={revLoading}
            scroll={{ x: 1280 }}
            pagination={{
              current: revisionQueryParams.page,
              pageSize: revisionQueryParams.page_size,
              total: revisionTotal,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total) => `共 ${total} 条`,
              onChange: (page, pageSize) => setRevisionQueryParams({ page, page_size: pageSize }),
            }}
          />
        </>
      ),
    },
  ]

  // ========== Render ==========

  return (
    <div style={{ padding: '24px 28px' }}>
      {/* Page Title Header */}
      <div style={{ marginBottom: 24 }}>
        <h2
          style={{
            fontSize: 22,
            fontWeight: 600,
            color: '#1a1a1a',
            margin: 0,
            marginBottom: 4,
            lineHeight: 1.3,
          }}
        >
          安全操规管理
        </h2>
        <p style={{ fontSize: 14, color: '#787671', margin: 0, lineHeight: 1.5 }}>
          管理已审核的安全操作规程 · 车间归类 · 批量导入自动识别 · AI法规合规审核 · 版本修订 · 标准化生成
        </p>
      </div>

      {/* Content Card */}
      <div
        style={{
          background: '#ffffff',
          borderRadius: 12,
          border: '1px solid #e5e3df',
          padding: '4px 24px 24px',
        }}
      >
        <Tabs activeKey={activeTab} onChange={(key) => setActiveTab(key)} items={tabItems} />
      </div>

      {/* ═══ Regulation Drawer ═══ */}
      <Drawer
        title={editingRegulation ? '编辑操规' : '新建操规'}
        open={regDrawerOpen}
        onClose={() => setRegDrawerOpen(false)}
        styles={{ wrapper: { width: 480 } }}
        destroyOnHidden
        extra={
          <Space>
            <Button onClick={() => setRegDrawerOpen(false)}>取消</Button>
            <Button
              type="primary"
              loading={regSubmitting}
              onClick={handleRegSubmit}
              style={{
                borderRadius: 8,
                background: '#5645d4',
                borderColor: '#5645d4',
                fontWeight: 600,
                boxShadow: 'none',
              }}
            >
              保存
            </Button>
          </Space>
        }
      >
        <Form
          form={editingRegulation ? regEditForm : regForm}
          layout="vertical"
          requiredMark="optional"
        >
          <Form.Item
            name="regulation_no"
            label="操规编号（可选）"
          >
            <Input placeholder="由文控/车间编号时填写，可留空" />
          </Form.Item>
          <Form.Item
            name="regulation_name"
            label="操规名称"
            rules={[{ required: true, message: '请输入操规名称' }]}
          >
            <Input placeholder="请输入操规名称" />
          </Form.Item>
          <Form.Item name="position" label="所属岗位">
            <Input placeholder="请输入所属岗位" />
          </Form.Item>
          <Form.Item name="workshop" label="车间/部门">
            <Select
              showSearch
              allowClear
              placeholder="选择或输入车间/部门"
              options={WORKSHOP_OPTIONS}
            />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={3} placeholder="请输入备注" />
          </Form.Item>
        </Form>
      </Drawer>

      {/* ═══ Revision Drawer ═══ */}
      <Drawer
        title="新建修订记录"
        open={revDrawerOpen}
        onClose={() => setRevDrawerOpen(false)}
        styles={{ wrapper: { width: 480 } }}
        destroyOnHidden
        extra={
          <Space>
            <Button onClick={() => setRevDrawerOpen(false)}>取消</Button>
            <Button
              type="primary"
              loading={revSubmitting}
              onClick={handleRevSubmit}
              style={{
                borderRadius: 8,
                background: '#5645d4',
                borderColor: '#5645d4',
                fontWeight: 600,
                boxShadow: 'none',
              }}
            >
              保存
            </Button>
          </Space>
        }
      >
        <Form form={revForm} layout="vertical" requiredMark="optional">
          <Form.Item
            name="revision_no"
            label="修订编号"
            rules={[{ required: true, message: '请输入修订编号' }]}
          >
            <Input placeholder="请输入修订编号" />
          </Form.Item>
          <Form.Item
            name="revision_type"
            label="修订类型"
            rules={[{ required: true, message: '请选择修订类型' }]}
          >
            <Select
              options={REVISION_TYPE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
              placeholder="人工修订 / AI修订"
            />
          </Form.Item>
          <Form.Item
            name="regulation_id"
            label="关联操规"
            rules={[{ required: true, message: '请选择关联操规' }]}
          >
            <Select
              showSearch
              placeholder="请选择操规"
              filterOption={(input, option) =>
                (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
              }
              options={regulationsForSelect.map((r) => ({
                value: r.id,
                label: `${r.regulation_no} - ${r.regulation_name}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="reviser" label="修订人ID">
            <Input placeholder="请输入修订人ID" />
          </Form.Item>
          <Form.Item name="reviser_name" label="修订人姓名">
            <Input placeholder="请输入修订人姓名" />
          </Form.Item>
          <Form.Item name="revision_opinion" label="修订意见">
            <Input.TextArea rows={4} placeholder="描述修订意见，AI修订模式将基于此意见生成修订稿" />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} placeholder="请输入备注" />
          </Form.Item>
        </Form>
      </Drawer>

      {/* ═══ AI Generation Result Modal ═══ */}
      <Modal
        title="AI 修订生成结果"
        open={aiModalVisible}
        onOk={handleAIConfirm}
        onCancel={() => {
          setAiModalVisible(false)
          setAiContent('')
          setAiRevisionId(null)
        }}
        width={800}
        okText="确认保存"
        cancelText="取消"
        confirmLoading={aiConfirming}
        okButtonProps={{ disabled: !aiContent || aiGenerating }}
      >
        {aiGenerating ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '48px 0' }}>
            <Spin size="large" />
            <Text style={{ marginTop: 16, color: '#787671' }}>AI 正在生成修订稿...</Text>
          </div>
        ) : aiContent ? (
          <>
            <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 8, color: '#1a1a1a' }}>文档名称</div>
            <Input
              value={aiDocumentName}
              onChange={(e) => setAiDocumentName(e.target.value)}
              placeholder="修订稿文件名"
            />
            <Divider style={{ margin: '16px 0' }} />
            <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 8, color: '#1a1a1a' }}>生成内容预览</div>
            <div
              style={{
                background: '#fafaf9',
                border: '1px solid #e5e3df',
                borderRadius: 8,
                padding: 16,
                maxHeight: 400,
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
                fontSize: 13,
                lineHeight: 1.6,
                color: '#37352f',
              }}
            >
              {aiContent}
            </div>
          </>
        ) : null}
      </Modal>

      {/* ── SOP Generator Modal ── */}
      <SopGeneratorModal
        open={generatorModalOpen}
        onClose={() => setGeneratorModalOpen(false)}
        onGenerated={handleSopGenerated}
      />

      {/* ═══ 批量导入 Modal ═══ */}
      <Modal
        title={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <CloudUploadOutlined style={{ color: '#5645d4' }} />
            批量导入车间操规（自动识别）
          </span>
        }
        open={batchOpen}
        onCancel={() => setBatchOpen(false)}
        footer={[
          <Button key="close" onClick={() => setBatchOpen(false)}>
            关闭
          </Button>,
          <Button
            key="upload"
            type="primary"
            icon={<CloudUploadOutlined />}
            loading={batchUploading}
            onClick={handleBatchUpload}
            style={{
              borderRadius: 8,
              background: '#5645d4',
              borderColor: '#5645d4',
              fontWeight: 600,
            }}
          >
            开始导入（{batchFiles.length} 个文件）
          </Button>,
        ]}
        width={880}
      >
        <Upload.Dragger
          multiple
          accept=".docx,.doc,.docm,.pdf,.txt,.md"
          showUploadList={false}
          beforeUpload={(file) => {
            const uid = `${Date.now()}-${file.name}-${batchFiles.length}`
            setBatchFiles((prev) => [...prev, { file, uid }])
            return false
          }}
          onRemove={(file) => {
            setBatchFiles((prev) => prev.filter((entry) => entry.uid !== file.uid))
          }}
          fileList={batchFiles.map((entry) => ({
            uid: entry.uid,
            name: entry.file.name,
            size: entry.file.size,
            status: 'done' as const,
          }))}
        >
          <p style={{ fontSize: 32, color: '#5645d4', margin: '12px 0 4px' }}>
            <CloudUploadOutlined />
          </p>
          <p style={{ fontSize: 14, fontWeight: 500 }}>点击或拖拽操规文件到此处</p>
          <p style={{ fontSize: 12, color: '#787671' }}>
            支持 docx / doc / docm / pdf / txt / md，单次最多 50 个，单个 ≤ 20MB；
            系统自动识别车间、岗位并生成台账记录，同名文件重复导入自动跳过
          </p>
        </Upload.Dragger>
        <div
          style={{
            display: 'flex',
            gap: 12,
            alignItems: 'center',
            marginTop: 12,
            flexWrap: 'wrap',
          }}
        >
          <span style={{ fontSize: 13, color: T.slate }}>文件名未标明车间时归属：</span>
          <Select
            placeholder="选择兜底车间"
            allowClear
            showSearch
            style={{ width: 160 }}
            value={batchHintWorkshop}
            onChange={setBatchHintWorkshop}
            options={WORKSHOP_OPTIONS}
          />
          <span style={{ fontSize: 13, color: T.slate }}>AI 辅助识别：</span>
          <Switch checked={batchUseAi} onChange={setBatchUseAi} />
          <span style={{ fontSize: 12, color: '#a4a097' }}>
            关闭后仅按文件名规则识别（更快，不消耗模型额度）
          </span>
        </div>
        {batchResult && (
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 8 }}>导入结果</div>
            <Table
              size="small"
              rowKey={(record) => record.file_name}
              dataSource={batchResult.items}
              pagination={false}
              scroll={{ y: 260 }}
              columns={[
                {
                  title: '文件名',
                  dataIndex: 'file_name',
                  ellipsis: true,
                  width: 220,
                },
                {
                  title: '车间',
                  dataIndex: 'workshop',
                  width: 100,
                  render: (v: string) => v || '-',
                },
                {
                  title: '岗位',
                  dataIndex: 'position',
                  width: 90,
                  render: (v: string) => v || '-',
                },
                {
                  title: '识别',
                  dataIndex: 'recognized_by',
                  width: 70,
                  render: (v: string) => (
                    <span style={v === 'ai' ? pillPurple : pillNeutral}>
                      {v === 'ai' ? 'AI' : '规则'}
                    </span>
                  ),
                },
                {
                  title: '结果',
                  dataIndex: 'ok',
                  width: 80,
                  render: (ok: boolean, record) =>
                    ok ? (
                      <span style={pillSuccess}>成功</span>
                    ) : (
                      <Tooltip title={record.message}>
                        <span style={pillError}>{record.message.includes('已导入') ? '跳过' : '失败'}</span>
                      </Tooltip>
                    ),
                },
              ]}
            />
          </div>
        )}
      </Modal>

      {/* ═══ AI 法规合规审核 Modal ═══ */}
      <Modal
        title={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <SafetyCertificateOutlined style={{ color: '#5645d4' }} />
            AI 法规合规审核
            {reviewTarget && (
              <span style={{ fontSize: 13, fontWeight: 400, color: T.slate }}>
                · {reviewTarget.regulation_name}
              </span>
            )}
          </span>
        }
        open={reviewOpen}
        onCancel={() => setReviewOpen(false)}
        footer={[
          <Button
            key="history"
            icon={<HistoryOutlined />}
            loading={reviewHistoryLoading}
            onClick={handleLoadReviewHistory}
          >
            审核历史
          </Button>,
          <Button key="close" onClick={() => setReviewOpen(false)}>
            关闭
          </Button>,
          <Button
            key="run"
            type="primary"
            icon={<SafetyOutlined />}
            loading={reviewRunning}
            onClick={handleRunReview}
            style={{
              borderRadius: 8,
              background: '#5645d4',
              borderColor: '#5645d4',
              fontWeight: 600,
            }}
          >
            {reviewReport ? '重新审核' : '开始审核'}
          </Button>,
        ]}
        width={960}
      >
        {reviewRunning && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '48px 0',
            }}
          >
            <Spin size="large" />
            <Text style={{ marginTop: 16, color: '#787671' }}>
              AI 正在依据安全法规审核要点逐项核对操规内容（约需 1-2 分钟）...
            </Text>
          </div>
        )}
        {!reviewRunning && reviewReport && (
          <div style={{ maxHeight: 520, overflow: 'auto' }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
              {(() => {
                const meta = REVIEW_RESULT_META[reviewReport.result]
                return meta ? (
                  <span style={{ ...statusPill(meta.color, meta.bg), fontSize: 14, padding: '4px 12px' }}>
                    {meta.label}
                  </span>
                ) : null
              })()}
              <span style={{ fontSize: 14, color: T.slate }}>
                合规评分 <b style={{ fontSize: 18, color: '#1a1a1a' }}>{reviewReport.score}</b> / 100
              </span>
              <span style={{ fontSize: 12, color: '#a4a097' }}>
                {dayjs(reviewReport.created_at).format('YYYY-MM-DD HH:mm')}
              </span>
            </div>
            <div
              style={{
                background: '#fafaf9',
                border: '1px solid #e5e3df',
                borderRadius: 8,
                padding: 12,
                fontSize: 13,
                lineHeight: 1.7,
                color: '#37352f',
                marginBottom: 16,
              }}
            >
              {reviewReport.summary || '（AI 未给出总体评价）'}
              <div style={{ marginTop: 6, fontSize: 12, color: '#a4a097' }}>
                AI 结论仅作辅助分析，整改与放行请由车间和安全管理员人工确认。
              </div>
            </div>
            {reviewReport.missing_items.length > 0 && (
              <>
                <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 8 }}>
                  缺失项（{reviewReport.missing_items.length}）
                </div>
                <Table
                  size="small"
                  rowKey={(_, index) => `missing-${index}`}
                  dataSource={reviewReport.missing_items}
                  pagination={false}
                  columns={reviewItemColumns}
                />
              </>
            )}
            {reviewReport.non_compliant_items.length > 0 && (
              <>
                <div style={{ fontSize: 14, fontWeight: 500, margin: '16px 0 8px' }}>
                  不合规项（{reviewReport.non_compliant_items.length}）
                </div>
                <Table
                  size="small"
                  rowKey={(_, index) => `nc-${index}`}
                  dataSource={reviewReport.non_compliant_items}
                  pagination={false}
                  columns={reviewItemColumns}
                />
              </>
            )}
            {reviewReport.missing_items.length === 0 && reviewReport.non_compliant_items.length === 0 && (
              <div style={{ fontSize: 13, color: '#52c41a', padding: '8px 0' }}>
                未发现缺失或不合规项。
              </div>
            )}
            {reviewReport.suggestions.length > 0 && (
              <>
                <div style={{ fontSize: 14, fontWeight: 500, margin: '16px 0 8px' }}>优先整改建议</div>
                <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.9 }}>
                  {reviewReport.suggestions.map((suggestion, index) => (
                    <li key={index}>{suggestion}</li>
                  ))}
                </ul>
              </>
            )}
            {reviewHistory.length > 0 && (
              <>
                <div style={{ fontSize: 14, fontWeight: 500, margin: '16px 0 8px' }}>审核历史</div>
                {reviewHistory.map((item) => {
                  const meta = REVIEW_RESULT_META[item.result]
                  return (
                    <div
                      key={item.id}
                      style={{
                        display: 'flex',
                        gap: 10,
                        alignItems: 'center',
                        fontSize: 13,
                        padding: '4px 0',
                        borderBottom: '1px dashed #e5e3df',
                      }}
                    >
                      {meta ? (
                        <span style={statusPill(meta.color, meta.bg)}>{meta.label}</span>
                      ) : (
                        <span style={pillDefault}>{item.result}</span>
                      )}
                      <span style={{ color: T.slate }}>{item.score} 分</span>
                      <span style={{ color: '#a4a097' }}>
                        {dayjs(item.created_at).format('YYYY-MM-DD HH:mm')}
                      </span>
                    </div>
                  )
                })}
              </>
            )}
          </div>
        )}
        {!reviewRunning && !reviewReport && (
          <div style={{ fontSize: 13, color: T.slate, lineHeight: 2 }}>
            <p style={{ margin: 0 }}>
              依据内置安全法规审核要点逐项核对操规内容，覆盖：
            </p>
            <ul style={{ margin: '4px 0 0', paddingLeft: 20 }}>
              <li>编制审批与版本管理、适用范围与岗位职责（含特种作业持证）</li>
              <li>危险因素辨识、安全操作步骤与工艺参数、异常故障处置</li>
              <li>个体防护用品、特殊作业管控（GB 30871）、应急处置措施</li>
              <li>职业健康与环保、安全警示禁止事项、培训考核记录</li>
            </ul>
            <p style={{ margin: '8px 0 0', color: '#a4a097', fontSize: 12 }}>
              审核依据：《安全生产法》《危险化学品安全管理条例》、GB 30871-2022、
              GB/T 33000-2016、AQ/T 3034 等法规标准的要点拆解；无内容的操规请先上传文档或生成标准化内容。
            </p>
          </div>
        )}
      </Modal>

      {/* ═══ 文档在线预览 Modal ═══ */}
      <Modal
        title={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, maxWidth: '80vw' }}>
            <FileTextOutlined style={{ color: '#0075de' }} />
            <Text ellipsis style={{ maxWidth: '72vw' }}>
              {previewData?.file_name || previewTarget?.regulation_name || '文档预览'}
            </Text>
          </span>
        }
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        width="92vw"
        footer={[
          <Button
            key="download"
            icon={<DownloadOutlined />}
            loading={previewDownloading}
            onClick={handleDownloadDocument}
            disabled={!previewTarget?.document_path}
          >
            下载原文件
          </Button>,
          <Button key="close" type="primary" onClick={() => setPreviewOpen(false)}
            style={{
              borderRadius: 8,
              background: '#5645d4',
              borderColor: '#5645d4',
              fontWeight: 600,
            }}>
            关闭
          </Button>,
        ]}
      >
        {previewLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '48px 0' }}>
            <Spin size="large" />
            <Text style={{ marginTop: 16, color: '#787671' }}>正在提取文档正文...</Text>
          </div>
        ) : (
          <>
            {previewData?.note && (
              <div
                style={{
                  background: '#fff7e8',
                  border: '1px solid #ffd591',
                  borderRadius: 8,
                  padding: '8px 12px',
                  fontSize: 13,
                  color: '#d46b08',
                  marginBottom: 12,
                }}
              >
                {previewData.note}
              </div>
            )}
            {previewData?.content ? (
              <div
                className="sop-doc-preview"
                style={{
                  background: '#fafaf9',
                  border: '1px solid #e5e3df',
                  borderRadius: 8,
                  padding: '20px 28px',
                  maxHeight: '68vh',
                  overflow: 'auto',
                  fontSize: 13.5,
                  lineHeight: 1.9,
                  color: '#37352f',
                }}
              >
                <style>{`
                  .sop-doc-preview h1, .sop-doc-preview h2, .sop-doc-preview h3,
                  .sop-doc-preview h4 { font-weight: 600; color: #1a1a1a; margin: 18px 0 8px; line-height: 1.5; }
                  .sop-doc-preview h1 { font-size: 18px; border-bottom: 2px solid #e5e3df; padding-bottom: 6px; }
                  .sop-doc-preview h2 { font-size: 16px; }
                  .sop-doc-preview h3, .sop-doc-preview h4 { font-size: 14.5px; }
                  .sop-doc-preview h1:first-child, .sop-doc-preview h2:first-child { margin-top: 0; }
                  .sop-doc-preview p { margin: 8px 0; }
                  .sop-doc-preview ul, .sop-doc-preview ol { margin: 8px 0; padding-left: 24px; }
                  .sop-doc-preview li { margin: 4px 0; }
                  .sop-doc-preview table { border-collapse: collapse; width: 100%; margin: 12px 0; }
                  .sop-doc-preview th, .sop-doc-preview td { border: 1px solid #d6d3cd; padding: 6px 10px; font-size: 12.5px; text-align: left; }
                  .sop-doc-preview th { background: #efede9; font-weight: 600; }
                  .sop-doc-preview strong { color: #1a1a1a; }
                  .sop-doc-preview blockquote { border-left: 3px solid #d6d3cd; margin: 8px 0; padding: 2px 12px; color: #787671; }
                `}</style>
                <ReactMarkdown>{previewData.content}</ReactMarkdown>
              </div>
            ) : (
              !previewData?.note && (
                <div style={{ color: '#787671', fontSize: 13, padding: '24px 0', textAlign: 'center' }}>
                  暂无可预览内容
                </div>
              )
            )}
          </>
        )}
      </Modal>

    </div>
  )
}
