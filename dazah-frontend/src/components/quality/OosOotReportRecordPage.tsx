'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import dayjs from 'dayjs'
import { App, Avatar, Button, Card, Drawer, Form, Input, Input as AntInput, Modal, Popconfirm, Select, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { pullOosOotReportRecords, updateOosOotReportRecord, deleteOosOotReportRecord } from '@/actions/quality'
import { fetchOosOotReportRecords, fetchDepartmentContacts, fetchQualityFeishuAppSettings } from '@/lib/api/client/quality'
import type { DepartmentContact, OosOotReportRecordItem } from '@/types/quality'

interface FormValues {
  content: string
  product_name: string
  batch_number: string
  report_department: string
  reporter: string
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm:ss') : value
}

function formatBoolean(value: boolean | null | undefined): string {
  if (value === null || value === undefined) return '-'
  return value ? '是' : '否'
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function renderPerson(
  persons: Array<{ name?: string; avatar_url?: string; id?: string }> | null | undefined,
  fallbackName: string | null | undefined
) {
  const list = persons?.length ? persons : fallbackName ? [{ name: fallbackName }] : []
  if (list.length === 0) return <span>-</span>
  return (
    <Space size={4} wrap>
      {list.map((person, index) => (
        <span key={index} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <Avatar size={20} src={person.avatar_url || undefined}>
            {person.name?.slice(0, 1) || '?'}
          </Avatar>
          <span>{person.name || '-'}</span>
        </span>
      ))}
    </Space>
  )
}

export default function OosOotReportRecordPage() {
  const { message } = App.useApp()
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [filterReportDept, setFilterReportDept] = useState<string | undefined>()
  const [filterReporter, setFilterReporter] = useState<string | undefined>()
  const [filterProductName, setFilterProductName] = useState<string | undefined>()
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRecord, setEditingRecord] = useState<OosOotReportRecordItem | null>(null)
  const [form] = Form.useForm<FormValues>()
  const [contacts, setContacts] = useState<DepartmentContact[]>([])
  const [stepDept, setStepDept] = useState<string | undefined>(undefined)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerRecord, setDrawerRecord] = useState<OosOotReportRecordItem | null>(null)

  const queryClient = useQueryClient()

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-oos-oot', 'report-records'],
    queryFn: () => fetchOosOotReportRecords({ page: 1, page_size: 100 }),
  })

  const { data: appSettings } = useQuery({
    queryKey: ['quality-feishu-settings', 'app'],
    queryFn: fetchQualityFeishuAppSettings,
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载OOS/OOT报告记录失败'))
    }
  }, [error, message])

  const items = useMemo<OosOotReportRecordItem[]>(() => data?.data ?? [], [data?.data])

  const loadContacts = useCallback(async () => {
    try {
      const list = await fetchDepartmentContacts()
      setContacts(list)
    } catch {
      // contacts load silently
    }
  }, [])

  useEffect(() => { void loadContacts() }, [loadContacts])

  // 部门列表（去重）
  const departmentOptions = useMemo(() => {
    const depts = [...new Set(contacts.map((c) => c.department).filter(Boolean))]
    return depts.map((d) => ({ label: d!, value: d! }))
  }, [contacts])

  // 人员列表，按部门过滤
  const reporterOptions = useMemo(() => {
    let filtered = contacts
    if (stepDept) {
      filtered = contacts.filter((c) => c.department === stepDept)
    }
    return filtered
      .filter((c) => c.name)
      .map((c) => ({ label: c.name!, value: (c as any).bitable_user_id || c.open_id || c.name! }))
  }, [contacts, stepDept])

  const reportDeptOptions = useMemo(() => {
    const vals = [...new Set(items.map(i => i.report_department).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const reporterOptions2 = useMemo(() => {
    const vals = [...new Set(items.map(i => i.reporter).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const productNameOptions = useMemo(() => {
    const vals = [...new Set(items.map(i => i.product_name).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result: any = await pullOosOotReportRecords()
      message.success(`从飞书拉取完成：成功 ${result?.synced ?? 0} 条，失败 ${result?.failed ?? 0} 条`)
      queryClient.invalidateQueries({ queryKey: ['quality-oos-oot', 'report-records'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '从飞书拉取失败'))
    } finally {
      setPulling(false)
    }
  }, [queryClient, message])

  const handleCreateNew = useCallback(() => {
    const url = appSettings?.oos_oot_report_form_url
    if (!url) {
      message.warning('尚未配置OOS/OOT报告记录表单链接，请先在飞书设置中配置')
      return
    }
    window.open(url, '_blank')
  }, [appSettings, message])

  const openEdit = useCallback((record: OosOotReportRecordItem) => {
    setEditingRecord(record)
    setStepDept(record.report_department || undefined)
    form.setFieldsValue({
      content: record.content ?? '',
      product_name: record.product_name ?? '',
      batch_number: record.batch_number ?? '',
      report_department: record.report_department ?? '',
      reporter: record.reporter ?? '',
    })
    setModalVisible(true)
  }, [form])

  const openDetail = useCallback((record: OosOotReportRecordItem) => {
    setDrawerRecord(record)
    setDrawerOpen(true)
  }, [])

  const closeModal = useCallback(() => {
    setModalVisible(false)
    setEditingRecord(null)
    setStepDept(undefined)
    form.resetFields()
  }, [form])

  const handleDepartmentChange = useCallback((value: string) => {
    setStepDept(value || undefined)
    form.setFieldValue('reporter', undefined)
  }, [form])

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields()
    try {
      setSaving(true)
      const payload: Record<string, unknown> = {
        content: values.content.trim(),
        product_name: values.product_name?.trim() || '',
        batch_number: values.batch_number?.trim() || '',
        report_department: values.report_department?.trim() || '',
        reporter: values.reporter?.trim() || '',
      }
      if (editingRecord) {
        await updateOosOotReportRecord(editingRecord.record_id, payload)
        message.success('报告记录已更新')
      }
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['quality-oos-oot', 'report-records'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存报告记录失败'))
    } finally {
      setSaving(false)
    }
  }, [closeModal, editingRecord, form, queryClient, message])

  const handleDelete = useCallback(async (recordId: string) => {
    try {
      await deleteOosOotReportRecord(recordId)
      message.success('报告记录已删除')
      queryClient.invalidateQueries({ queryKey: ['quality-oos-oot', 'report-records'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除报告记录失败'))
    }
  }, [queryClient, message])

  const hasFilters = filterReportDept || filterReporter || filterProductName
  const clearFilters = useCallback(() => {
    setFilterReportDept(undefined)
    setFilterReporter(undefined)
    setFilterProductName(undefined)
  }, [])

  const filteredItems = (() => {
    let result = items
    if (searchKeyword) {
      const kw = searchKeyword.toLowerCase()
      result = result.filter((item) =>
        (item.content ?? '').includes(kw) ||
        (item.product_name ?? '').includes(kw) ||
        (item.batch_number ?? '').includes(kw) ||
        (item.report_department ?? '').includes(kw) ||
        (item.reporter ?? '').includes(kw)
      )
    }
    if (filterReportDept) result = result.filter(i => i.report_department === filterReportDept)
    if (filterReporter) result = result.filter(i => i.reporter === filterReporter)
    if (filterProductName) result = result.filter(i => i.product_name === filterProductName)
    return result
  })()

  const columns: ColumnsType<OosOotReportRecordItem> = [
    { title: '报告时间', dataIndex: 'report_time', key: 'report_time', width: 180, render: (v: string | null) => formatDateTime(v) },
    { title: '内容', dataIndex: 'content', key: 'content', width: 280, ellipsis: true, render: (v: string | null) => v || '-' },
    { title: '涉及产品名称', dataIndex: 'product_name', key: 'product_name', width: 160, render: (v: string | null) => v || '-' },
    { title: '涉及批号', dataIndex: 'batch_number', key: 'batch_number', width: 160, render: (v: string | null) => v || '-' },
    { title: '报告部门', dataIndex: 'report_department', key: 'report_department', width: 140, render: (v: string | null) => v || '-' },
    {
      title: '报告人', key: 'reporter', width: 160,
      render: (_, record) => renderPerson(record.reporters, record.reporter),
    },
    {
      title: '附件', key: 'attachments', width: 180,
      render: (_, record) => {
        const attachments = record.attachments
        if (!attachments?.length) return <span>-</span>
        return (
          <Space size={4} wrap>
            {attachments.map((att, idx) => (
              att.url ? (
                <a key={idx} href={att.url} target="_blank" rel="noopener noreferrer">
                  {att.name || `附件${idx + 1}`}
                </a>
              ) : (
                <span key={idx}>{att.name || `附件${idx + 1}`}</span>
              )
            ))}
          </Space>
        )
      },
    },
    {
      title: '操作', key: 'action', width: 180, fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button type="link" onClick={() => openDetail(record)}>详情</Button>
          <Button type="link" onClick={() => openEdit(record)}>修改</Button>
          <Popconfirm title="确认删除这条报告记录？" okText="删除" cancelText="取消" onConfirm={() => void handleDelete(record.record_id)}>
            <Button type="link" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / OOS/OOT管理 / 报告记录</p>
        <Typography.Title level={3} style={{ margin: 0 }}>OOS/OOT报告记录</Typography.Title>
      </div>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
          <AntInput.Search placeholder="搜索内容、产品名称、批号..." allowClear style={{ width: 320 }} value={searchKeyword} onChange={(e) => setSearchKeyword(e.target.value)} />
          <Space>
            <Button type="primary" onClick={handleCreateNew}>新增</Button>
            <Button loading={pulling} onClick={() => void handlePullFromFeishu()}>从飞书拉取</Button>
          </Space>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
          <Select allowClear placeholder="报告部门" style={{ width: 140 }} value={filterReportDept} onChange={setFilterReportDept} options={reportDeptOptions} />
          <Select allowClear placeholder="报告人" style={{ width: 140 }} value={filterReporter} onChange={setFilterReporter} options={reporterOptions2} />
          <Select allowClear placeholder="涉及产品名称" style={{ width: 160 }} value={filterProductName} onChange={setFilterProductName} options={productNameOptions} />
          <Button size="small" onClick={clearFilters} disabled={!hasFilters}>清除筛选</Button>
        </div>
        <Table<OosOotReportRecordItem> rowKey="record_id" loading={loading} columns={columns} dataSource={filteredItems} pagination={false} scroll={{ x: 1400 }} />
      </Card>
      <Modal title="修改报告记录" open={modalVisible} onOk={() => void handleSubmit()} onCancel={closeModal} confirmLoading={saving} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Form.Item name="content" label="内容" rules={[{ required: true, message: '请输入内容' }]}>
            <Input.TextArea placeholder="请输入内容" rows={3} />
          </Form.Item>
          <Form.Item name="product_name" label="涉及产品名称">
            <Input placeholder="请输入涉及产品名称" />
          </Form.Item>
          <Form.Item name="batch_number" label="涉及批号">
            <Input placeholder="请输入涉及批号" />
          </Form.Item>
          <Form.Item name="report_department" label="报告部门">
            <Select showSearch allowClear placeholder="选择部门" options={departmentOptions} onChange={handleDepartmentChange} />
          </Form.Item>
          <Form.Item name="reporter" label="报告人">
            <Select showSearch allowClear placeholder={stepDept ? `选择${stepDept}的人员` : '请先选择部门再选人'} filterOption={(input, option) => (option?.label as string)?.toLowerCase().includes(input.toLowerCase())} options={reporterOptions} />
          </Form.Item>
        </Form>
      </Modal>
      <Drawer
        title="报告记录详情"
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); setDrawerRecord(null) }}
        width={600}
      >
        {drawerRecord && (
          <Space direction="vertical" size={16} style={{ display: 'flex' }}>
            <div>
              <Typography.Text strong>报告时间：</Typography.Text>
              <div>{formatDateTime(drawerRecord.report_time)}</div>
            </div>
            <div>
              <Typography.Text strong>内容：</Typography.Text>
              <div>{drawerRecord.content || '-'}</div>
            </div>
            <div>
              <Typography.Text strong>涉及产品名称：</Typography.Text>
              <div>{drawerRecord.product_name || '-'}</div>
            </div>
            <div>
              <Typography.Text strong>涉及批号：</Typography.Text>
              <div>{drawerRecord.batch_number || '-'}</div>
            </div>
            <div>
              <Typography.Text strong>报告部门：</Typography.Text>
              <div>{drawerRecord.report_department || '-'}</div>
            </div>
            <div>
              <Typography.Text strong>报告人：</Typography.Text>
              <div>{renderPerson(drawerRecord.reporters, drawerRecord.reporter)}</div>
            </div>
            <div>
              <Typography.Text strong>部门负责人确认：</Typography.Text>
              <div>{formatBoolean(drawerRecord.department_head_confirmed)}</div>
            </div>
            {drawerRecord.department_heads && drawerRecord.department_heads.length > 0 && (
              <div>
                <Typography.Text strong>部门负责人：</Typography.Text>
                <div>{renderPerson(drawerRecord.department_heads, null)}</div>
              </div>
            )}
            <div>
              <Typography.Text strong>涉及发酵负责人确认：</Typography.Text>
              <div>{formatBoolean((drawerRecord as any).fermentation_head_confirmed)}</div>
            </div>
            <div>
              <Typography.Text strong>涉及提炼负责人确认：</Typography.Text>
              <div>{formatBoolean((drawerRecord as any).refinement_head_confirmed)}</div>
            </div>
            <div>
              <Typography.Text strong>QA确认：</Typography.Text>
              <div>{formatBoolean(drawerRecord.qa_confirmed)}</div>
            </div>
            {drawerRecord.qas && drawerRecord.qas.length > 0 && (
              <div>
                <Typography.Text strong>QA：</Typography.Text>
                <div>{renderPerson(drawerRecord.qas, null)}</div>
              </div>
            )}
            <div>
              <Typography.Text strong>QA负责人确认：</Typography.Text>
              <div>{formatBoolean(drawerRecord.qa_head_confirmed)}</div>
            </div>
            {drawerRecord.qa_heads && drawerRecord.qa_heads.length > 0 && (
              <div>
                <Typography.Text strong>QA负责人：</Typography.Text>
                <div>{renderPerson(drawerRecord.qa_heads, null)}</div>
              </div>
            )}
            <div>
              <Typography.Text strong>附件：</Typography.Text>
              <div>
                {drawerRecord.attachments?.length ? (
                  <Space size={4} wrap>
                    {drawerRecord.attachments.map((att, idx) => (
                      att.url ? (
                        <a key={idx} href={att.url} target="_blank" rel="noopener noreferrer">
                          {att.name || `附件${idx + 1}`}
                        </a>
                      ) : (
                        <span key={idx}>{att.name || `附件${idx + 1}`}</span>
                      )
                    ))}
                  </Space>
                ) : '-'}
              </div>
            </div>
          </Space>
        )}
      </Drawer>
    </div>
  )
}
