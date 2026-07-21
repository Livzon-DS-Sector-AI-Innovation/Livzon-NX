'use client'

import { useMemo, useState } from 'react'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import {
  App,
  Button,
  DatePicker,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
} from 'antd'
import type { TableProps } from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
  SaveOutlined,
  SendOutlined,
} from '@ant-design/icons'
import {
  createPurchaseRequest,
  submitPurchaseRequest,
  updatePurchaseRequest,
} from '@/actions/purchasing'
import { fetchPurchaseRequests } from '@/lib/api/purchasing'
import type {
  PurchaseRequestCategory,
  PurchaseRequestItemInput,
  PurchaseRequestResponse,
} from '@/types/purchasing'
import {
  calculateLineAmount,
  defaultPurchaseRequestItem,
  formatMoney,
  purchaseStatusColors,
  purchaseStatusLabels,
} from './purchaseRequestConstants'

type PurchaseRequestFormClientProps = {
  category: PurchaseRequestCategory
  categoryLabel: string
  initialRequests: PurchaseRequestResponse[]
  initialTotal: number
}

type PurchaseRequestFormValues = {
  request_department: string
  request_date: Dayjs
  items: PurchaseRequestItemInput[]
}

type EditableItemRow = {
  key: number
  name: number
}

const DEFAULT_PAGE_SIZE = 20

function normalizeItems(items: PurchaseRequestResponse['items']): PurchaseRequestItemInput[] {
  const normalized = (items ?? []).map((item) => ({
    product_name: item.product_name,
    specification: item.specification,
    purpose: item.purpose,
    material: item.material,
    brand: item.brand,
    quantity: item.quantity,
    unit: item.unit,
    unit_price: item.unit_price,
    remarks: item.remarks,
  }))
  return normalized.length > 0 ? normalized : [{ ...defaultPurchaseRequestItem }]
}

function buildPayload(
  values: PurchaseRequestFormValues,
  category: PurchaseRequestCategory
) {
  return {
    category,
    request_department: values.request_department,
    request_date: values.request_date.format('YYYY-MM-DD'),
    items: values.items.map((item) => ({
      ...item,
      product_name: item.product_name?.trim(),
      specification: item.specification?.trim() ?? '',
      purpose: item.purpose?.trim() ?? '',
      material: item.material?.trim() ?? '',
      brand: item.brand?.trim() ?? '',
      unit: item.unit?.trim() ?? '',
      remarks: item.remarks?.trim() ?? '',
    })),
  }
}

export function PurchaseRequestFormClient({
  category,
  categoryLabel,
  initialRequests,
  initialTotal,
}: PurchaseRequestFormClientProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<PurchaseRequestFormValues>()
  const [records, setRecords] = useState(initialRequests)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [submittingId, setSubmittingId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [detailRecord, setDetailRecord] = useState<PurchaseRequestResponse | null>(null)
  const watchedItems = Form.useWatch('items', form) ?? []

  const totalAmount = useMemo(
    () =>
      watchedItems.reduce(
        (sum, item) => sum + calculateLineAmount(item?.quantity, item?.unit_price),
        0
      ),
    [watchedItems]
  )

  const loadRecords = async (nextPage = page) => {
    setLoading(true)
    try {
      const response = await fetchPurchaseRequests({
        category,
        page: nextPage,
        page_size: DEFAULT_PAGE_SIZE,
      })
      setRecords(response.data ?? [])
      setTotal(Number(response.meta?.total ?? response.data?.length ?? 0))
      setPage(nextPage)
    } catch {
      message.error('采购申请列表加载失败')
    } finally {
      setLoading(false)
    }
  }

  const resetForm = () => {
    setEditingId(null)
    form.resetFields()
    form.setFieldsValue({
      request_date: dayjs(),
      items: [{ ...defaultPurchaseRequestItem }],
    })
  }

  const handleFinish = async (values: PurchaseRequestFormValues) => {
    setSaving(true)
    try {
      const payload = buildPayload(values, category)
      const response = editingId
        ? await updatePurchaseRequest(editingId, {
            request_department: payload.request_department,
            request_date: payload.request_date,
            items: payload.items,
          })
        : await createPurchaseRequest(payload)

      if (response.code !== 200) {
        message.error(response.message || '采购申请保存失败')
        return
      }
      message.success(editingId ? '采购申请已更新' : '采购申请已保存')
      resetForm()
      await loadRecords(1)
    } catch {
      message.error('采购申请保存失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  const handleEdit = (record: PurchaseRequestResponse) => {
    setEditingId(record.id)
    form.setFieldsValue({
      request_department: record.request_department,
      request_date: dayjs(record.request_date),
      items: normalizeItems(record.items),
    })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleSubmitFlow = async (record: PurchaseRequestResponse) => {
    setSubmittingId(record.id)
    try {
      const response = await submitPurchaseRequest(record.id)
      if (response.code !== 200) {
        message.error(response.message || '采购申请提交失败')
        return
      }
      message.success('已提交至部门负责人审批')
      await loadRecords(page)
    } catch {
      message.error('采购申请提交失败，请稍后重试')
    } finally {
      setSubmittingId(null)
    }
  }

  const recordColumns: TableProps<PurchaseRequestResponse>['columns'] = [
    {
      title: '申请日期',
      dataIndex: 'request_date',
      key: 'request_date',
      width: 130,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD'),
    },
    {
      title: '申购部门',
      dataIndex: 'request_department',
      key: 'request_department',
      width: 180,
      ellipsis: true,
    },
    {
      title: '合计',
      dataIndex: 'total_amount',
      key: 'total_amount',
      width: 120,
      render: (value: string | number) => formatMoney(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 160,
      render: (status: PurchaseRequestResponse['status']) => (
        <Tag color={purchaseStatusColors[status]}>{purchaseStatusLabels[status]}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      fixed: 'right',
      render: (_, record) => {
        const editable = record.status === 'draft' || record.status === 'rejected'
        return (
          <Space size="small">
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => setDetailRecord(record)}
            >
              查看
            </Button>
            {editable && (
              <Button
                type="link"
                size="small"
                icon={<EditOutlined />}
                onClick={() => handleEdit(record)}
              >
                编辑
              </Button>
            )}
            {editable && (
              <Popconfirm
                title="确认提交到部门负责人审批？"
                okText="提交"
                cancelText="取消"
                onConfirm={() => handleSubmitFlow(record)}
              >
                <Button
                  type="link"
                  size="small"
                  icon={<SendOutlined />}
                  loading={submittingId === record.id}
                >
                  提交
                </Button>
              </Popconfirm>
            )}
          </Space>
        )
      },
    },
  ]

  const detailItemColumns: TableProps<NonNullable<PurchaseRequestResponse['items']>[number]>['columns'] = [
    { title: '序号', dataIndex: 'sequence', key: 'sequence', width: 70 },
    { title: '商品名称', dataIndex: 'product_name', key: 'product_name', width: 160 },
    { title: '规格', dataIndex: 'specification', key: 'specification', width: 120 },
    { title: '用途', dataIndex: 'purpose', key: 'purpose', width: 160 },
    { title: '材质', dataIndex: 'material', key: 'material', width: 100 },
    { title: '品牌', dataIndex: 'brand', key: 'brand', width: 100 },
    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 90 },
    { title: '单位', dataIndex: 'unit', key: 'unit', width: 80 },
    {
      title: '单价（元）',
      dataIndex: 'unit_price',
      key: 'unit_price',
      width: 110,
      render: (value) => formatMoney(value),
    },
    {
      title: '总额（元）',
      dataIndex: 'total_amount',
      key: 'total_amount',
      width: 110,
      render: (value) => formatMoney(value),
    },
    { title: '备注', dataIndex: 'remarks', key: 'remarks', width: 180 },
  ]

  const approvalColumns: TableProps<NonNullable<PurchaseRequestResponse['approvals']>[number]>['columns'] = [
    {
      title: '审批角色',
      dataIndex: 'approval_role',
      key: 'approval_role',
      width: 140,
      render: (role: string) => (role === 'department_head' ? '部门负责人' : '分管领导'),
    },
    {
      title: '结果',
      dataIndex: 'result',
      key: 'result',
      width: 100,
      render: (result: string) => (
        <Tag color={result === 'approved' ? 'success' : 'error'}>
          {result === 'approved' ? '通过' : '驳回'}
        </Tag>
      ),
    },
    { title: '审批人', dataIndex: 'approver_name', key: 'approver_name', width: 120 },
    { title: '意见', dataIndex: 'opinion', key: 'opinion' },
    {
      title: '审批时间',
      dataIndex: 'approval_time',
      key: 'approval_time',
      width: 170,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
  ]

  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">采购管理 / 采购申请</p>
        <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">
          {categoryLabel}采购申请
        </h1>
      </div>

      <Form
        form={form}
        layout="vertical"
        initialValues={{
          request_date: dayjs(),
          items: [{ ...defaultPurchaseRequestItem }],
        }}
        onFinish={handleFinish}
      >
        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)]">
          <div className="grid gap-4 border-b border-[var(--color-hairline)] bg-[var(--color-surface-soft)] px-4 py-4 md:grid-cols-3">
            <Form.Item
              name="request_department"
              label="申购部门"
              className="mb-0"
              rules={[{ required: true, message: '请输入申购部门' }]}
            >
              <Input placeholder="例如：102一车间" />
            </Form.Item>
            <Form.Item
              name="request_date"
              label="申请日期（年 / 月 / 日）"
              className="mb-0"
              rules={[{ required: true, message: '请选择申请日期' }]}
            >
              <DatePicker className="w-full" format="YYYY年MM月DD日" />
            </Form.Item>
            <div className="flex items-end">
              <div className="pb-1 text-[14px] text-[var(--color-charcoal)]">
                分类：<span className="font-semibold">{categoryLabel}</span>
              </div>
            </div>
          </div>

          <div className="p-4">
            <Form.List name="items">
              {(fields, { add, remove }) => {
                const editableRows = fields.map((field) => ({
                  key: field.key,
                  name: field.name,
                }))
                const editableColumns: TableProps<EditableItemRow>['columns'] = [
                  {
                    title: '序号',
                    key: 'sequence',
                    width: 64,
                    render: (_, __, index) => index + 1,
                  },
                  {
                    title: '商品名称',
                    key: 'product_name',
                    width: 160,
                    render: (_, row) => (
                      <Form.Item
                        name={[row.name, 'product_name']}
                        rules={[{ required: true, message: '请输入商品名称' }]}
                        className="mb-0"
                      >
                        <Input />
                      </Form.Item>
                    ),
                  },
                  {
                    title: '规格',
                    key: 'specification',
                    width: 130,
                    render: (_, row) => (
                      <Form.Item name={[row.name, 'specification']} className="mb-0">
                        <Input />
                      </Form.Item>
                    ),
                  },
                  {
                    title: '用途',
                    key: 'purpose',
                    width: 160,
                    render: (_, row) => (
                      <Form.Item name={[row.name, 'purpose']} className="mb-0">
                        <Input />
                      </Form.Item>
                    ),
                  },
                  {
                    title: '材质',
                    key: 'material',
                    width: 110,
                    render: (_, row) => (
                      <Form.Item name={[row.name, 'material']} className="mb-0">
                        <Input />
                      </Form.Item>
                    ),
                  },
                  {
                    title: '品牌',
                    key: 'brand',
                    width: 110,
                    render: (_, row) => (
                      <Form.Item name={[row.name, 'brand']} className="mb-0">
                        <Input />
                      </Form.Item>
                    ),
                  },
                  {
                    title: '数量',
                    key: 'quantity',
                    width: 110,
                    render: (_, row) => (
                      <Form.Item
                        name={[row.name, 'quantity']}
                        rules={[{ required: true, message: '请输入数量' }]}
                        className="mb-0"
                      >
                        <InputNumber className="w-full" min={0} precision={4} />
                      </Form.Item>
                    ),
                  },
                  {
                    title: '单位',
                    key: 'unit',
                    width: 90,
                    render: (_, row) => (
                      <Form.Item name={[row.name, 'unit']} className="mb-0">
                        <Input />
                      </Form.Item>
                    ),
                  },
                  {
                    title: '单价（元）',
                    key: 'unit_price',
                    width: 120,
                    render: (_, row) => (
                      <Form.Item
                        name={[row.name, 'unit_price']}
                        rules={[{ required: true, message: '请输入单价' }]}
                        className="mb-0"
                      >
                        <InputNumber className="w-full" min={0} precision={4} />
                      </Form.Item>
                    ),
                  },
                  {
                    title: '总额（元）',
                    key: 'total_amount',
                    width: 120,
                    render: (_, row) => {
                      const item = watchedItems[row.name]
                      return (
                        <span className="font-medium text-[var(--color-charcoal)]">
                          {formatMoney(calculateLineAmount(item?.quantity, item?.unit_price))}
                        </span>
                      )
                    },
                  },
                  {
                    title: '备注',
                    key: 'remarks',
                    width: 180,
                    render: (_, row) => (
                      <Form.Item name={[row.name, 'remarks']} className="mb-0">
                        <Input />
                      </Form.Item>
                    ),
                  },
                  {
                    title: '',
                    key: 'actions',
                    width: 70,
                    fixed: 'right',
                    render: (_, row) => (
                      <Button
                        danger
                        type="text"
                        icon={<DeleteOutlined />}
                        disabled={fields.length <= 1}
                        onClick={() => remove(row.name)}
                      />
                    ),
                  },
                ]

                return (
                  <div className="space-y-3">
                    <Table
                      columns={editableColumns}
                      dataSource={editableRows}
                      rowKey="key"
                      pagination={false}
                      bordered
                      scroll={{ x: 1370 }}
                      summary={() => (
                        <Table.Summary.Row>
                          <Table.Summary.Cell index={0} colSpan={9}>
                            <span className="font-semibold">合计</span>
                          </Table.Summary.Cell>
                          <Table.Summary.Cell index={9}>
                            <span className="font-semibold">{formatMoney(totalAmount)}</span>
                          </Table.Summary.Cell>
                          <Table.Summary.Cell index={10} colSpan={2} />
                        </Table.Summary.Row>
                      )}
                    />
                    <Button
                      icon={<PlusOutlined />}
                      onClick={() => add({ ...defaultPurchaseRequestItem })}
                    >
                      新增明细
                    </Button>
                  </div>
                )
              }}
            </Form.List>
          </div>
        </section>

        <div className="flex justify-end gap-3">
          <Button onClick={resetForm}>重置</Button>
          <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>
            {editingId ? '更新申请' : '保存申请'}
          </Button>
        </div>
      </Form>

      <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-6">
        <div className="mb-4 flex items-center justify-between gap-4">
          <h2 className="text-[18px] font-semibold text-[var(--color-charcoal)]">申请记录</h2>
          <Button loading={loading} onClick={() => loadRecords(page)}>
            刷新
          </Button>
        </div>
        <Table
          columns={recordColumns}
          dataSource={records}
          rowKey="id"
          loading={loading}
          scroll={{ x: 900 }}
          pagination={{
            current: page,
            pageSize: DEFAULT_PAGE_SIZE,
            total,
            showSizeChanger: false,
            showTotal: (value) => `共 ${value} 条`,
            onChange: (nextPage) => loadRecords(nextPage),
          }}
        />
      </section>

      <Modal
        title="采购申请详情"
        open={Boolean(detailRecord)}
        footer={null}
        width={1100}
        onCancel={() => setDetailRecord(null)}
      >
        {detailRecord && (
          <div className="space-y-4">
            <Descriptions bordered size="small" column={3}>
              <Descriptions.Item label="分类">{categoryLabel}</Descriptions.Item>
              <Descriptions.Item label="申购部门">
                {detailRecord.request_department}
              </Descriptions.Item>
              <Descriptions.Item label="申请日期">
                {dayjs(detailRecord.request_date).format('YYYY-MM-DD')}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={purchaseStatusColors[detailRecord.status]}>
                  {purchaseStatusLabels[detailRecord.status]}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="合计">
                {formatMoney(detailRecord.total_amount)}
              </Descriptions.Item>
            </Descriptions>
            <Table
              columns={detailItemColumns}
              dataSource={detailRecord.items ?? []}
              rowKey="id"
              pagination={false}
              bordered
              scroll={{ x: 1350 }}
            />
            <Table
              columns={approvalColumns}
              dataSource={detailRecord.approvals ?? []}
              rowKey="id"
              pagination={false}
              locale={{ emptyText: '暂无审批记录' }}
            />
          </div>
        )}
      </Modal>
    </div>
  )
}
