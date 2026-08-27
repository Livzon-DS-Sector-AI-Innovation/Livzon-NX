'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import dayjs from 'dayjs'
import { App, Avatar, Button, Card, Drawer, Form, Input as AntInput, Modal, Popconfirm, Select, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { pullOosOotInvestigationPushRecords, updateOosOotInvestigationPushRecord, deleteOosOotInvestigationPushRecord } from '@/actions/quality'
import { fetchOosOotInvestigationPushRecords, fetchDepartmentContacts, fetchOosLedgerRecords, fetchOotLedgerRecords, fetchQualityFeishuAppSettings } from '@/lib/api/client/quality'
import type { DepartmentContact, OosOotInvestigationPushRecordItem } from '@/types/quality'

interface FormValues {
  oos_oot_code: string
  push_round: string
  department: string
  submitter: string
  department_head_direct: string
  department_head_result: string
  qa_result: string
  qa_head_result: string
  process_status: string
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm:ss') : value
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

export default function OosOotInvestigationPushPage() {
  const { message } = App.useApp()
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [filterDept, setFilterDept] = useState<string | undefined>()
  const [filterOosOotCode, setFilterOosOotCode] = useState<string | undefined>()
  const [filterDeptHeadResult, setFilterDeptHeadResult] = useState<string | undefined>()
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRecord, setEditingRecord] = useState<OosOotInvestigationPushRecordItem | null>(null)
  const [form] = Form.useForm<FormValues>()
  const [contacts, setContacts] = useState<DepartmentContact[]>([])
  const [invCodes, setInvCodes] = useState<string[]>([])
  const [stepDept, setStepDept] = useState<string | undefined>(undefined)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerRecord, setDrawerRecord] = useState<OosOotInvestigationPushRecordItem | null>(null)

  const queryClient = useQueryClient()

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-oos-oot', 'investigation-push'],
    queryFn: () => fetchOosOotInvestigationPushRecords({ page: 1, page_size: 100 }),
  })

  const { data: appSettings } = useQuery({
    queryKey: ['quality-feishu-settings', 'app'],
    queryFn: fetchQualityFeishuAppSettings,
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载调查推送记录失败'))
    }
  }, [error, message])

  const items = useMemo<OosOotInvestigationPushRecordItem[]>(
    () => data?.data ?? [],
    [data?.data],
  )

  const loadContacts = useCallback(async () => {
    try {
      const list = await fetchDepartmentContacts()
      setContacts(list)
    } catch { /* silent */ }
  }, [])

  // 从 OOS/OOT 台账获取调查编号列表
  const loadInvCodes = useCallback(async () => {
    try {
      const [oosRes, ootRes] = await Promise.all([
        fetchOosLedgerRecords({ page_size: '500' }),
        fetchOotLedgerRecords({ page_size: '500' }),
      ])
      const codes = new Set<string>()
      for (const item of (oosRes.data || [])) {
        if (item.investigation_code) codes.add(item.investigation_code)
      }
      for (const item of (ootRes.data || [])) {
        if (item.investigation_code) codes.add(item.investigation_code)
      }
      setInvCodes([...codes].sort())
    } catch { /* silent */ }
  }, [])

  useEffect(() => { void loadContacts(); void loadInvCodes() }, [loadContacts, loadInvCodes])

  const invCodeOptions = invCodes.map((c) => ({ label: c, value: c }))

  // 部门列表
  const departmentOptions = useMemo(() => {
    const depts = [...new Set(contacts.map((c) => c.department).filter(Boolean))]
    return depts.map((d) => ({ label: d!, value: d! }))
  }, [contacts])

  // 人员列表，按部门过滤
  const submitterOptions = useMemo(() => {
    let filtered = contacts
    if (stepDept) filtered = contacts.filter((c) => c.department === stepDept)
    return filtered
      .filter((c) => c.name)
      .map((c) => ({ label: c.name!, value: (c as any).bitable_user_id || c.open_id || c.name! }))
  }, [contacts, stepDept])

  const deptOptions = useMemo(() => {
    const vals = [...new Set(items.map(i => i.department).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const oosOotCodeOptions = useMemo(() => {
    const vals = [...new Set(items.map(i => i.oos_oot_code).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const deptHeadResultOptions = useMemo(() => {
    const vals = [...new Set(items.map(i => i.department_head_result).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  // 根据选中的部门和提交人，获取部门负责人
  const getDeptHead = useCallback((dept: string | undefined, personBitableId: string | undefined) => {
    if (!dept) return undefined
    // 先从联系人中找对应部门的部门负责人
    const deptContacts = contacts.filter((c) => c.department === dept)
    if (deptContacts.length > 0 && deptContacts[0].department_head_name) {
      const headName = deptContacts[0].department_head_name
      const headContact = contacts.find((c) => c.name === headName)
      if (headContact) return (headContact as any).bitable_user_id || headContact.open_id
    }
    return undefined
  }, [contacts])

  const handleDepartmentChange = useCallback((value: string) => {
    setStepDept(value || undefined)
    form.setFieldValue('submitter', undefined)
    // 自动填充部门负责人
    const headId = getDeptHead(value || undefined, undefined)
    form.setFieldValue('department_head_direct', headId || undefined)
  }, [form, getDeptHead])

  const handleSubmitterChange = useCallback((value: string) => {
    const headId = getDeptHead(stepDept, value || undefined)
    if (headId) form.setFieldValue('department_head_direct', headId)
  }, [form, getDeptHead, stepDept])

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result: any = await pullOosOotInvestigationPushRecords()
      message.success(`从飞书拉取完成：成功 ${result?.synced ?? 0} 条，失败 ${result?.failed ?? 0} 条`)
      queryClient.invalidateQueries({ queryKey: ['quality-oos-oot', 'investigation-push'] })
      await loadInvCodes()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '从飞书拉取失败'))
    } finally { setPulling(false) }
  }, [queryClient, loadInvCodes, message])

  const handleCreateNew = useCallback(() => {
    const url = appSettings?.oos_oot_investigation_push_form_url
    if (!url) {
      message.warning('尚未配置OOS/OOT调查推送表单链接，请先在飞书设置中配置')
      return
    }
    window.open(url, '_blank')
  }, [appSettings, message])

  const openEdit = useCallback((record: OosOotInvestigationPushRecordItem) => {
    setEditingRecord(record)
    setStepDept(record.department || undefined)
    form.setFieldsValue({
      oos_oot_code: record.oos_oot_code ?? '',
      push_round: record.push_round ?? '',
      department: record.department ?? '',
      submitter: record.submitter ?? '',
      department_head_direct: record.department_head_direct ?? '',
      department_head_result: record.department_head_result ?? '',
      qa_result: record.qa_result ?? '',
      qa_head_result: record.qa_head_result ?? '',
      process_status: record.process_status ?? '',
    })
    setModalVisible(true)
  }, [form])

  const openDetail = useCallback((record: OosOotInvestigationPushRecordItem) => {
    setDrawerRecord(record)
    setDrawerOpen(true)
  }, [])

  const closeModal = useCallback(() => {
    setModalVisible(false)
    setEditingRecord(null)
    setStepDept(undefined)
    form.resetFields()
  }, [form])

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields()
    try {
      setSaving(true)
      const payload: Record<string, unknown> = {
        oos_oot_code: values.oos_oot_code.trim(),
        push_round: values.push_round?.trim() || '',
        department: values.department?.trim() || '',
        submitter: values.submitter?.trim() || '',
        department_head_direct: values.department_head_direct?.trim() || '',
        department_head_result: values.department_head_result?.trim() || '',
        qa_result: values.qa_result?.trim() || '',
        qa_head_result: values.qa_head_result?.trim() || '',
        process_status: values.process_status?.trim() || '',
      }
      if (editingRecord) {
        await updateOosOotInvestigationPushRecord(editingRecord.record_id, payload)
        message.success('调查推送记录已更新')
      }
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['quality-oos-oot', 'investigation-push'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存调查推送记录失败'))
    } finally { setSaving(false) }
  }, [closeModal, editingRecord, form, queryClient, message])

  const handleDelete = useCallback(async (recordId: string) => {
    try {
      await deleteOosOotInvestigationPushRecord(recordId)
      message.success('调查推送记录已删除')
      queryClient.invalidateQueries({ queryKey: ['quality-oos-oot', 'investigation-push'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除调查推送记录失败'))
    }
  }, [queryClient, message])

  const hasFilters = filterDept || filterOosOotCode || filterDeptHeadResult
  const clearFilters = useCallback(() => {
    setFilterDept(undefined)
    setFilterOosOotCode(undefined)
    setFilterDeptHeadResult(undefined)
  }, [])

  const filteredItems = (() => {
    let result = items
    if (searchKeyword) {
      const kw = searchKeyword.toLowerCase()
      result = result.filter((item) =>
        (item.oos_oot_code ?? '').includes(kw) ||
        (item.department ?? '').includes(kw) ||
        (item.submitter ?? '').includes(kw)
      )
    }
    if (filterDept) result = result.filter(i => i.department === filterDept)
    if (filterOosOotCode) result = result.filter(i => i.oos_oot_code === filterOosOotCode)
    if (filterDeptHeadResult) result = result.filter(i => i.department_head_result === filterDeptHeadResult)
    return result
  })()

  const columns: ColumnsType<OosOotInvestigationPushRecordItem> = [
    { title: 'OOS/OOT编号', dataIndex: 'oos_oot_code', key: 'oos_oot_code', width: 160, render: (v: string) => v || '-' },
    { title: '第N次推送', dataIndex: 'push_round', key: 'push_round', width: 120, render: (v: string | null) => v || '-' },
    {
      title: '调查报告', key: 'investigation_report_url', width: 140,
      render: (_, record) => {
        const url = record.investigation_report_url
        if (!url) return <span>-</span>
        return <a href={url} target="_blank" rel="noopener noreferrer">查看报告</a>
      },
    },
    { title: '提交日期', dataIndex: 'submitted_at', key: 'submitted_at', width: 160, render: (v: string | null) => formatDateTime(v) },
    {
      title: '提交人', key: 'submitter', width: 160,
      render: (_, record) => renderPerson(record.submitters, record.submitter),
    },
    {
      title: '部门负责人', key: 'department_head', width: 160,
      render: (_, record) => renderPerson(record.department_heads, record.department_head),
    },
    { title: '部门负责人审核结果', dataIndex: 'department_head_result', key: 'department_head_result', width: 150, render: (v: string | null) => v || '-' },
    { title: '部门负责人审核时间', dataIndex: 'department_head_reviewed_at', key: 'department_head_reviewed_at', width: 170, render: (v: string | null) => formatDateTime(v) },
    {
      title: '操作', key: 'action', width: 180, fixed: 'right' as const,
      render: (_, record) => (
        <Space size="small">
          <Button type="link" onClick={() => openDetail(record)}>详情</Button>
          <Button type="link" onClick={() => openEdit(record)}>修改</Button>
          <Popconfirm title="确认删除？" okText="删除" cancelText="取消" onConfirm={() => void handleDelete(record.record_id)}>
            <Button type="link" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / OOS/OOT管理 / 调查推送记录</p>
        <Typography.Title level={3} style={{ margin: 0 }}>OOS/OOT调查推送记录</Typography.Title>
      </div>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
          <AntInput.Search placeholder="搜索编号、部门、提交人..." allowClear style={{ width: 320 }} value={searchKeyword} onChange={(e) => setSearchKeyword(e.target.value)} />
          <Space>
            <Button type="primary" onClick={handleCreateNew}>新增</Button>
            <Button loading={pulling} onClick={() => void handlePullFromFeishu()}>从飞书拉取</Button>
          </Space>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
          <Select allowClear placeholder="部门" style={{ width: 140 }} value={filterDept} onChange={setFilterDept} options={deptOptions} />
          <Select allowClear placeholder="OOS/OOT编号" style={{ width: 160 }} value={filterOosOotCode} onChange={setFilterOosOotCode} options={oosOotCodeOptions} />
          <Select allowClear placeholder="部门负责人审核结果" style={{ width: 170 }} value={filterDeptHeadResult} onChange={setFilterDeptHeadResult} options={deptHeadResultOptions} />
          <Button size="small" onClick={clearFilters} disabled={!hasFilters}>清除筛选</Button>
        </div>
        <Table<OosOotInvestigationPushRecordItem> rowKey="record_id" loading={loading} columns={columns} dataSource={filteredItems} pagination={false} scroll={{ x: 1500 }} />
      </Card>
      <Modal title="修改调查推送记录" open={modalVisible} onOk={() => void handleSubmit()} onCancel={closeModal} confirmLoading={saving} destroyOnHidden width={600}>
        <Form form={form} layout="vertical">
          <Form.Item name="oos_oot_code" label="OOS/OOT编号" rules={[{ required: true, message: '请选择OOS/OOT编号' }]}>
            <Select showSearch allowClear placeholder="从台账调查编号中选择" filterOption={(input, option) => (option?.label as string)?.toLowerCase().includes(input.toLowerCase())} options={invCodeOptions} />
          </Form.Item>
          <Form.Item name="push_round" label="第N次推送">
            <Select allowClear placeholder="请选择" options={[{ label: '第1次', value: '第1次' }, { label: '第2次', value: '第2次' }, { label: '第3次', value: '第3次' }]} />
          </Form.Item>
          <Form.Item name="department" label="部门">
            <Select showSearch allowClear placeholder="选择部门" options={departmentOptions} onChange={handleDepartmentChange} />
          </Form.Item>
          <Form.Item name="submitter" label="提交人">
            <Select showSearch allowClear placeholder={stepDept ? `选择${stepDept}的人员` : '请先选择部门'} filterOption={(input, option) => (option?.label as string)?.toLowerCase().includes(input.toLowerCase())} options={submitterOptions} disabled={!stepDept} onChange={handleSubmitterChange} />
          </Form.Item>
          <Form.Item name="department_head_direct" label="部门负责人">
            <Select showSearch allowClear placeholder="选择部门后自动填充" filterOption={(input, option) => (option?.label as string)?.toLowerCase().includes(input.toLowerCase())} options={submitterOptions} disabled />
          </Form.Item>
          <Form.Item name="department_head_result" label="部门负责人审核结果">
            <Select allowClear placeholder="请选择" options={[{ label: '待审核', value: '待审核' }, { label: '通过', value: '通过' }, { label: '不通过', value: '不通过' }]} />
          </Form.Item>
          <Form.Item name="qa_result" label="QA审核结果">
            <Select allowClear placeholder="请选择" options={[{ label: '待审核', value: '待审核' }, { label: '通过', value: '通过' }, { label: '不通过', value: '不通过' }]} />
          </Form.Item>
          <Form.Item name="qa_head_result" label="QA负责人审核结果">
            <Select allowClear placeholder="请选择" options={[{ label: '待审核', value: '待审核' }, { label: '通过', value: '通过' }, { label: '不通过', value: '不通过' }]} />
          </Form.Item>
          <Form.Item name="process_status" label="流程状态">
            <Select allowClear placeholder="请选择" options={[{ label: '待部门负责人审核', value: '待部门负责人审核' }, { label: '待QA审核', value: '待QA审核' }, { label: '待QA负责人审核', value: '待QA负责人审核' }, { label: '已通过', value: '已通过' }, { label: '已退回', value: '已退回' }]} />
          </Form.Item>
        </Form>
      </Modal>
      <Drawer
        title="调查推送详情"
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); setDrawerRecord(null) }}
        width={600}
      >
        {drawerRecord && (
          <Space direction="vertical" size={16} style={{ display: 'flex' }}>
            <div>
              <Typography.Text strong>OOS/OOT编号：</Typography.Text>
              <div>{drawerRecord.oos_oot_code || '-'}</div>
            </div>
            <div>
              <Typography.Text strong>第N次推送：</Typography.Text>
              <div>{drawerRecord.push_round || '-'}</div>
            </div>
            <div>
              <Typography.Text strong>调查报告：</Typography.Text>
              <div>
                {drawerRecord.investigation_report_url ? (
                  <a href={drawerRecord.investigation_report_url} target="_blank" rel="noopener noreferrer">查看报告</a>
                ) : '-'}
              </div>
            </div>
            <div>
              <Typography.Text strong>提交日期：</Typography.Text>
              <div>{formatDateTime(drawerRecord.submitted_at)}</div>
            </div>
            <div>
              <Typography.Text strong>提交人：</Typography.Text>
              <div>{renderPerson(drawerRecord.submitters, drawerRecord.submitter)}</div>
            </div>
            <div>
              <Typography.Text strong>部门负责人：</Typography.Text>
              <div>{renderPerson(drawerRecord.department_heads, drawerRecord.department_head)}</div>
            </div>
            <div>
              <Typography.Text strong>部门负责人审核结果：</Typography.Text>
              <div>{drawerRecord.department_head_result || '-'}</div>
            </div>
            <div>
              <Typography.Text strong>部门负责人审核时间：</Typography.Text>
              <div>{formatDateTime(drawerRecord.department_head_reviewed_at)}</div>
            </div>
            <div>
              <Typography.Text strong>QA审核结果：</Typography.Text>
              <div>{drawerRecord.qa_result || '-'}</div>
            </div>
            <div>
              <Typography.Text strong>QA审核时间：</Typography.Text>
              <div>{formatDateTime(drawerRecord.qa_reviewed_at)}</div>
            </div>
            {drawerRecord.qas && drawerRecord.qas.length > 0 && (
              <div>
                <Typography.Text strong>QA：</Typography.Text>
                <div>{renderPerson(drawerRecord.qas, null)}</div>
              </div>
            )}
            <div>
              <Typography.Text strong>QA负责人审核结果：</Typography.Text>
              <div>{drawerRecord.qa_head_result || '-'}</div>
            </div>
            <div>
              <Typography.Text strong>QA负责人审核时间：</Typography.Text>
              <div>{formatDateTime(drawerRecord.qa_head_reviewed_at)}</div>
            </div>
            {drawerRecord.qa_heads && drawerRecord.qa_heads.length > 0 && (
              <div>
                <Typography.Text strong>QA负责人：</Typography.Text>
                <div>{renderPerson(drawerRecord.qa_heads, null)}</div>
              </div>
            )}
            <div>
              <Typography.Text strong>流程状态：</Typography.Text>
              <div>{drawerRecord.process_status || '-'}</div>
            </div>
          </Space>
        )}
      </Drawer>
    </div>
  )
}
