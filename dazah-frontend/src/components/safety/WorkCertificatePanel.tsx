'use client'

/**
 * 人员特殊作业证件管理面板：到期统计卡 + 筛选列表 + 新建/编辑
 * （附件上传 → AI 识别建议 → 人工确认回填，参照 MSDS 流程）。
 * 支持 ?cert=<id> 深链打开详情抽屉（作业票人员证件跳转入口）。
 */

import {
  WORK_CERTIFICATES_PAGE_KEY,
  certificateFileContentUrl,
  certificateFilePreviewUrl,
} from '@/lib/work-permit-api'

import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  Card,
  DatePicker,
  Drawer,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import dayjs from 'dayjs'
import { ImportOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { UploadFile } from 'antd/es/upload/interface'

import WorkCertificateImportModal from '@/components/safety/WorkCertificateImportModal'

import {
  createWorkCertificate,
  deleteWorkCertificate,
  getCertificateCategories,
  getCertificateExpirySummary,
  getWorkCertificates,
  updateWorkCertificate,
  uploadWorkCertificateFile,
} from '@/actions/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import PlatformNotice from '@/components/shared/PlatformNotice'

type CertificateRow = {
  id: string
  person_name: string
  department: string | null
  certificate_category: string
  certificate_category_label: string
  certificate_no: string | null
  issuing_authority: string | null
  issue_date: string | null
  expiry_date: string | null
  qualification_scope: string | null
  status: string
  files: { id: string; file_name: string }[]
  days_to_expiry: number | null
}

type SummaryShape = {
  total: number
  valid: number
  expiring_in_30d: number
  expired: number
}

const STATUS_META: Record<string, { label: string; color: string }> = {
  valid: { label: '有效', color: 'green' },
  expiring: { label: '即将到期', color: 'orange' },
  expired: { label: '已过期', color: 'red' },
  revoked: { label: '已吊销', color: 'default' },
}

export function WorkCertificatePanel({
  initialList,
  initialSummary,
  initialError,
  highlightCertId,
}: {
  initialList: { items: CertificateRow[]; total: number } | null
  initialSummary: SummaryShape | null
  initialError: string | null
  highlightCertId?: string | null
}) {
  const permissions = usePagePermissions(WORK_CERTIFICATES_PAGE_KEY)
  const [items, setItems] = useState<CertificateRow[]>(initialList?.items ?? [])
  const [total, setTotal] = useState(initialList?.total ?? 0)
  const [summary, setSummary] = useState<SummaryShape | null>(initialSummary)
  const [error, setError] = useState<string | null>(initialError)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [category, setCategory] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [keyword, setKeyword] = useState<string | null>(null)
  const [categories, setCategories] = useState<{ [key: string]: string }[]>([])
  const [editorOpen, setEditorOpen] = useState(false)
  const [detail, setDetail] = useState<CertificateRow | null>(
    highlightCertId
      ? (initialList?.items ?? []).find((item) => item.id === highlightCertId) ?? null
      : null
  )
  const [editing, setEditing] = useState<CertificateRow | null>(null)
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [aiSuggestion, setAiSuggestion] = useState<Record<
    string,
    unknown
  > | null>(null)
  const [aiError, setAiError] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)

  const load = useCallback(
    async (targetPage = page) => {
      setLoading(true)
      const [listRes, summaryRes] = await Promise.all([
        getWorkCertificates({
          pageKey: WORK_CERTIFICATES_PAGE_KEY,
          page: targetPage,
          certificateCategory: category,
          status,
          keyword,
        }),
        getCertificateExpirySummary(WORK_CERTIFICATES_PAGE_KEY),
      ])
      if (listRes.code === 200 && listRes.data) {
        setItems(listRes.data.items as never)
        setTotal(listRes.data.total)
        setError(null)
      } else {
        setError(listRes.message ?? '加载失败')
      }
      if (summaryRes.code === 200 && summaryRes.data) setSummary(summaryRes.data)
      setLoading(false)
    },
    [page, category, status, keyword]
  )

  useEffect(() => {
    void getCertificateCategories(WORK_CERTIFICATES_PAGE_KEY).then((res) => {
      if (res.code === 200 && res.data)
        setCategories(res.data.categories as never)
    })
    if (!initialList) {
      const timer = setTimeout(() => void load(1), 0)
      return () => clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const openCreate = useCallback(() => {
    setEditing(null)
    setAiSuggestion(null)
    setAiError(null)
    form.resetFields()
    setEditorOpen(true)
  }, [form])

  const openEdit = useCallback(
    (record: CertificateRow) => {
      setEditing(record)
      setAiSuggestion(null)
      setAiError(null)
      form.setFieldsValue({
        person_name: record.person_name,
        department: record.department,
        certificate_category: record.certificate_category,
        certificate_no: record.certificate_no,
        issuing_authority: record.issuing_authority,
        issue_date: record.issue_date ? dayjs(record.issue_date) : null,
        expiry_date: record.expiry_date ? dayjs(record.expiry_date) : null,
        qualification_scope: record.qualification_scope,
      })
      setEditorOpen(true)
    },
    [form]
  )

  const handleUpload = useCallback(
    async (file: UploadFile) => {
      if (!file.originFileObj) return
      setUploading(true)
      const response = await uploadWorkCertificateFile(
        editing?.id ?? '',
        file.originFileObj
      )
      setUploading(false)
      if (response.code !== 200 || !response.data) {
        message.error(response.message ?? '上传失败')
        return
      }
      const suggestion = response.data.ai_suggestion
      if (suggestion) {
        setAiSuggestion(suggestion as unknown as Record<string, unknown>)
        setAiError(null)
        form.setFieldsValue({
          person_name: suggestion.person_name ?? form.getFieldValue('person_name'),
          certificate_category:
            suggestion.certificate_category ??
            form.getFieldValue('certificate_category'),
          certificate_no: suggestion.certificate_no ?? form.getFieldValue('certificate_no'),
          issuing_authority:
            suggestion.issuing_authority ?? form.getFieldValue('issuing_authority'),
          issue_date: suggestion.issue_date
            ? dayjs(String(suggestion.issue_date))
            : form.getFieldValue('issue_date'),
          expiry_date: suggestion.expiry_date
            ? dayjs(String(suggestion.expiry_date))
            : form.getFieldValue('expiry_date'),
          qualification_scope:
            suggestion.qualification_scope ?? form.getFieldValue('qualification_scope'),
        })
        setConfirmOpen(true)
        message.success('AI 识别完成，请核对并确认回填内容')
      } else {
        setAiError(response.data.ai_error ?? '未能识别证件内容')
        message.warning(response.data.ai_error ?? '未能识别证件内容，请手动填写')
      }
    },
    [editing, form]
  )

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields()
    const payload: Record<string, unknown> = {
      person_name: values.person_name,
      department: values.department ?? null,
      certificate_category: values.certificate_category,
      certificate_no: values.certificate_no ?? null,
      issuing_authority: values.issuing_authority ?? null,
      issue_date: values.issue_date ? values.issue_date.format('YYYY-MM-DD') : null,
      expiry_date: values.expiry_date ? values.expiry_date.format('YYYY-MM-DD') : null,
      qualification_scope: values.qualification_scope ?? null,
    }
    setSaving(true)
    const response = editing
      ? await updateWorkCertificate(editing.id, payload)
      : await createWorkCertificate(payload)
    setSaving(false)
    if (response.code !== 200) {
      message.error(response.message ?? '保存失败')
      return
    }
    message.success(editing ? '证件已更新' : '证件已创建')
    setEditorOpen(false)
    await load(page)
  }, [form, editing, load, page])

  const columns: ColumnsType<CertificateRow> = [
    {
      title: '姓名',
      dataIndex: 'person_name',
      width: 110,
      render: (value: string, record) => (
        <a
          onClick={() => setDetail(record)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') setDetail(record)
          }}
        >
          {value}
        </a>
      ),
    },
    { title: '证件类别', dataIndex: 'certificate_category_label', width: 150 },
    { title: '证件号', dataIndex: 'certificate_no', width: 150, render: (v: string | null) => v ?? '-' },
    {
      title: '有效期至',
      dataIndex: 'expiry_date',
      width: 120,
      render: (value: string | null, record) => (
        <Space size={4}>
          {value ?? '-'}
          {record.status === 'expiring' && <Tag color="orange">{record.days_to_expiry}天</Tag>}
          {record.status === 'expired' && <Tag color="red">已过期</Tag>}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value: string) => (
        <Tag color={STATUS_META[value]?.color ?? 'default'}>
          {STATUS_META[value]?.label ?? value}
        </Tag>
      ),
    },
    {
      title: '附件',
      dataIndex: 'files',
      render: (files: CertificateRow['files'], record) =>
        (files ?? []).length === 0
          ? '-'
          : files.map((file) => (
              <a
                key={file.id}
                href={certificateFilePreviewUrl(record.id, file.id)}
                target="_blank"
                rel="noreferrer"
                style={{ marginRight: 8 }}
              >
                {file.file_name}
              </a>
            )),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, record) => (
        <Space size={8}>
          <a onClick={() => openEdit(record)}>编辑</a>
          {permissions.canDelete && (
            <Popconfirm
              title="确认删除该证件？"
              onConfirm={async () => {
                await deleteWorkCertificate(record.id)
                message.success('已删除')
                await load(page)
              }}
            >
              <a style={{ color: 'var(--ant-color-error)' }}>删除</a>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      {!permissions.canAccess && (
        <PlatformNotice
          type="warning"
          message="无权访问证件管理页面"
          description="请联系管理员授予「特种作业证件」页面权限。"
        />
      )}
      {error && (
        <PlatformNotice
          type="error"
          message="证件列表加载失败"
          description={error}
          action={<Button size="small" onClick={() => void load(page)}>重试</Button>}
        />
      )}
      <Card size="small">
        <Space wrap size={16}>
          <Button onClick={() => { setStatus(null); setPage(1); void load(1) }}>
            全部：{summary?.total ?? 0}
          </Button>
          <Button
            onClick={() => { setStatus('expiring'); setPage(1); void load(1) }}
            type={status === 'expiring' ? 'primary' : 'default'}
          >
            30天内到期：{summary?.expiring_in_30d ?? 0}
          </Button>
          <Button
            danger
            onClick={() => { setStatus('expired'); setPage(1); void load(1) }}
            type={status === 'expired' ? 'primary' : 'default'}
          >
            已过期：{summary?.expired ?? 0}
          </Button>
        </Space>
      </Card>
      <Card size="small">
        <Space wrap>
          <Select
            allowClear
            placeholder="证件类别"
            style={{ width: 190 }}
            value={category}
            options={categories}
            onChange={(value) => {
              setCategory(value ?? null)
              setPage(1)
            }}
          />
          <Input.Search
            allowClear
            placeholder="姓名/证件号/部门"
            style={{ width: 220 }}
            onSearch={(value) => {
              setKeyword(value || null)
              setPage(1)
              void load(1)
            }}
          />
          <Button onClick={() => void load(page)}>刷新</Button>
          {permissions.canOperate && (
            <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>
              Excel 导入
            </Button>
          )}
          {permissions.canOperate && (
            <Button type="primary" onClick={openCreate}>
              新建证件
            </Button>
          )}
        </Space>
      </Card>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          showSizeChanger: false,
          showTotal: (value) => `共 ${value} 条`,
          onChange: (next) => {
            setPage(next)
            void load(next)
          },
        }}
        scroll={{ x: 'max-content' }}
      />

      <WorkCertificateImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => void load(1)}
      />

      <Drawer
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        size={560}
        destroyOnHidden
        title={editing ? `编辑证件：${editing.person_name}` : '新建证件'}
        footer={
          <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button onClick={() => setEditorOpen(false)}>取消</Button>
            <Button type="primary" loading={saving} onClick={() => void handleSubmit()}>
              保存
            </Button>
          </Space>
        }
      >
        {editing && (
          <>
            <Typography.Paragraph type="secondary">
              上传证件扫描件（pdf/png/jpg）后 AI 自动识别证件号、姓名、类别与有效期，
              识别结果需人工确认后回填。
            </Typography.Paragraph>
            <Upload
              accept=".pdf,.png,.jpg,.jpeg"
              showUploadList={false}
              beforeUpload={() => false}
              onChange={({ file }) => {
                if (file.originFileObj) void handleUpload(file)
              }}
            >
              <Button loading={uploading}>上传证件附件并识别</Button>
            </Upload>
            <div style={{ marginTop: 8 }}>
              {(editing.files ?? []).map((file) => (
                <a
                  key={file.id}
                  href={certificateFileContentUrl(editing.id, file.id)}
                  target="_blank"
                  rel="noreferrer"
                  style={{ marginRight: 12 }}
                >
                  {file.file_name}
                </a>
              ))}
            </div>
          </>
        )}
        {!editing && (
          <Typography.Paragraph type="secondary">
            请先保存证件基础信息，再上传附件进行 AI 识别（识别结果仅作建议，需人工确认）。
          </Typography.Paragraph>
        )}
        {aiError && (
          <PlatformNotice type="warning" message="AI 识别未成功" description={aiError} />
        )}
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item label="持证人姓名" name="person_name" rules={[{ required: true }]}>
            <Input placeholder="姓名" />
          </Form.Item>
          <Form.Item label="证件类别" name="certificate_category" rules={[{ required: true }]}>
            <Select options={categories} placeholder="选择类别" />
          </Form.Item>
          <Form.Item label="证件号" name="certificate_no">
            <Input placeholder="证件号" />
          </Form.Item>
          <Form.Item label="发证机关" name="issuing_authority">
            <Input placeholder="发证机关" />
          </Form.Item>
          <Space wrap>
            <Form.Item label="发证日期" name="issue_date">
              <DatePicker style={{ width: 160 }} />
            </Form.Item>
            <Form.Item label="有效期至" name="expiry_date">
              <DatePicker style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Form.Item label="准操项目/资质范围" name="qualification_scope">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item label="所属部门" name="department">
            <Input placeholder="部门（选填）" />
          </Form.Item>
        </Form>
      </Drawer>

      <Drawer
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        size={420}
        title={detail ? `${detail.person_name} 的证件` : ''}
      >
        {detail && (
          <Spin spinning={false}>
            <Typography.Paragraph>
              类别：{detail.certificate_category_label}
              <br />
              证件号：{detail.certificate_no ?? '-'}
              <br />
              有效期至：{detail.expiry_date ?? '-'}
              <br />
              状态：
              <Tag color={STATUS_META[detail.status]?.color ?? 'default'}>
                {STATUS_META[detail.status]?.label ?? detail.status}
              </Tag>
            </Typography.Paragraph>
            {(detail.files ?? []).map((file) => (
              <a
                key={file.id}
                href={certificateFilePreviewUrl(detail.id, file.id)}
                target="_blank"
                rel="noreferrer"
                style={{ marginRight: 12 }}
              >
                预览 {file.file_name}
              </a>
            ))}
          </Spin>
        )}
      </Drawer>

      <Modal
        open={confirmOpen}
        title="确认 AI 识别结果"
        onCancel={() => setConfirmOpen(false)}
        onOk={() => {
          setConfirmOpen(false)
          message.success('识别内容已回填表单，请核对后保存')
        }}
        okText="已核对"
      >
        <pre style={{ maxHeight: 240, overflow: 'auto', fontSize: 12 }}>
          {JSON.stringify(aiSuggestion, null, 2)}
        </pre>
      </Modal>
    </Space>
  )
}
