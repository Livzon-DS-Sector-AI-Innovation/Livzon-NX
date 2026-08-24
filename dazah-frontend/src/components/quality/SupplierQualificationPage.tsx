'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import { App, Button, Card, DatePicker, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { pullSupplierQualifications, createSupplierQualification, updateSupplierQualification, deleteSupplierQualification } from '@/actions/quality'
import { fetchSupplierQualifications } from '@/lib/api/client/quality'
import type { SupplierQualificationItem } from '@/types/quality'

const MATERIAL_TYPE_OPTIONS = [
  { label: '固体', value: '固体' },
  { label: '液体', value: '液体' },
  { label: '包材', value: '包材' },
]

const QUALIFICATION_NAME_OPTIONS = [
  { label: '营业执照', value: '营业执照' },
  { label: '生产许可证', value: '生产许可证' },
  { label: '安全生产许可证', value: '安全生产许可证' },
  { label: '危险化学品登记证', value: '危险化学品登记证' },
  { label: '生产备案证明', value: '生产备案证明' },
  { label: '经营许可证', value: '经营许可证' },
  { label: '经销商营业执照', value: '经销商营业执照' },
  { label: 'ISO（9001）', value: 'ISO（9001）' },
  { label: '质量证书ISO（9001）', value: '质量证书ISO（9001）' },
  { label: 'ISO（14001）', value: 'ISO（14001）' },
  { label: 'ISO（22000）', value: 'ISO（22000）' },
  { label: 'ISO（45001）', value: 'ISO（45001）' },
  { label: 'COA可靠性确认', value: 'COA可靠性确认' },
  { label: '质量协议', value: '质量协议' },
  { label: '调查问卷', value: '调查问卷' },
  { label: '三方检测报告', value: '三方检测报告' },
  { label: 'KOSHER证书', value: 'KOSHER证书' },
  { label: 'HALAL', value: 'HALAL' },
  { label: 'IP证书', value: 'IP证书' },
  { label: 'HACCP证书', value: 'HACCP证书' },
  { label: '注册证', value: '注册证' },
  { label: '其他证书', value: '其他证书' },
]

interface FormValues {
  supplier_name: string
  material_name: string
  material_type: string
  qualification_name: string
  qualification_file: string
  is_completed: boolean
  deadline: Dayjs | null
  responsible_person: string
  remark: string
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD') : value
}

function toDateValue(value: string | null | undefined): Dayjs | null {
  if (!value) return null
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed : null
}

interface SupplierQualificationPageProps {
  initialItems?: SupplierQualificationItem[]
}

export default function SupplierQualificationPage({ initialItems = [] }: SupplierQualificationPageProps) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [materialTypeFilter, setMaterialTypeFilter] = useState<string | undefined>()
  const [qualificationNameFilter, setQualificationNameFilter] = useState<string | undefined>()
  const [isCompletedFilter, setIsCompletedFilter] = useState<boolean | undefined>()
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRecord, setEditingRecord] = useState<SupplierQualificationItem | null>(null)
  const [form] = Form.useForm<FormValues>()

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-supplier', 'list', {
      materialTypeFilter: materialTypeFilter ?? '',
      qualificationNameFilter: qualificationNameFilter ?? '',
      isCompletedFilter: isCompletedFilter === undefined ? '' : String(isCompletedFilter),
    }],
    queryFn: () =>
      fetchSupplierQualifications({
        page: 1,
        page_size: 200,
        material_type: materialTypeFilter || undefined,
        qualification_name: qualificationNameFilter || undefined,
        is_completed: isCompletedFilter,
      }),
    initialData: initialItems.length ? { items: initialItems, total: initialItems.length } : undefined,
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载供应商资质失败'))
    }
  }, [error, message])

  const items = data?.items ?? []

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result = await pullSupplierQualifications()
      message.success(`从飞书拉取完成：成功 ${result?.synced ?? 0} 条`)
      queryClient.invalidateQueries({ queryKey: ['quality-supplier', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '从飞书拉取失败'))
    } finally {
      setPulling(false)
    }
  }, [queryClient, message])

  const openCreate = useCallback(() => {
    setEditingRecord(null)
    form.resetFields()
    form.setFieldsValue({ is_completed: false })
    setModalVisible(true)
  }, [form])

  const openEdit = useCallback((record: SupplierQualificationItem) => {
    setEditingRecord(record)
    form.setFieldsValue({
      supplier_name: record.supplier_name ?? '',
      material_name: record.material_name ?? '',
      material_type: record.material_type ?? '',
      qualification_name: record.qualification_name ?? '',
      qualification_file: record.qualification_file ?? '',
      is_completed: record.is_completed ?? false,
      deadline: toDateValue(record.deadline),
      responsible_person: record.responsible_person ?? '',
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
      const payload = {
        supplier_name: values.supplier_name?.trim() || '',
        material_name: values.material_name?.trim() || null,
        material_type: values.material_type?.trim() || null,
        qualification_name: values.qualification_name?.trim() || '',
        qualification_file: values.qualification_file?.trim() || null,
        is_completed: values.is_completed ?? false,
        deadline: values.deadline ? values.deadline.format('YYYY-MM-DD') : null,
        responsible_person: values.responsible_person?.trim() || null,
        remark: values.remark?.trim() || null,
      }
      if (editingRecord) {
        await updateSupplierQualification(editingRecord.record_id, payload)
        message.success('供应商资质记录已更新')
      } else {
        await createSupplierQualification(payload)
        message.success('供应商资质记录已创建')
      }
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['quality-supplier', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存供应商资质记录失败'))
    } finally {
      setSaving(false)
    }
  }, [closeModal, editingRecord, form, queryClient, message])

  const handleDelete = useCallback(async (recordId: string) => {
    try {
      await deleteSupplierQualification(recordId)
      message.success('供应商资质记录已删除')
      queryClient.invalidateQueries({ queryKey: ['quality-supplier', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除供应商资质记录失败'))
    }
  }, [queryClient, message])

  const filteredItems = useMemo(() => {
    if (!searchKeyword) return items
    const keyword = searchKeyword.toLowerCase()
    return items.filter((item) =>
      [
        item.supplier_name,
        item.material_name,
        item.material_type,
        item.qualification_name,
        item.qualification_file,
        item.responsible_person,
        item.remark,
      ].some((value) => (value ?? '').toLowerCase().includes(keyword))
    )
  }, [items, searchKeyword])

  const columns: ColumnsType<SupplierQualificationItem> = [
    {
      title: '供应商名称',
      dataIndex: 'supplier_name',
      key: 'supplier_name',
      width: 180,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '物料名称',
      dataIndex: 'material_name',
      key: 'material_name',
      width: 140,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '物料类型',
      dataIndex: 'material_type',
      key: 'material_type',
      width: 90,
      render: (value: string | null) => {
        const colorMap: Record<string, string> = { '固体': 'orange', '液体': 'blue', '包材': 'purple' }
        return value ? <span style={{ color: colorMap[value] ?? 'default' }}>{value}</span> : '-'
      },
    },
    {
      title: '资质名称',
      dataIndex: 'qualification_name',
      key: 'qualification_name',
      width: 160,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '资质文件',
      dataIndex: 'qualification_file',
      key: 'qualification_file',
      width: 150,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '是否完成',
      dataIndex: 'is_completed',
      key: 'is_completed',
      width: 90,
      render: (value: boolean) => (
        <span style={{ color: value ? '#1aae39' : '#dd5b00' }}>{value ? '已完成' : '未完成'}</span>
      ),
    },
    {
      title: '截止日期',
      dataIndex: 'deadline',
      key: 'deadline',
      width: 120,
      render: (value: string | null) => {
        if (!value) return '-'
        const d = dayjs(value)
        if (!d.isValid()) return '-'
        const isExpired = d.isBefore(dayjs(), 'day') && !d.isSame(dayjs(), 'day')
        return <span style={{ color: isExpired ? '#e03131' : undefined }}>{d.format('YYYY-MM-DD')}</span>
      },
    },
    {
      title: '到期状态',
      dataIndex: 'expiry_status',
      key: 'expiry_status',
      width: 140,
      render: (value: string | null) => {
        if (!value) return '-'
        const isOverdue = value.includes('已延期')
        return <span style={{ color: isOverdue ? '#e03131' : '#0075de' }}>{value}</span>
      },
    },
    {
      title: '负责人',
      dataIndex: 'responsible_person',
      key: 'responsible_person',
      width: 100,
      render: (value: string | null) => value || '-',
    },
    {
      title: '备注',
      dataIndex: 'remark',
      key: 'remark',
      width: 150,
      ellipsis: true,
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
            title="确认删除这条供应商资质记录？"
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
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 供应商管理 / 供应商资质</p>
        <Typography.Title level={3} style={{ margin: 0 }}>供应商资质</Typography.Title>
      </div>

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
          <Space wrap>
            <Input.Search
              placeholder="搜索供应商名称、物料、资质..."
              allowClear
              style={{ width: 300 }}
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
            />
            <Select
              placeholder="物料类型"
              allowClear
              style={{ width: 120 }}
              value={materialTypeFilter}
              onChange={(val) => setMaterialTypeFilter(val)}
              options={MATERIAL_TYPE_OPTIONS}
            />
            <Select
              placeholder="资质名称"
              allowClear
              style={{ width: 180 }}
              value={qualificationNameFilter}
              onChange={(val) => setQualificationNameFilter(val)}
              options={QUALIFICATION_NAME_OPTIONS}
            />
            <Select
              placeholder="完成状态"
              allowClear
              style={{ width: 120 }}
              value={isCompletedFilter}
              onChange={(val) => setIsCompletedFilter(val)}
              options={[
                { label: '已完成', value: true },
                { label: '未完成', value: false },
              ]}
            />
          </Space>
          <Space>
            <Button type="primary" onClick={openCreate}>新增</Button>
            <Button loading={pulling} onClick={() => void handlePullFromFeishu()}>从飞书拉取</Button>
          </Space>
        </div>

        <Table<SupplierQualificationItem>
          rowKey="record_id"
          loading={loading}
          columns={columns}
          dataSource={filteredItems}
          pagination={false}
          scroll={{ x: 1400 }}
        />
      </Card>

      <Modal
        title={editingRecord ? '修改供应商资质记录' : '新增供应商资质记录'}
        open={modalVisible}
        onOk={() => void handleSubmit()}
        onCancel={closeModal}
        confirmLoading={saving}
        destroyOnHidden
        width={800}
      >
        <Form form={form} layout="vertical">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16 }}>
            <Form.Item
              name="supplier_name"
              label="供应商名称"
              rules={[{ required: true, message: '请输入供应商名称' }]}
            >
              <Input placeholder="请输入供应商名称" />
            </Form.Item>
            <Form.Item name="material_name" label="物料名称">
              <Input placeholder="请输入物料名称" />
            </Form.Item>
            <Form.Item name="material_type" label="物料类型">
              <Select placeholder="请选择物料类型" allowClear options={MATERIAL_TYPE_OPTIONS} />
            </Form.Item>
            <Form.Item
              name="qualification_name"
              label="资质名称"
              rules={[{ required: true, message: '请选择资质名称' }]}
            >
              <Select placeholder="请选择资质名称" allowClear options={QUALIFICATION_NAME_OPTIONS} />
            </Form.Item>
            <Form.Item name="qualification_file" label="资质文件">
              <Input placeholder="请输入资质文件" />
            </Form.Item>
            <Form.Item name="deadline" label="截止日期">
              <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
            </Form.Item>
            <Form.Item name="responsible_person" label="负责人">
              <Input placeholder="请输入负责人" />
            </Form.Item>
            <Form.Item name="is_completed" label="是否完成" valuePropName="checked">
              <Switch />
            </Form.Item>
          </div>

          <Form.Item name="remark" label="备注">
            <Input.TextArea placeholder="请输入备注" rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
