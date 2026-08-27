'use client'

import { useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Menu,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Upload,
} from 'antd'
import type { TableColumnsType } from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  FolderOutlined,
  InboxOutlined,
  PaperClipOutlined,
  PlusOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { createDocumentDepartment, createDocumentEntry, deleteDocumentDepartment, deleteDocumentEntry, importDocumentCatalogExcel, batchImportDocumentAttachments, updateDocumentDepartment, updateDocumentEntry } from '@/actions/quality'
import { fetchDocumentDepartments, fetchDocumentEntries, fetchDocumentCatalogExport, fetchDocumentEntryAttachmentContent } from '@/lib/api/client/quality'

import DocumentEntryAttachmentModal, {
  DocumentAttachmentPreviewModal,
  type AttachmentPreviewState,
} from './DocumentEntryAttachmentModal'
import type {
  DocumentDepartmentItem,
  DocumentEntryAttachment,
  DocumentEntryItem,
} from '@/types/quality'

const ALL_DEPARTMENTS_KEY = 'all'

interface EntryFormValues {
  department_id: string
  seq_no?: number | null
  name: string
  code?: string | null
  effective_date?: dayjs.Dayjs | null
}

interface DepartmentFormValues {
  name: string
  sort_order?: number
}

interface DocumentCatalogPageProps {
  initialDepartments?: DocumentDepartmentItem[]
}

export default function DocumentCatalogPage({ initialDepartments = [] }: DocumentCatalogPageProps) {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()

  const [selectedKey, setSelectedKey] = useState<string>(ALL_DEPARTMENTS_KEY)
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)

  const [entryModalOpen, setEntryModalOpen] = useState(false)
  const [editingEntry, setEditingEntry] = useState<DocumentEntryItem | null>(null)
  const [entrySaving, setEntrySaving] = useState(false)
  const [entryForm] = Form.useForm<EntryFormValues>()

  const [deptModalOpen, setDeptModalOpen] = useState(false)
  const [editingDept, setEditingDept] = useState<DocumentDepartmentItem | null>(null)
  const [deptSaving, setDeptSaving] = useState(false)
  const [deptForm] = Form.useForm<DepartmentFormValues>()

  const [importing, setImporting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [attImporting, setAttImporting] = useState(false)
  const [attachmentEntry, setAttachmentEntry] = useState<DocumentEntryItem | null>(null)
  const [attachmentModalOpen, setAttachmentModalOpen] = useState(false)
  const [preview, setPreview] = useState<AttachmentPreviewState | null>(null)

  const { data: departments = [], isLoading: deptLoading } = useQuery({
    queryKey: ['quality-documents', 'departments'],
    queryFn: fetchDocumentDepartments,
    initialData: initialDepartments.length ? initialDepartments : undefined,
  })

  const { data: entryData, isLoading: entryLoading, error: entryError } = useQuery({
    queryKey: ['quality-documents', 'entries', selectedKey, keyword, page, pageSize],
    queryFn: () =>
      fetchDocumentEntries({
        department_id: selectedKey === ALL_DEPARTMENTS_KEY ? undefined : selectedKey,
        keyword: keyword || undefined,
        page,
        page_size: pageSize,
      }),
  })

  useEffect(() => {
    if (entryError) {
      message.error('加载文件目录失败，请稍后重试')
    }
  }, [entryError, message])

  const entries = entryData?.items ?? []
  const total = entryData?.total ?? 0
  const selectedDept = departments.find((dept) => dept.id === selectedKey)

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['quality-documents'] })
  }

  const handleSelectDepartment = (key: string) => {
    setSelectedKey(key)
    setPage(1)
  }

  // ---------- 条目 ----------

  const openCreateEntry = () => {
    setEditingEntry(null)
    entryForm.resetFields()
    entryForm.setFieldsValue({
      department_id: selectedKey === ALL_DEPARTMENTS_KEY ? departments[0]?.id : selectedKey,
    })
    setEntryModalOpen(true)
  }

  const openEditEntry = (entry: DocumentEntryItem) => {
    setEditingEntry(entry)
    entryForm.setFieldsValue({
      department_id: entry.department_id,
      seq_no: entry.seq_no,
      name: entry.name,
      code: entry.code,
      effective_date: entry.effective_date ? dayjs(entry.effective_date) : null,
    })
    setEntryModalOpen(true)
  }

  const handleSaveEntry = async () => {
    let values: EntryFormValues
    try {
      values = await entryForm.validateFields()
    } catch {
      return
    }
    const payload = {
      department_id: values.department_id,
      seq_no: values.seq_no ?? null,
      name: values.name.trim(),
      code: values.code?.trim() || null,
      effective_date: values.effective_date ? values.effective_date.format('YYYY-MM-DD') : null,
    }
    setEntrySaving(true)
    try {
      if (editingEntry) {
        await updateDocumentEntry(editingEntry.id, payload)
        message.success('更新成功')
      } else {
        await createDocumentEntry(payload)
        message.success('创建成功')
      }
      setEntryModalOpen(false)
      refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败')
    } finally {
      setEntrySaving(false)
    }
  }

  const handleDeleteEntry = (entry: DocumentEntryItem) => {
    modal.confirm({
      title: '删除文件条目',
      content: `确定删除「${entry.name}」吗？`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteDocumentEntry(entry.id)
          message.success('已删除')
          refresh()
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除失败')
        }
      },
    })
  }

  // ---------- 部门 ----------

  const openCreateDept = () => {
    setEditingDept(null)
    deptForm.resetFields()
    deptForm.setFieldsValue({ sort_order: (departments.at(-1)?.sort_order ?? 0) + 1 })
    setDeptModalOpen(true)
  }

  const openEditDept = (dept: DocumentDepartmentItem) => {
    setEditingDept(dept)
    deptForm.setFieldsValue({ name: dept.name, sort_order: dept.sort_order })
    setDeptModalOpen(true)
  }

  const handleSaveDept = async () => {
    let values: DepartmentFormValues
    try {
      values = await deptForm.validateFields()
    } catch {
      return
    }
    const payload = { name: values.name.trim(), sort_order: values.sort_order ?? 0 }
    setDeptSaving(true)
    try {
      if (editingDept) {
        await updateDocumentDepartment(editingDept.id, payload)
        message.success('更新成功')
      } else {
        await createDocumentDepartment(payload)
        message.success('创建成功')
      }
      setDeptModalOpen(false)
      refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败')
    } finally {
      setDeptSaving(false)
    }
  }

  const handleDeleteDept = (dept: DocumentDepartmentItem) => {
    modal.confirm({
      title: '删除部门',
      content: `确定删除「${dept.name}」吗？该部门下的 ${dept.document_count} 条文件目录将一并删除。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteDocumentDepartment(dept.id)
          message.success('已删除')
          if (selectedKey === dept.id) setSelectedKey(ALL_DEPARTMENTS_KEY)
          refresh()
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除失败')
        }
      },
    })
  }

  // ---------- Excel/Word 导入 ----------

  const handleImportUpload = async (file: File): Promise<void> => {
    setImporting(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const result = await importDocumentCatalogExcel(formData)
      if (result) {
        message.success(`导入完成：${result.department_count} 个部门，${result.entry_count} 条文件记录`)
      }
      refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导入失败')
    } finally {
      setImporting(false)
    }
  }

  // ---------- 统一附件导入（自动识别名称/编号，失败 LLM 匹配） ----------

  const handleAttachmentImport = async (fileList: File[]) => {
    if (fileList.length === 0) return
    setAttImporting(true)
    try {
      const formData = new FormData()
      fileList.forEach((file) => formData.append('files', file))
      const result = await batchImportDocumentAttachments(formData)
      if (result) {
        const unmatched = result.results.filter((item) => !item.matched)
        if (unmatched.length === 0) {
          message.success(`附件导入完成：${result.bound} 个全部自动绑定`)
        } else {
          message.warning(
            `附件导入：成功 ${result.bound} 个，未匹配 ${unmatched.length} 个（${unmatched
              .slice(0, 3)
              .map((item) => item.file_name)
              .join('、')}${unmatched.length > 3 ? ' 等' : ''}）`
          )
        }
      }
      refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '附件导入失败')
    } finally {
      setAttImporting(false)
    }
  }

  // ---------- 导出 ----------

  const handleExport = async () => {
    if (selectedKey === ALL_DEPARTMENTS_KEY) {
      message.info('请先在左侧选择要导出的部门')
      return
    }
    setExporting(true)
    try {
      const { blob, filename } = await fetchDocumentCatalogExport(selectedKey, selectedDept?.name)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导出失败')
    } finally {
      setExporting(false)
    }
  }

  const openAttachmentManager = (entry: DocumentEntryItem) => {
    setAttachmentEntry(entry)
    setAttachmentModalOpen(true)
  }

  // ---------- 附件预览 ----------

  const openAttachmentPreview = async (entryId: string, attachment: DocumentEntryAttachment) => {
    setPreview({ attachment, text: '', blobUrl: '', contentType: '', loading: true })
    try {
      const content = await fetchDocumentEntryAttachmentContent(entryId, attachment.storage_key)
      setPreview({ attachment, ...content, loading: false })
    } catch (error) {
      message.error(error instanceof Error ? error.message : '预览失败')
      setPreview(null)
    }
  }

  // ---------- 渲染 ----------

  const menuItems = [
    { key: ALL_DEPARTMENTS_KEY, label: '全部部门' },
    ...departments.map((dept) => ({ key: dept.id, label: dept.name })),
  ]

  const columns: TableColumnsType<DocumentEntryItem> = [
    {
      title: '序号',
      dataIndex: 'seq_no',
      width: 70,
      render: (value: number | null, _record: DocumentEntryItem, index: number) =>
        value ?? index + 1,
    },
    {
      title: '文件名称',
      dataIndex: 'name',
      ellipsis: { showTitle: false },
      render: (value: string) => (
        <Tooltip title={value} placement="topLeft">
          {value}
        </Tooltip>
      ),
    },
    { title: '文件编码', dataIndex: 'code', width: 200, render: (value: string | null) => value || '-' },
    {
      title: '生效日期',
      dataIndex: 'effective_date',
      width: 120,
      render: (_: unknown, record: DocumentEntryItem) =>
        record.effective_date || record.effective_date_text || '-',
    },
    ...(selectedKey === ALL_DEPARTMENTS_KEY
      ? [
          {
            title: '所属部门',
            dataIndex: 'department_id',
            width: 160,
            ellipsis: true,
            render: (value: string) => departments.find((dept) => dept.id === value)?.name ?? '-',
          } as TableColumnsType<DocumentEntryItem>[number],
        ]
      : []),
    {
      title: '附件',
      key: 'attachments',
      width: 160,
      render: (_: unknown, record: DocumentEntryItem) => {
        const attachments = record.attachments ?? []
        if (attachments.length === 0) return <span className="text-gray-300">-</span>
        const shown = attachments.slice(0, 2)
        return (
          <Space size={4} wrap>
            {shown.map((att) => (
              <Tag
                key={att.storage_key}
                color="blue"
                className="cursor-pointer"
                onClick={() => openAttachmentPreview(record.id, att)}
              >
                <PaperClipOutlined className="mr-1" />
                {att.file_name.length > 12 ? `${att.file_name.slice(0, 12)}…` : att.file_name}
              </Tag>
            ))}
            {attachments.length > 2 && (
              <Button type="link" size="small" onClick={() => openAttachmentManager(record)}>
                +{attachments.length - 2}
              </Button>
            )}
            {attachments.length > 0 && (
              <Button type="link" size="small" onClick={() => openAttachmentManager(record)}>
                管理
              </Button>
            )}
          </Space>
        )
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, record: DocumentEntryItem) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => openEditEntry(record)}>
            编辑
          </Button>
          <Button type="link" size="small" danger onClick={() => handleDeleteEntry(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div className="flex h-full min-h-[calc(100vh-120px)] gap-4">
      <Card
        size="small"
        title={
          <span>
            <FolderOutlined className="mr-2" />
            部门分类
          </span>
        }
        extra={
          <Button type="link" size="small" icon={<PlusOutlined />} onClick={openCreateDept}>
            新增
          </Button>
        }
        className="!w-72 shrink-0 overflow-auto"
        loading={deptLoading && departments.length === 0}
      >
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => handleSelectDepartment(key)}
          className="!border-e-0"
        />
      </Card>

      <Card
        size="small"
        title={
          selectedDept ? (
            <Space size={4}>
              <span>{selectedDept.name}</span>
              <Tag className="!mr-0">{selectedDept.document_count}</Tag>
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={() => openEditDept(selectedDept)}
              />
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => handleDeleteDept(selectedDept)}
              />
            </Space>
          ) : (
            '全部部门'
          )
        }
        extra={
          <Space>
            <Input.Search
              placeholder="搜索文件名称 / 编码"
              allowClear
              style={{ width: 240 }}
              onSearch={(value) => {
                setKeyword(value.trim())
                setPage(1)
              }}
            />
            <Upload
              accept=".docx,.doc,.xls,.xlsx"
              multiple
              showUploadList={false}
              beforeUpload={(file) => {
                handleImportUpload(file)
                return false
              }}
            >
              <Button icon={<UploadOutlined />} loading={importing}>
                导入文件目录
              </Button>
            </Upload>
            <Upload
              accept=".doc,.docx,.pdf,.png,.jpg,.jpeg,.md"
              multiple
              showUploadList={false}
              beforeUpload={(file, all) => {
                if (file === all[0]) {
                  handleAttachmentImport(all as unknown as File[])
                }
                return false
              }}
            >
              <Button icon={<PaperClipOutlined />} loading={attImporting}>
                导入附件
              </Button>
            </Upload>
            <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
              导出
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateEntry}>
              新增条目
            </Button>
          </Space>
        }
        className="flex-1 overflow-hidden [&_.ant-card-body]:h-[calc(100%-46px)] [&_.ant-card-body]:overflow-auto"
      >
        <Table<DocumentEntryItem>
          rowKey="id"
          size="small"
          loading={entryLoading}
          columns={columns}
          dataSource={entries}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (value) => `共 ${value} 条`,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage)
              setPageSize(nextPageSize)
            },
          }}
          locale={{ emptyText: <InboxOutlined className="text-3xl text-gray-300" /> }}
        />
      </Card>

      <Modal
        title={editingEntry ? '编辑文件条目' : '新增文件条目'}
        open={entryModalOpen}
        onOk={handleSaveEntry}
        confirmLoading={entrySaving}
        onCancel={() => setEntryModalOpen(false)}
        destroyOnHidden
      >
        <Form form={entryForm} layout="vertical" className="mt-4">
          <Form.Item
            name="department_id"
            label="所属部门"
            rules={[{ required: true, message: '请选择所属部门' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={departments.map((dept) => ({ value: dept.id, label: dept.name }))}
            />
          </Form.Item>
          <Form.Item
            name="name"
            label="文件名称"
            rules={[{ required: true, message: '请输入文件名称' }]}
          >
            <Input placeholder="如：201一车间人员进出洁净区管理程序" maxLength={500} />
          </Form.Item>
          <div className="grid grid-cols-2 gap-4">
            <Form.Item name="code" label="文件编码">
              <Input placeholder="如：SMP-XT1-002/07" maxLength={255} />
            </Form.Item>
            <Form.Item name="seq_no" label="序号">
              <InputNumber min={1} precision={0} className="!w-full" placeholder="序号" />
            </Form.Item>
          </div>
          <Form.Item name="effective_date" label="生效日期">
            <DatePicker className="!w-full" format="YYYY-MM-DD" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingDept ? '重命名部门' : '新增部门'}
        open={deptModalOpen}
        onOk={handleSaveDept}
        confirmLoading={deptSaving}
        onCancel={() => setDeptModalOpen(false)}
        destroyOnHidden
      >
        <Form form={deptForm} layout="vertical" className="mt-4">
          <Form.Item
            name="name"
            label="部门名称"
            rules={[{ required: true, message: '请输入部门名称' }]}
          >
            <Input placeholder="如：QA、SC-101一车间" maxLength={255} />
          </Form.Item>
          <Form.Item name="sort_order" label="排序序号">
            <InputNumber min={0} precision={0} className="!w-full" />
          </Form.Item>
        </Form>
      </Modal>

      <DocumentEntryAttachmentModal
        open={attachmentModalOpen}
        entry={entries.find((item) => item.id === attachmentEntry?.id) ?? attachmentEntry}
        onClose={() => setAttachmentModalOpen(false)}
        onChanged={refresh}
        onPreview={(att) => attachmentEntry && openAttachmentPreview(attachmentEntry.id, att)}
      />

      <DocumentAttachmentPreviewModal preview={preview} onClose={() => setPreview(null)} />
    </div>
  )
}
