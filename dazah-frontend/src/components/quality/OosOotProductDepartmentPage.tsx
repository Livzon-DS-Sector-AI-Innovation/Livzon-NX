'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Button, Card, Form, Input, Input as AntInput, Modal, Popconfirm, Select, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { pullProductDepartmentRecords, createProductDepartmentRecord, updateProductDepartmentRecord, deleteProductDepartmentRecord } from '@/actions/quality'
import { fetchProductDepartmentRecords, fetchDepartmentContacts } from '@/lib/api/client/quality'
import type { DepartmentContact } from '@/types/quality'

interface ProductDepartmentItem {
  record_id: string
  serial_number: string | null
  product_code: string | null
  fermentation_department: string | null
  fermentation_head: string | null
  extraction_department: string | null
  extraction_head: string | null
}

interface FormValues {
  serial_number: string
  product_code: string
  fermentation_department: string
  fermentation_head: string
  extraction_department: string
  extraction_head: string
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export default function OosOotProductDepartmentPage() {
  const { message } = App.useApp()
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [filterProductCode, setFilterProductCode] = useState<string | undefined>()
  const [filterFermDept, setFilterFermDept] = useState<string | undefined>()
  const [filterExtrDept, setFilterExtrDept] = useState<string | undefined>()
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRecord, setEditingRecord] = useState<ProductDepartmentItem | null>(null)
  const [form] = Form.useForm<FormValues>()
  const [contacts, setContacts] = useState<DepartmentContact[]>([])

  const queryClient = useQueryClient()

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-oos-oot', 'product-department'],
    queryFn: () => fetchProductDepartmentRecords({ page: 1, page_size: 100 }),
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载产品对应部门失败'))
    }
  }, [error, message])

  const items = useMemo<ProductDepartmentItem[]>(() => data?.data ?? [], [data?.data])

  const loadContacts = useCallback(async () => {
    try {
      const list = await fetchDepartmentContacts()
      setContacts(list)
    } catch {
      // contacts load silently
    }
  }, [])

  useEffect(() => {
    void loadContacts()
  }, [loadContacts])

  const contactOptions = contacts
    .filter((c) => c.name)
    .map((c) => ({ label: c.name!, value: (c as any).bitable_user_id || c.open_id || c.name! }))

  const productCodeOptions = useMemo(() => {
    const vals = [...new Set(items.map(i => i.product_code).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const fermDeptOptions = useMemo(() => {
    const vals = [...new Set(items.map(i => i.fermentation_department).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const extrDeptOptions = useMemo(() => {
    const vals = [...new Set(items.map(i => i.extraction_department).filter(Boolean))]
    return vals.map(v => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result: any = await pullProductDepartmentRecords()
      message.success(`从飞书拉取完成：成功 ${result?.synced ?? 0} 条，失败 ${result?.failed ?? 0} 条`)
      queryClient.invalidateQueries({ queryKey: ['quality-oos-oot', 'product-department'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '从飞书拉取失败'))
    } finally {
      setPulling(false)
    }
  }, [queryClient, message])

  const openCreate = useCallback(() => {
    setEditingRecord(null)
    form.resetFields()
    setModalVisible(true)
  }, [form])

  const openEdit = useCallback((record: ProductDepartmentItem) => {
    setEditingRecord(record)
    form.setFieldsValue({
      serial_number: record.serial_number ?? '',
      product_code: record.product_code ?? '',
      fermentation_department: record.fermentation_department ?? '',
      fermentation_head: record.fermentation_head ?? '',
      extraction_department: record.extraction_department ?? '',
      extraction_head: record.extraction_head ?? '',
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
        product_code: values.product_code?.trim() || '',
        fermentation_department: values.fermentation_department?.trim() || '',
        fermentation_head: values.fermentation_head?.trim() || '',
        extraction_department: values.extraction_department?.trim() || '',
        extraction_head: values.extraction_head?.trim() || '',
      }
      if (editingRecord) {
        await updateProductDepartmentRecord(editingRecord.record_id, payload)
        message.success('产品对应部门记录已更新')
      } else {
        await createProductDepartmentRecord(payload)
        message.success('产品对应部门记录已创建')
      }
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['quality-oos-oot', 'product-department'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存产品对应部门记录失败'))
    } finally {
      setSaving(false)
    }
  }, [closeModal, editingRecord, form, queryClient, message])

  const handleDelete = useCallback(async (recordId: string) => {
    try {
      await deleteProductDepartmentRecord(recordId)
      message.success('产品对应部门记录已删除')
      queryClient.invalidateQueries({ queryKey: ['quality-oos-oot', 'product-department'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除产品对应部门记录失败'))
    }
  }, [queryClient, message])

  const hasFilters = filterProductCode || filterFermDept || filterExtrDept
  const clearFilters = useCallback(() => {
    setFilterProductCode(undefined)
    setFilterFermDept(undefined)
    setFilterExtrDept(undefined)
  }, [])

  const filteredItems = (() => {
    let result = items
    if (searchKeyword) {
      const kw = searchKeyword.toLowerCase()
      result = result.filter((item) =>
        (item.serial_number ?? '').includes(kw) ||
        (item.product_code ?? '').includes(kw) ||
        (item.fermentation_department ?? '').includes(kw) ||
        (item.extraction_department ?? '').includes(kw) ||
        (item.fermentation_head ?? '').includes(kw) ||
        (item.extraction_head ?? '').includes(kw)
      )
    }
    if (filterProductCode) result = result.filter(i => i.product_code === filterProductCode)
    if (filterFermDept) result = result.filter(i => i.fermentation_department === filterFermDept)
    if (filterExtrDept) result = result.filter(i => i.extraction_department === filterExtrDept)
    return result
  })()

  const columns: ColumnsType<ProductDepartmentItem> = [
    {
      title: '序号',
      dataIndex: 'serial_number',
      key: 'serial_number',
      width: 80,
      render: (value: string | null) => value || '-',
    },
    {
      title: '产品代码',
      dataIndex: 'product_code',
      key: 'product_code',
      width: 140,
      render: (value: string | null) => value || '-',
    },
    {
      title: '涉及发酵部门',
      dataIndex: 'fermentation_department',
      key: 'fermentation_department',
      width: 160,
      render: (value: string | null) => value || '-',
    },
    {
      title: '涉及发酵部门负责人',
      dataIndex: 'fermentation_head',
      key: 'fermentation_head',
      width: 180,
      render: (value: string | null) => value || '-',
    },
    {
      title: '涉及提炼部门',
      dataIndex: 'extraction_department',
      key: 'extraction_department',
      width: 160,
      render: (value: string | null) => value || '-',
    },
    {
      title: '涉及提炼部门负责人',
      dataIndex: 'extraction_head',
      key: 'extraction_head',
      width: 180,
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
            title="确认删除这条记录？"
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
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / OOS/OOT管理 / 产品对应部门</p>
        <Typography.Title level={3} style={{ margin: 0 }}>产品对应部门</Typography.Title>
      </div>

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
          <AntInput.Search
            placeholder="搜索产品代码、部门..."
            allowClear
            style={{ width: 320 }}
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
          />
          <Space>
            <Button type="primary" onClick={openCreate}>新增</Button>
            <Button loading={pulling} onClick={() => void handlePullFromFeishu()}>从飞书拉取</Button>
          </Space>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
          <Select allowClear placeholder="产品代码" style={{ width: 140 }} value={filterProductCode} onChange={setFilterProductCode} options={productCodeOptions} />
          <Select allowClear placeholder="涉及发酵部门" style={{ width: 160 }} value={filterFermDept} onChange={setFilterFermDept} options={fermDeptOptions} />
          <Select allowClear placeholder="涉及提炼部门" style={{ width: 160 }} value={filterExtrDept} onChange={setFilterExtrDept} options={extrDeptOptions} />
          <Button size="small" onClick={clearFilters} disabled={!hasFilters}>清除筛选</Button>
        </div>

        <Table<ProductDepartmentItem>
          rowKey="record_id"
          loading={loading}
          columns={columns}
          dataSource={filteredItems}
          pagination={false}
          scroll={{ x: 1000 }}
        />
      </Card>

      <Modal
        title={editingRecord ? '修改产品对应部门' : '新增产品对应部门'}
        open={modalVisible}
        onOk={() => void handleSubmit()}
        onCancel={closeModal}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="serial_number" label="序号">
            <Input placeholder="请输入序号" />
          </Form.Item>
          <Form.Item name="product_code" label="产品代码">
            <Input placeholder="请输入产品代码" />
          </Form.Item>
          <Form.Item name="fermentation_department" label="涉及发酵部门">
            <Input placeholder="请输入涉及发酵部门" />
          </Form.Item>
          <Form.Item name="fermentation_head" label="涉及发酵部门负责人">
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
          <Form.Item name="extraction_department" label="涉及提炼部门">
            <Input placeholder="请输入涉及提炼部门" />
          </Form.Item>
          <Form.Item name="extraction_head" label="涉及提炼部门负责人">
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
        </Form>
      </Modal>
    </div>
  )
}
