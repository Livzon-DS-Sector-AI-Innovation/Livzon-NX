'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  App, AutoComplete, Button, DatePicker, Form, Image, Input, Modal, Popconfirm,
  Select, Space, Table, Tag, Typography, Upload,
} from 'antd'
import {
  DeleteOutlined, EyeOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, UploadOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  fetchOnboardingList,
  fetchOnboardingById,
  fetchOnboardingAttachmentContent,
  fetchDepartments,
  fetchJobPostings,
} from '@/lib/api/client/hr'
import {
  updateOnboardingAction,
  deleteOnboardingAction,
  uploadOnboardingAttachmentAction,
} from '@/actions/hr'
import OnboardingAttachmentPreviewModal from './OnboardingAttachmentPreviewModal'

// 新增入口：飞书多维「入职信息表」公开表单
const ONBOARDING_FORM_URL = 'https://j0eukrlohu.feishu.cn/share/base/form/shrcnds8SEIlMXMdB3qS9QzWlth'

const ATTACHMENT_FIELDS = [
  { key: 'resignation_attachment', label: '离职证明附件' },
  { key: 'id_attachment', label: '身份信息附件' },
  { key: 'education_attachment', label: '学历证书附件' },
  { key: 'other_attachment', label: '其他附件' },
] as const

type AttachmentFieldKey = (typeof ATTACHMENT_FIELDS)[number]['key']

interface AttachmentItem {
  file_token?: string
  name?: string
  type?: string
  size?: number
  url?: string
}

interface OnboardingRecord {
  id: string
  name?: string
  onboard_date?: string
  department?: string
  level?: string
  resignation_attachment?: AttachmentItem[]
  id_attachment?: AttachmentItem[]
  education_attachment?: AttachmentItem[]
  other_attachment?: AttachmentItem[]
}

const IMAGE_EXT = /\.(png|jpe?g|gif|webp|bmp|svg)$/i
const ONLINE_PREVIEW_EXT = /\.(pdf|docx?|xlsx?|csv)$/i

export default function OnboardingManagementPage() {
  const { message } = App.useApp()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<OnboardingRecord | null>(null)
  const [saving, setSaving] = useState(false)
  const [imagePreview, setImagePreview] = useState<{ url: string; open: boolean }>({ url: '', open: false })
  const [previewFile, setPreviewFile] = useState<{ open: boolean; fileName: string; blob: Blob | null }>({
    open: false,
    fileName: '',
    blob: null,
  })
  const [draftAttachments, setDraftAttachments] = useState<Record<AttachmentFieldKey, AttachmentItem[]>>({
    resignation_attachment: [],
    id_attachment: [],
    education_attachment: [],
    other_attachment: [],
  })
  const [form] = Form.useForm()

  const { data: listData, isLoading, refetch } = useQuery({
    queryKey: ['onboarding-list', page, pageSize, keyword],
    queryFn: () => fetchOnboardingList({ keyword: keyword || undefined, page, page_size: pageSize }),
  })

  const { data: deptData } = useQuery({
    queryKey: ['hr-departments'],
    queryFn: () => fetchDepartments({ page_size: 200 }),
  })
  const departmentOptions = useMemo(
    () => (deptData?.data || []).map((d: { name: string }) => ({ value: d.name, label: d.name })),
    [deptData],
  )

  const { data: jobData } = useQuery({
    queryKey: ['hr-job-postings'],
    queryFn: () => fetchJobPostings({ page_size: 200 }),
  })
  const positionOptions = useMemo(
    () => (jobData?.data || []).map((j: { title: string }) => ({ value: j.title, label: j.title })),
    [jobData],
  )

  const records: OnboardingRecord[] = listData?.data || []
  const total = listData?.meta?.total ?? 0

  // 打开附件：图片内嵌预览；PDF/DOCX/XLSX 在线预览弹窗；其余新标签打开（后端代理下载）
  const openAttachment = async (recordId: string, att: AttachmentItem) => {
    const name = att.name || 'attachment'
    if (!att.file_token) {
      if (att.url) {
        window.open(att.url, '_blank')
        return
      }
      message.warning('附件无下载地址')
      return
    }
    try {
      const blob = await fetchOnboardingAttachmentContent(recordId, att.file_token)
      if (IMAGE_EXT.test(name)) {
        const url = URL.createObjectURL(blob)
        setImagePreview({ url, open: true })
      } else if (ONLINE_PREVIEW_EXT.test(name)) {
        setPreviewFile({ open: true, fileName: name, blob })
      } else {
        const url = URL.createObjectURL(blob)
        window.open(url, '_blank')
      }
    } catch (e) {
      message.error(e.message || '附件预览失败')
    }
  }

  const handleEdit = async (record: OnboardingRecord) => {
    try {
      const detail = (await fetchOnboardingById(record.id))?.data || record
      setEditing(detail)
      form.setFieldsValue({
        name: detail.name,
        onboard_date: detail.onboard_date ? dayjs(detail.onboard_date) : null,
        department: detail.department,
        level: detail.level,
      })
      const drafts: Record<AttachmentFieldKey, AttachmentItem[]> = {
        resignation_attachment: detail.resignation_attachment || [],
        id_attachment: detail.id_attachment || [],
        education_attachment: detail.education_attachment || [],
        other_attachment: detail.other_attachment || [],
      }
      setDraftAttachments(drafts)
      setModalOpen(true)
    } catch (e) {
      message.error(e.message || '加载详情失败')
    }
  }

  const handleSave = async () => {
    if (!editing) return
    try {
      const values = await form.validateFields()
      setSaving(true)
      const payload: Record<string, unknown> = {
        name: values.name || undefined,
        onboard_date: values.onboard_date ? values.onboard_date.format('YYYY-MM-DD') : undefined,
        department: values.department || undefined,
        level: values.level || undefined,
      }
      for (const f of ATTACHMENT_FIELDS) {
        payload[f.key] = draftAttachments[f.key]
      }
      await updateOnboardingAction(editing.id, payload)
      message.success('保存成功')
      setModalOpen(false)
      refetch()
    } catch (e) {
      if (e?.message) message.error(e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (record: OnboardingRecord) => {
    try {
      await deleteOnboardingAction(record.id)
      message.success('删除成功')
      refetch()
    } catch (e) {
      message.error(e.message || '删除失败')
    }
  }

  const handleUpload = async (fieldKey: AttachmentFieldKey, file: File) => {
    try {
      const res = await uploadOnboardingAttachmentAction(file)
      setDraftAttachments((prev) => ({
        ...prev,
        [fieldKey]: [...prev[fieldKey], { file_token: res.file_token, name: res.name }],
      }))
    } catch (e) {
      message.error(e.message || '上传失败')
    }
  }

  const handleRemoveAttachment = (fieldKey: AttachmentFieldKey, index: number) => {
    setDraftAttachments((prev) => ({
      ...prev,
      [fieldKey]: prev[fieldKey].filter((_, i) => i !== index),
    }))
  }

  const attachmentColumns = ATTACHMENT_FIELDS.map((field) => ({
    title: field.label,
    key: field.key,
    width: 160,
    render: (_: unknown, record: OnboardingRecord) => {
      const atts = record[field.key] || []
      if (atts.length === 0) return <Typography.Text type="secondary">-</Typography.Text>
      return (
        <Space size={4} wrap>
          {atts.map((att, idx) => (
            <Tag
              key={att.file_token || idx}
              icon={<EyeOutlined />}
              color="blue"
              style={{ cursor: 'pointer' }}
              onClick={() => openAttachment(record.id, att)}
            >
              {att.name || '附件'}
            </Tag>
          ))}
        </Space>
      )
    },
  }))

  const columns = [
    { title: '姓名', dataIndex: 'name', key: 'name', width: 120, render: (v: string) => v || '-' },
    { title: '入职日期', dataIndex: 'onboard_date', key: 'onboard_date', width: 120, render: (v: string) => v || '-' },
    { title: '入职部门', dataIndex: 'department', key: 'department', width: 160, render: (v: string) => v || '-' },
    { title: '岗位', dataIndex: 'level', key: 'level', width: 180, render: (v: string) => v || '-' },
    ...attachmentColumns,
    {
      title: '操作',
      key: 'action',
      width: 130,
      render: (_: unknown, record: OnboardingRecord) => (
        <Space>
          <Button size="small" onClick={() => handleEdit(record)}>编辑</Button>
          <Popconfirm
            title="确认删除该入职记录？"
            description="将从飞书多维表格删除，不可恢复。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => handleDelete(record)}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">入职台账</h1>
        <Space>
          <Input
            placeholder="搜索姓名"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onPressEnter={() => { setKeyword(searchInput); setPage(1) }}
            prefix={<SearchOutlined />}
            className="w-48"
            allowClear
          />
          <Button icon={<ReloadOutlined />} onClick={() => refetch()}>刷新</Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => window.open(ONBOARDING_FORM_URL, '_blank', 'noopener,noreferrer')}
          >
            新增
          </Button>
        </Space>
      </div>

      <Table
        rowKey="id"
        loading={isLoading}
        columns={columns}
        dataSource={records}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
        locale={{ emptyText: '暂无入职记录' }}
        scroll={{ x: 1250 }}
      />

      <Modal
        title={`编辑入职信息 - ${editing?.name || ''}`}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSave}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        width={720}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 8 }}>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
              <Input placeholder="姓名" />
            </Form.Item>
            <Form.Item name="onboard_date" label="入职日期">
              <DatePicker style={{ width: '100%' }} placeholder="选择入职日期" />
            </Form.Item>
            <Form.Item name="department" label="入职部门">
              <Select
                showSearch
                allowClear
                placeholder="选择或输入部门"
                options={departmentOptions}
                filterOption={(input, option) =>
                  (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                }
              />
            </Form.Item>
            <Form.Item name="level" label="岗位">
              <AutoComplete
                allowClear
                placeholder="选择或输入岗位"
                options={positionOptions}
                filterOption={(input, option) =>
                  (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                }
              />
            </Form.Item>
          </div>

          {ATTACHMENT_FIELDS.map((field) => (
            <Form.Item key={field.key} label={field.label}>
              <Space direction="vertical" style={{ width: '100%' }} size={4}>
                {(draftAttachments[field.key] || []).map((att, idx) => (
                  <Space key={att.file_token || idx}>
                    <Typography.Link onClick={() => editing && openAttachment(editing.id, att)}>
                      {att.name || '附件'}
                    </Typography.Link>
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => handleRemoveAttachment(field.key, idx)}
                    />
                  </Space>
                ))}
                <Upload
                  showUploadList={false}
                  beforeUpload={(file) => {
                    handleUpload(field.key, file as File)
                    return false
                  }}
                >
                  <Button size="small" icon={<UploadOutlined />}>上传附件</Button>
                </Upload>
              </Space>
            </Form.Item>
          ))}
        </Form>
      </Modal>

      {imagePreview.url && (
        <Image
          alt=""
          style={{ display: 'none' }}
          src={imagePreview.url}
          preview={{
            open: imagePreview.open,
            onOpenChange: (v) => {
              if (!v) setImagePreview((p) => ({ ...p, open: false }))
            },
          }}
        />
      )}

      <OnboardingAttachmentPreviewModal
        open={previewFile.open}
        fileName={previewFile.fileName}
        blob={previewFile.blob}
        onClose={() => setPreviewFile({ open: false, fileName: '', blob: null })}
      />
    </div>
  )
}
