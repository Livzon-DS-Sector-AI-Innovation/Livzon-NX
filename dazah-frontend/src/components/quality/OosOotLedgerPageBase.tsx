'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import { App, Button, Card, DatePicker, Form, Input, Input as AntInput, Modal, Popconfirm, Select, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DownloadOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { fetchDepartmentContacts } from '@/lib/api/client/quality'
import type { DepartmentContact } from '@/types/quality'

export interface OosOotLedgerRecord {
  record_id: string
  serial_number: string | null
  date: string | null
  material_name: string | null
  batch_number: string | null
  investigation_code: string | null
  problem_description: string | null
  root_cause: string | null
  corrective_actions: string | null
  final_disposition: string | null
  registrant: string | null
  remark: string | null
}

/** OOS/OOT 台账差异配置：两个页面仅标签、query key、actions 与导出地址不同 */
export interface OosOotLedgerConfig {
  /** 台账标签：OOS 或 OOT */
  label: 'OOS' | 'OOT'
  /** React Query key 前缀 */
  queryKeyPrefix: string
  /** 导出接口地址 */
  exportUrl: string
  fetchRecords: (params: { page: string; page_size: string }) => Promise<{ data?: OosOotLedgerRecord[] }>
  pullRecords: () => Promise<unknown>
  createRecord: (payload: Record<string, unknown>) => Promise<unknown>
  updateRecord: (recordId: string, payload: Record<string, unknown>) => Promise<unknown>
  deleteRecord: (recordId: string) => Promise<unknown>
}

interface FormValues {
  serial_number: string
  date: Dayjs | null
  material_name: string
  batch_number: string
  investigation_code: string
  problem_description: string
  root_cause: string
  corrective_actions: string
  final_disposition: string
  registrant: string
  remark: string
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD') : value
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

/**
 * OOS/OOT 台账页通用实现（原 OosLedgerPage/OotLedgerPage 克隆合并）。
 */
export function OosOotLedgerPageBase({ config }: { config: OosOotLedgerConfig }) {
  const { label, queryKeyPrefix, exportUrl, fetchRecords, pullRecords, createRecord, updateRecord, deleteRecord } = config
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [filterMaterial, setFilterMaterial] = useState<string | undefined>()
  const [filterBatch, setFilterBatch] = useState<string | undefined>()
  const [filterInvCode, setFilterInvCode] = useState<string | undefined>()
  const [filterRegistrant, setFilterRegistrant] = useState<string | undefined>()
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRecord, setEditingRecord] = useState<OosOotLedgerRecord | null>(null)
  const [form] = Form.useForm<FormValues>()

  const { data: contacts = [] } = useQuery<DepartmentContact[]>({
    queryKey: ['quality-department-contacts'],
    queryFn: fetchDepartmentContacts,
  })

  const { data, isLoading: loading, error } = useQuery({
    queryKey: [queryKeyPrefix, 'list'],
    queryFn: () => fetchRecords({ page: '1', page_size: '100' }),
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, `加载${label}台账失败`))
    }
  }, [error, message, label])

  const items = useMemo<OosOotLedgerRecord[]>(() => data?.data ?? [], [data?.data])

  const contactOptions = contacts
    .filter((c) => c.name)
    .map((c) => ({ label: c.name!, value: (c as any).bitable_user_id || c.open_id || c.name! }))

  const materialOptions = useMemo(() => {
    const vals = [...new Set(items.map(i => i.material_name).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const batchOptions = useMemo(() => {
    const vals = [...new Set(items.map(i => i.batch_number).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const invCodeOptions = useMemo(() => {
    const vals = [...new Set(items.map(i => i.investigation_code).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const registrantOptions = useMemo(() => {
    const vals = [...new Set(items.map(i => i.registrant).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result: any = await pullRecords()
      message.success(`从飞书拉取完成：成功 ${result?.synced ?? 0} 条，失败 ${result?.failed ?? 0} 条`)
      queryClient.invalidateQueries({ queryKey: [queryKeyPrefix, 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '从飞书拉取失败'))
    } finally {
      setPulling(false)
    }
  }, [queryClient, message, pullRecords, queryKeyPrefix])

  const openCreate = useCallback(() => {
    setEditingRecord(null)
    form.resetFields()
    form.setFieldsValue({ date: dayjs() })
    setModalVisible(true)
  }, [form])

  const openEdit = useCallback((record: OosOotLedgerRecord) => {
    setEditingRecord(record)
    form.setFieldsValue({
      serial_number: record.serial_number ?? '',
      date: record.date ? dayjs(record.date) : null,
      material_name: record.material_name ?? '',
      batch_number: record.batch_number ?? '',
      investigation_code: record.investigation_code ?? '',
      problem_description: record.problem_description ?? '',
      root_cause: record.root_cause ?? '',
      corrective_actions: record.corrective_actions ?? '',
      final_disposition: record.final_disposition ?? '',
      registrant: record.registrant ?? '',
      remark: record.remark ?? '',
    })
    setModalVisible(true)
  }, [form])

  const closeModal = useCallback(() => {
    setModalVisible(false)
    setEditingRecord(null)
    form.resetFields()
  }, [form])

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields()
    try {
      setSaving(true)
      const payload: Record<string, unknown> = {
        serial_number: values.serial_number?.trim() || '',
        date: values.date ? values.date.format('YYYY-MM-DD') : '',
        material_name: values.material_name?.trim() || '',
        batch_number: values.batch_number?.trim() || '',
        investigation_code: values.investigation_code?.trim() || '',
        problem_description: values.problem_description?.trim() || '',
        root_cause: values.root_cause?.trim() || '',
        corrective_actions: values.corrective_actions?.trim() || '',
        final_disposition: values.final_disposition?.trim() || '',
        registrant: values.registrant?.trim() || '',
        remark: values.remark?.trim() || '',
      }
      if (editingRecord) {
        await updateRecord(editingRecord.record_id, payload)
        message.success(`${label}台账记录已更新`)
      } else {
        await createRecord(payload)
        message.success(`${label}台账记录已创建`)
      }
      closeModal()
      queryClient.invalidateQueries({ queryKey: [queryKeyPrefix, 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, `保存${label}台账记录失败`))
    } finally {
      setSaving(false)
    }
  }, [closeModal, editingRecord, form, queryClient, message, label, queryKeyPrefix, createRecord, updateRecord])

  const handleDelete = useCallback(async (recordId: string) => {
    try {
      await deleteRecord(recordId)
      message.success(`${label}台账记录已删除`)
      queryClient.invalidateQueries({ queryKey: [queryKeyPrefix, 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, `删除${label}台账记录失败`))
    }
  }, [queryClient, message, label, queryKeyPrefix, deleteRecord])

  const hasFilters = filterMaterial || filterBatch || filterInvCode || filterRegistrant
  const clearFilters = useCallback(() => {
    setFilterMaterial(undefined)
    setFilterBatch(undefined)
    setFilterInvCode(undefined)
    setFilterRegistrant(undefined)
  }, [])

  const filteredItems = (() => {
    let result = items
    if (searchKeyword) {
      const kw = searchKeyword.toLowerCase()
      result = result.filter((item) =>
        (item.serial_number ?? '').includes(kw) ||
        (item.material_name ?? '').includes(kw) ||
        (item.batch_number ?? '').includes(kw) ||
        (item.investigation_code ?? '').includes(kw) ||
        (item.problem_description ?? '').includes(kw) ||
        (item.registrant ?? '').includes(kw)
      )
    }
    if (filterMaterial) result = result.filter(i => i.material_name === filterMaterial)
    if (filterBatch) result = result.filter(i => i.batch_number === filterBatch)
    if (filterInvCode) result = result.filter(i => i.investigation_code === filterInvCode)
    if (filterRegistrant) result = result.filter(i => i.registrant === filterRegistrant)
    return result
  })()

  const columns: ColumnsType<OosOotLedgerRecord> = [
    {
      title: '序号',
      dataIndex: 'serial_number',
      key: 'serial_number',
      width: 80,
      render: (value: string | null) => value || '-',
    },
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
      width: 120,
      render: (value: string | null) => formatDate(value),
    },
    {
      title: '物料名称',
      dataIndex: 'material_name',
      key: 'material_name',
      width: 150,
      render: (value: string | null) => value || '-',
    },
    {
      title: '批号',
      dataIndex: 'batch_number',
      key: 'batch_number',
      width: 140,
      render: (value: string | null) => value || '-',
    },
    {
      title: '调查编号',
      dataIndex: 'investigation_code',
      key: 'investigation_code',
      width: 150,
      render: (value: string | null) => value || '-',
    },
    {
      title: '问题描述',
      dataIndex: 'problem_description',
      key: 'problem_description',
      width: 250,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '登记人',
      dataIndex: 'registrant',
      key: 'registrant',
      width: 120,
      render: (value: string | null) => value || '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button type="link" onClick={() => openEdit(record)}>修改</Button>
          <Popconfirm
            title="确认删除这条台账记录？"
            okText="删除"
            cancelText="取消"
            onConfirm={() => void handleDelete(record.record_id)}
          >
            <Button type="link" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / OOS/OOT管理 / {label}台账</p>
        <Typography.Title level={3} style={{ margin: 0 }}>{label}台账</Typography.Title>
      </div>

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
          <AntInput.Search
            placeholder="搜索序号、物料名称、批号..."
            allowClear
            style={{ width: 320 }}
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
          />
          <Space>
            <Button type="primary" onClick={openCreate}>新增</Button>
            <Button loading={pulling} onClick={() => void handlePullFromFeishu()}>从飞书拉取</Button>
            <Button icon={<DownloadOutlined />} onClick={() => window.open(exportUrl, '_blank')}>导出</Button>
          </Space>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
          <Select allowClear placeholder="物料名称" style={{ width: 140 }} value={filterMaterial} onChange={setFilterMaterial} options={materialOptions} />
          <Select allowClear placeholder="批号" style={{ width: 140 }} value={filterBatch} onChange={setFilterBatch} options={batchOptions} />
          <Select allowClear placeholder="调查编号" style={{ width: 140 }} value={filterInvCode} onChange={setFilterInvCode} options={invCodeOptions} />
          <Select allowClear placeholder="登记人" style={{ width: 140 }} value={filterRegistrant} onChange={setFilterRegistrant} options={registrantOptions} />
          <Button size="small" onClick={clearFilters} disabled={!hasFilters}>清除筛选</Button>
        </div>

        <Table<OosOotLedgerRecord>
          rowKey="record_id"
          loading={loading}
          columns={columns}
          dataSource={filteredItems}
          pagination={false}
          scroll={{ x: 1100 }}
        />
      </Card>

      <Modal
        title={editingRecord ? `修改${label}台账记录` : `新增${label}台账记录`}
        open={modalVisible}
        onOk={() => void handleSubmit()}
        onCancel={closeModal}
        confirmLoading={saving}
        destroyOnHidden
        width={600}
      >
        <Form form={form} layout="vertical">
          {editingRecord ? (
            <Form.Item name="serial_number" label="序号">
              <Input placeholder="序号" />
            </Form.Item>
          ) : null}
          <Form.Item name="date" label="日期">
            <DatePicker style={{ width: '100%' }} placeholder="请选择日期" format="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item name="material_name" label="物料名称">
            <Input placeholder="请输入物料名称" />
          </Form.Item>
          <Form.Item name="batch_number" label="批号">
            <Input placeholder="请输入批号" />
          </Form.Item>
          <Form.Item name="investigation_code" label="调查编号">
            <Input placeholder="请输入调查编号" />
          </Form.Item>
          <Form.Item name="problem_description" label="问题描述">
            <Input.TextArea placeholder="请输入问题描述" rows={2} />
          </Form.Item>
          <Form.Item name="root_cause" label="产生原因">
            <Input.TextArea placeholder="请输入产生原因" rows={2} />
          </Form.Item>
          <Form.Item name="corrective_actions" label="纠正预防措施">
            <Input.TextArea placeholder="请输入纠正预防措施" rows={2} />
          </Form.Item>
          <Form.Item name="final_disposition" label="最终处理结果">
            <Input placeholder="请输入最终处理结果" />
          </Form.Item>
          <Form.Item name="registrant" label="登记人">
            <Select
              showSearch
              allowClear
              placeholder="输入姓名搜索部门联系人"
              filterOption={(input, option) =>
                (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
              }
              options={contactOptions}
            />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea placeholder="请输入备注" rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
