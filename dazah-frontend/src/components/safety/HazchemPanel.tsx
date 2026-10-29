'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileTextOutlined,
  RobotOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { FeishuAttachmentPreviewModal } from '@/components/quality'
import {
  createHazardousChemical,
  deleteChemicalMsdsFile,
  deleteHazardousChemical,
  fetchChemicalMsdsBytes,
  getHazardousChemicals,
  listChemicalMsdsFiles,
  reextractChemicalMsdsFile,
  updateHazardousChemical,
  uploadChemicalMsdsFile,
  type ChemicalMsdsFileItem,
  type HazardousChemicalItem,
  type MsdsExtractionSuggestion,
} from '@/actions/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import { SAFETY_PAGE_TABLE_KEYS } from '@/lib/safety-page-tables'
import PageFeishuTable from './PageFeishuTable'

/** Server Action 返回 base64：在浏览器侧组装成 Blob URL。 */
function base64ToObjectUrl(base64: string, contentType: string): string {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return URL.createObjectURL(new Blob([bytes], { type: contentType }))
}

const { Text, Title } = Typography

const T = {
  error: '#E03131',
  warning: '#DD5B00',
  success: '#1AAE39',
  charcoal: '#37352f',
  slate: '#5d5b54',
  steel: '#787671',
  muted: '#bbb8b1',
  hairline: '#e5e3df',
  surface: '#f6f5f4',
  mint: '#d9f3e1',
  rose: '#fde0ec',
  peach: '#ffe8d4',
}

export const CHEMICAL_CATEGORY_LABELS: Record<string, string> = {
  explosive: '爆炸物',
  flammable_gas: '易燃气体',
  oxidizing_gas: '氧化性气体',
  flammable_liquid: '易燃液体',
  flammable_solid: '易燃固体',
  self_reactive: '自反应物质',
  oxidizing_liquid: '氧化性液体',
  organic_peroxide: '有机过氧化物',
  toxic: '毒性物质',
  corrosive: '腐蚀性物质',
  other: '其他',
}

const MSDS_ACCEPT = '.pdf,.doc,.docx,.png,.jpg,.jpeg'

interface ChemicalFormValues {
  name: string
  alias?: string
  cas_no?: string
  category: string
  hazard_statements?: string
  storage_requirements?: string
  remark?: string
}

interface MsdsPreviewState {
  open: boolean
  fileName: string
  previewSrc: string
  downloadSrc: string
  objectUrls: string[]
}

interface AiSuggestionState {
  open: boolean
  chemical: HazardousChemicalItem | null
  aiError: string | null
}

function formatSize(bytes: number): string {
  if (!bytes) return ''
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)}KB`
  return `${bytes}B`
}

export default function HazchemPanel({
  pageKey,
  initialChemicals,
  initialError,
}: {
  pageKey: string
  initialChemicals: HazardousChemicalItem[]
  initialError: string | null
}) {
  const { canOperate, canDelete } = usePagePermissions(pageKey)
  const { message } = App.useApp()

  const [chemicals, setChemicals] = useState<HazardousChemicalItem[]>(initialChemicals)
  const [chemTotal, setChemTotal] = useState(initialChemicals.length)
  const [error, setError] = useState<string | null>(initialError)
  const [loading, setLoading] = useState(false)
  const [chemKeyword, setChemKeyword] = useState('')
  const [activeTab, setActiveTab] = useState('chemicals')
  // 车间库存镜像表较重（拉取绑定表格列与记录），首次切到该页签时再挂载
  const [inventoryMounted, setInventoryMounted] = useState(false)

  const [chemFormOpen, setChemFormOpen] = useState(false)
  const [editingChemical, setEditingChemical] = useState<HazardousChemicalItem | null>(null)
  const [chemForm] = Form.useForm<ChemicalFormValues>()

  // MSDS 附件管理（按档案懒加载，避免列表页 N+1 拉附件）
  const [msdsChemical, setMsdsChemical] = useState<HazardousChemicalItem | null>(null)
  const [msdsFiles, setMsdsFiles] = useState<ChemicalMsdsFileItem[]>([])
  const [msdsLoading, setMsdsLoading] = useState(false)
  const [msdsUploading, setMsdsUploading] = useState(false)
  const [preview, setPreview] = useState<MsdsPreviewState>({
    open: false,
    fileName: '',
    previewSrc: '',
    downloadSrc: '',
    objectUrls: [],
  })

  // AI 识别结果确认（人工确认后才写入档案）
  const [aiState, setAiState] = useState<AiSuggestionState>({
    open: false,
    chemical: null,
    aiError: null,
  })
  const [aiForm] = Form.useForm<ChemicalFormValues>()
  const [aiApplying, setAiApplying] = useState(false)

  useEffect(() => {
    setChemicals(initialChemicals)
    setChemTotal(initialChemicals.length)
    setError(initialError)
  }, [initialChemicals, initialError])

  const refreshChemicals = useCallback(
    async (nextKeyword = chemKeyword) => {
      setLoading(true)
      try {
        const res = await getHazardousChemicals({
          keyword: nextKeyword || undefined,
          page_size: 200,
        })
        if (res.code === 200 && res.data) {
          setChemicals(res.data.items)
          setChemTotal(res.data.total)
          setError(null)
        } else {
          setError(res.message || '加载危化品档案失败')
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载危化品档案失败')
      } finally {
        setLoading(false)
      }
    },
    [chemKeyword]
  )

  const openChemCreate = () => {
    setEditingChemical(null)
    chemForm.setFieldsValue({
      name: '',
      alias: '',
      cas_no: '',
      category: 'flammable_liquid',
      hazard_statements: '',
      storage_requirements: '',
      remark: '',
    })
    setChemFormOpen(true)
  }

  const openChemEdit = (item: HazardousChemicalItem) => {
    setEditingChemical(item)
    chemForm.setFieldsValue({ ...item })
    setChemFormOpen(true)
  }

  const submitChemical = async () => {
    const values = await chemForm.validateFields()
    const payload = {
      name: values.name,
      alias: values.alias ?? '',
      cas_no: values.cas_no ?? '',
      category: values.category,
      hazard_statements: values.hazard_statements ?? '',
      storage_requirements: values.storage_requirements ?? '',
      remark: values.remark ?? '',
    }
    try {
      const res = editingChemical
        ? await updateHazardousChemical(editingChemical.id, payload)
        : await createHazardousChemical(payload)
      if (res.code === 200) {
        message.success(editingChemical ? '档案已更新' : '档案已创建')
        setChemFormOpen(false)
        await refreshChemicals()
      } else {
        message.error(res.message || '保存失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const handleChemDelete = async (item: HazardousChemicalItem) => {
    const res = await deleteHazardousChemical(item.id)
    if (res.code === 200) {
      message.success('档案已删除')
      await refreshChemicals()
    } else {
      message.error(res.message || '删除失败')
    }
  }

  // ---------- MSDS 附件 ----------

  const refreshMsdsFiles = useCallback(async (chemicalId: string) => {
    const res = await listChemicalMsdsFiles(chemicalId)
    if (res.code === 200 && res.data) {
      setMsdsFiles(res.data.items ?? [])
    }
  }, [])

  const openMsdsManager = (chemical: HazardousChemicalItem) => {
    setMsdsChemical(chemical)
    setMsdsFiles([])
    setMsdsLoading(true)
    void refreshMsdsFiles(chemical.id).finally(() => setMsdsLoading(false))
  }

  /** 打开 AI 识别确认弹窗：识别值覆盖非空字段，其余保持档案当前值。 */
  const openAiSuggestion = (
    chemical: HazardousChemicalItem,
    suggestion: MsdsExtractionSuggestion | null,
    aiError: string | null
  ) => {
    if (!suggestion) {
      if (aiError) message.info(`MSDS 已保存；AI 识别未完成：${aiError}`)
      return
    }
    aiForm.setFieldsValue({
      name: suggestion.name ?? chemical.name,
      alias: suggestion.alias ?? chemical.alias,
      cas_no: suggestion.cas_no ?? chemical.cas_no,
      category: suggestion.category ?? chemical.category,
      hazard_statements: suggestion.hazard_statements ?? chemical.hazard_statements,
      storage_requirements:
        suggestion.storage_requirements ?? chemical.storage_requirements,
      remark: suggestion.remark ?? chemical.remark,
    })
    setAiState({ open: true, chemical, aiError })
  }

  const handleMsdsUpload = async (file: File) => {
    if (!msdsChemical) return null
    setMsdsUploading(true)
    try {
      const res = await uploadChemicalMsdsFile(msdsChemical.id, file)
      if (res.code === 200 && res.data) {
        message.success('MSDS 已上传')
        await refreshMsdsFiles(msdsChemical.id)
        openAiSuggestion(
          res.data.chemical && res.data.chemical.id === msdsChemical.id
            ? res.data.chemical
            : msdsChemical,
          res.data.ai_suggestion ?? null,
          res.data.ai_error ?? null
        )
      } else {
        message.error(res.message || '上传失败')
      }
      return res
    } catch (err) {
      message.error(err instanceof Error ? err.message : '上传失败')
      return null
    } finally {
      setMsdsUploading(false)
    }
  }

  const handleMsdsPreview = async (file: ChemicalMsdsFileItem) => {
    if (!msdsChemical) return
    try {
      const [preview, download] = await Promise.all([
        fetchChemicalMsdsBytes(msdsChemical.id, file.id, true),
        fetchChemicalMsdsBytes(msdsChemical.id, file.id, false),
      ])
      const previewSrc = base64ToObjectUrl(preview.base64, preview.contentType)
      const downloadSrc = base64ToObjectUrl(download.base64, download.contentType)
      setPreview({
        open: true,
        fileName: file.file_name,
        previewSrc,
        downloadSrc,
        objectUrls: [previewSrc, downloadSrc],
      })
    } catch (err) {
      message.error(err instanceof Error ? err.message : '预览加载失败')
    }
  }

  /** 下载：Server Action 取字节 → 浏览器侧触发保存。 */
  const handleMsdsDownload = async (file: ChemicalMsdsFileItem) => {
    if (!msdsChemical) return
    try {
      const payload = await fetchChemicalMsdsBytes(msdsChemical.id, file.id, false)
      const url = base64ToObjectUrl(payload.base64, payload.contentType)
      const link = document.createElement('a')
      link.href = url
      link.download = file.file_name || 'MSDS'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '下载失败')
    }
  }

  const closePreview = () => {    for (const url of preview.objectUrls) URL.revokeObjectURL(url)
    setPreview({
      open: false,
      fileName: '',
      previewSrc: '',
      downloadSrc: '',
      objectUrls: [],
    })
  }

  const handleMsdsDelete = async (file: ChemicalMsdsFileItem) => {
    if (!msdsChemical) return
    const res = await deleteChemicalMsdsFile(msdsChemical.id, file.id)
    if (res.code === 200) {
      message.success('附件已删除')
      await refreshMsdsFiles(msdsChemical.id)
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const handleReextract = async (file: ChemicalMsdsFileItem) => {
    if (!msdsChemical) return
    const res = await reextractChemicalMsdsFile(msdsChemical.id, file.id)
    if (res.code === 200 && res.data) {
      openAiSuggestion(
        msdsChemical,
        res.data.ai_suggestion ?? null,
        res.data.ai_error ?? null
      )
    } else {
      message.error(res.message || '识别失败')
    }
  }

  const applyAiSuggestion = async () => {
    if (!aiState.chemical) return
    const values = await aiForm.validateFields()
    setAiApplying(true)
    try {
      const res = await updateHazardousChemical(aiState.chemical.id, {
        name: values.name,
        alias: values.alias ?? '',
        cas_no: values.cas_no ?? '',
        category: values.category,
        hazard_statements: values.hazard_statements ?? '',
        storage_requirements: values.storage_requirements ?? '',
        remark: values.remark ?? '',
      })
      if (res.code === 200) {
        message.success('档案已按识别结果更新')
        setAiState({ open: false, chemical: null, aiError: null })
        await refreshChemicals()
      } else {
        message.error(res.message || '更新失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '更新失败')
    } finally {
      setAiApplying(false)
    }
  }

  const chemicalColumns: ColumnsType<HazardousChemicalItem> = [
    {
      title: '品名',
      dataIndex: 'name',
      key: 'name',
      render: (v, row) => (
        <div>
          <Text strong style={{ color: T.charcoal }}>{v}</Text>
          {row.alias && (
            <div>
              <Text style={{ color: T.steel, fontSize: 12 }}>{row.alias}</Text>
            </div>
          )}
        </div>
      ),
    },
    {
      title: 'CAS 号',
      dataIndex: 'cas_no',
      key: 'cas_no',
      width: 130,
      render: (v: string) => (
        <Text style={{ fontFamily: 'monospace', fontSize: 12, color: T.steel }}>{v || '-'}</Text>
      ),
    },
    {
      title: '危险性类别',
      dataIndex: 'category',
      key: 'category',
      width: 120,
      render: (v: string) => (
        <Tag style={{ borderRadius: 6, border: 'none', backgroundColor: T.peach, color: T.warning, fontWeight: 600 }}>
          {CHEMICAL_CATEGORY_LABELS[v] || v}
        </Tag>
      ),
    },
    {
      title: 'MSDS 附件',
      key: 'msds',
      width: 130,
      render: (_, row) => (
        <Button
          type="link"
          size="small"
          icon={<FileTextOutlined />}
          style={{ padding: 0 }}
          onClick={() => openMsdsManager(row)}
        >
          查看 / 上传
        </Button>
      ),
    },
    {
      title: '储存要求',
      dataIndex: 'storage_requirements',
      key: 'storage_requirements',
      ellipsis: true,
      render: (v: string) => (
        <Text style={{ fontSize: 12, color: T.steel }}>{v || '-'}</Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" style={{ padding: 0 }} disabled={!canOperate} onClick={() => openChemEdit(row)}>
            编辑
          </Button>
          <Popconfirm title="确定删除该危化品档案？" onConfirm={() => handleChemDelete(row)} disabled={!canDelete}>
            <Button type="link" size="small" danger style={{ padding: 0 }} disabled={!canDelete}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4 pb-8">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <Title level={4} className="!mb-1">危化品与 MSDS 管理</Title>
          <Text style={{ color: T.slate, fontSize: 13 }}>
            危化品档案与 MSDS 附件；车间库存/超储镜像自飞书危化品统计表
          </Text>
        </div>
      </div>

      {error && (
        <Card variant="borderless" style={{ borderRadius: 12, border: `1px solid ${T.error}33` }}>
          <Text style={{ color: T.error }}>{error}</Text>
        </Card>
      )}

      <Card variant="borderless" style={{ borderRadius: 12, border: `1px solid ${T.hairline}` }}>
        <Tabs
          activeKey={activeTab}
          onChange={(key) => {
            setActiveTab(key)
            if (key === 'inventory') setInventoryMounted(true)
          }}
          items={[
            {
              key: 'chemicals',
              label: '危化品档案',
              children: (
                <>
                  <div className="flex items-center gap-3 mb-3 flex-wrap">
                    <Input.Search
                      placeholder="搜索品名/别名/CAS"
                      allowClear
                      style={{ maxWidth: 260 }}
                      onSearch={(v) => {
                        setChemKeyword(v)
                        void refreshChemicals(v)
                      }}
                    />
                    <Button type="primary" disabled={!canOperate} onClick={openChemCreate}>
                      新增危化品
                    </Button>
                    <Text style={{ color: T.muted, fontSize: 12, marginLeft: 'auto' }}>共 {chemTotal} 条</Text>
                  </div>
                  <Table<HazardousChemicalItem>
                    rowKey="id"
                    columns={chemicalColumns}
                    dataSource={chemicals}
                    loading={loading}
                    pagination={{ pageSize: 20, showSizeChanger: false }}
                    size="middle"
                  />
                </>
              ),
            },
            {
              key: 'inventory',
              label: '车间库存/超储',
              children: inventoryMounted ? (
                <PageFeishuTable
                  pageKey={SAFETY_PAGE_TABLE_KEYS.hazchemMsds}
                  pageName="危化品统计表"
                  showStats={false}
                  summarizeColumns={false}
                  allowCreate
                  hideMetaHint
                  defaultSortField="车间"
                />
              ) : null,
            },
          ]}
        />
      </Card>

      <Modal
        title={editingChemical ? '编辑危化品档案' : '新增危化品档案'}
        open={chemFormOpen}
        onOk={submitChemical}
        onCancel={() => setChemFormOpen(false)}
        width={640}
        destroyOnHidden
      >
        <Form<ChemicalFormValues> form={chemForm} layout="vertical" className="mt-3">
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="name" label="化学品名称" rules={[{ required: true, message: '请填写品名' }]}>
              <Input placeholder="如：乙醇" />
            </Form.Item>
            <Form.Item name="alias" label="别名/商品名">
              <Input />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="cas_no" label="CAS 号">
              <Input placeholder="如 64-17-5" />
            </Form.Item>
            <Form.Item name="category" label="危险性类别" rules={[{ required: true }]}>
              <Select
                options={Object.entries(CHEMICAL_CATEGORY_LABELS).map(([value, label]) => ({
                  value,
                  label,
                }))}
              />
            </Form.Item>
          </div>
          <Form.Item name="hazard_statements" label="危险性概述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="storage_requirements" label="储存要求">
            <Input.TextArea rows={2} placeholder="温度/禁配/防爆等要求" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`MSDS 附件 · ${msdsChemical?.name ?? ''}`}
        open={msdsChemical !== null}
        onCancel={() => setMsdsChemical(null)}
        footer={
          <Upload
            multiple
            showUploadList={false}
            accept={MSDS_ACCEPT}
            disabled={!canOperate || msdsUploading || msdsChemical === null}
            beforeUpload={(file) => {
              void handleMsdsUpload(file as File)
              return false
            }}
          >
            <Button type="primary" icon={<UploadOutlined />} loading={msdsUploading} disabled={!canOperate}>
              上传 MSDS（{MSDS_ACCEPT.replace(/\./g, '').toUpperCase()}）
            </Button>
          </Upload>
        }
        width={720}
        destroyOnHidden
      >
        <Text style={{ color: T.steel, fontSize: 12 }}>
          上传后自动 AI 识别 MSDS 内容（品名/CAS/危险性/储存要求等），确认后写入档案；支持 pdf/doc/docx/图片，单文件 ≤30MB。
        </Text>
        <List
          className="mt-3"
          size="small"
          loading={msdsLoading}
          dataSource={msdsFiles}
          locale={{ emptyText: '暂无 MSDS 附件' }}
          renderItem={(file) => (
            <List.Item
              actions={[
                <Button
                  key="preview"
                  type="link"
                  size="small"
                  icon={<EyeOutlined />}
                  style={{ padding: 0 }}
                  onClick={() => void handleMsdsPreview(file)}
                >
                  预览
                </Button>,
                <Button
                  key="download"
                  type="link"
                  size="small"
                  icon={<DownloadOutlined />}
                  style={{ padding: 0 }}
                  onClick={() => void handleMsdsDownload(file)}
                >
                  下载
                </Button>,
                <Button
                  key="extract"
                  type="link"
                  size="small"
                  icon={<RobotOutlined />}
                  style={{ padding: 0 }}
                  onClick={() => void handleReextract(file)}
                >
                  重新识别
                </Button>,
                <Popconfirm
                  key="delete"
                  title="确定删除该 MSDS 附件？"
                  disabled={!canDelete}
                  onConfirm={() => void handleMsdsDelete(file)}
                >
                  <Button type="link" size="small" danger icon={<DeleteOutlined />} style={{ padding: 0 }} disabled={!canDelete}>
                    删除
                  </Button>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={<Text style={{ color: T.charcoal }}>{file.file_name}</Text>}
                description={
                  <Text style={{ fontSize: 12, color: T.muted }}>
                    {formatSize(file.size_bytes)} · {file.created_at?.slice(0, 10)}
                  </Text>
                }
              />
            </List.Item>
          )}
        />
      </Modal>

      <Modal
        title="AI 识别结果确认"
        open={aiState.open}
        onOk={() => void applyAiSuggestion()}
        onCancel={() => setAiState({ open: false, chemical: null, aiError: null })}
        confirmLoading={aiApplying}
        okText="确认更新档案"
        width={680}
        destroyOnHidden
      >
        <Text style={{ color: T.slate, fontSize: 13 }}>
          AI 已从 MSDS 识别以下信息并填入表单（识别为空的字段保持档案原值），请核对后确认写入
          {aiState.chemical ? `「${aiState.chemical.name}」` : ''}档案。
        </Text>
        <Form<ChemicalFormValues> form={aiForm} layout="vertical" className="mt-3">
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="name" label="化学品名称" rules={[{ required: true, message: '请填写品名' }]}>
              <Input />
            </Form.Item>
            <Form.Item name="alias" label="别名/商品名">
              <Input />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="cas_no" label="CAS 号">
              <Input />
            </Form.Item>
            <Form.Item name="category" label="危险性类别" rules={[{ required: true }]}>
              <Select
                options={Object.entries(CHEMICAL_CATEGORY_LABELS).map(([value, label]) => ({
                  value,
                  label,
                }))}
              />
            </Form.Item>
          </div>
          <Form.Item name="hazard_statements" label="危险性概述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="storage_requirements" label="储存要求">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <FeishuAttachmentPreviewModal
        open={preview.open}
        fileName={preview.fileName}
        previewSrc={preview.previewSrc}
        downloadSrc={preview.downloadSrc}
        onClose={closePreview}
      />
    </div>
  )
}
