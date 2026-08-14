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
  Select,
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
  normalPurchaseCategories,
  purchaseCategoryLabels,
  purchaseStatusColors,
  purchaseStatusLabels,
  usesMaterialFields,
} from './purchaseRequestConstants'
import type { PurchaseRequestFormClientProps } from './PurchaseRequestFormClient'
import { MaterialCodeAutocomplete } from './MaterialCodeAutocomplete'

type UrgentGroup = {
  category: PurchaseRequestCategory
  items: PurchaseRequestItemInput[]
}

export type UrgentFormValues = {
  request_department: string
  request_date: Dayjs
  attachment_note: string
  groups: UrgentGroup[]
}

type EditableItemRow = {
  key: number
  name: number
}

type PurchaseRequestItemResponse = NonNullable<PurchaseRequestResponse['items']>[number]

const DEFAULT_PAGE_SIZE = 20

function normalizeItem(item: PurchaseRequestItemResponse): PurchaseRequestItemInput {
  return {
    product_name: item.product_name,
    specification: item.specification,
    material_code: item.material_code,
    material_description: item.material_description,
    rule_model: item.rule_model,
    purpose: item.purpose,
    material: item.material,
    brand: item.brand,
    quantity: item.quantity,
    unit: item.unit,
    unit_price: item.unit_price,
    remarks: item.remarks,
  }
}

export function normalizeGroups(record: PurchaseRequestResponse): UrgentGroup[] {
  const groups = new Map<PurchaseRequestCategory, PurchaseRequestItemInput[]>()
  for (const item of record.items ?? []) {
    const itemCategory = item.item_category
    if (!itemCategory || itemCategory === 'urgent') continue
    const items = groups.get(itemCategory) ?? []
    items.push(normalizeItem(item))
    groups.set(itemCategory, items)
  }
  return Array.from(groups.entries()).map(([category, items]) => ({ category, items }))
}

function trimItem(item: PurchaseRequestItemInput, category: PurchaseRequestCategory) {
  return {
    ...item,
    item_category: category,
    product_name: item.product_name?.trim() ?? '',
    specification: item.specification?.trim() ?? '',
    material_code: item.material_code?.trim() ?? '',
    material_description: item.material_description?.trim() ?? '',
    rule_model: item.rule_model?.trim() ?? '',
    purpose: item.purpose?.trim() ?? '',
    material: item.material?.trim() ?? '',
    brand: item.brand?.trim() ?? '',
    unit: item.unit?.trim() ?? '',
    remarks: item.remarks?.trim() ?? '',
  }
}

export function buildUrgentPurchasePayload(
  values: UrgentFormValues,
  category: PurchaseRequestCategory = 'urgent',
) {
  return {
    category,
    request_department: values.request_department,
    request_date: values.request_date.format('YYYY-MM-DD'),
    attachment_note: values.attachment_note?.trim() ?? '',
    items: values.groups.flatMap((group) =>
      group.items.map((item) => trimItem(item, group.category))
    ),
  }
}

export function itemDetailColumns(isUrgent: boolean, category: PurchaseRequestCategory) {
  if (isUrgent) {
    return [
      { title: '序号', dataIndex: 'sequence', key: 'sequence', width: 70 },
      {
        title: '申请类型',
        dataIndex: 'item_category',
        key: 'item_category',
        width: 130,
        render: (value: PurchaseRequestCategory) => purchaseCategoryLabels[value] ?? value,
      },
      {
        title: '物料编码/商品名称',
        key: 'material_code_compatibility',
        width: 180,
        render: (_: unknown, item: PurchaseRequestItemResponse) =>
          item.material_code || item.product_name,
      },
      {
        title: '物料说明/商品名称',
        key: 'material_description_compatibility',
        width: 190,
        render: (_: unknown, item: PurchaseRequestItemResponse) =>
          item.material_description || item.product_name,
      },
      {
        title: '规格型号',
        key: 'rule_model_compatibility',
        width: 170,
        render: (_: unknown, item: PurchaseRequestItemResponse) =>
          item.rule_model || item.specification,
      },
    ]
  }

  return [
    { title: '序号', dataIndex: 'sequence', key: 'sequence', width: 70 },
    ...(usesMaterialFields(category)
      ? [
          { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 150 },
          { title: '物料说明', dataIndex: 'material_description', key: 'material_description', width: 180 },
          { title: '规格型号', dataIndex: 'rule_model', key: 'rule_model', width: 150 },
        ]
      : [
          { title: '商品名称', dataIndex: 'product_name', key: 'product_name', width: 160 },
          { title: '规格', dataIndex: 'specification', key: 'specification', width: 120 },
        ]),
  ]
}

export function UrgentPurchaseRequestFormClient({
  category,
  categoryLabel,
  initialRequests,
  initialTotal,
}: PurchaseRequestFormClientProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<UrgentFormValues>()
  const [records, setRecords] = useState(initialRequests)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [submittingId, setSubmittingId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [detailRecord, setDetailRecord] = useState<PurchaseRequestResponse | null>(null)
  const [attachmentNoteOpen, setAttachmentNoteOpen] = useState(false)
  const [attachmentNoteDraft, setAttachmentNoteDraft] = useState('')
  const [categoryPickerOpen, setCategoryPickerOpen] = useState(false)
  const [categoryToAdd, setCategoryToAdd] = useState<PurchaseRequestCategory | undefined>()
  const watchedGroupsValue = Form.useWatch('groups', form)
  const watchedGroups = useMemo(() => watchedGroupsValue ?? [], [watchedGroupsValue])
  const watchedAttachmentNote = Form.useWatch('attachment_note', form) ?? ''

  const totalAmount = useMemo(
    () =>
      watchedGroups.reduce(
        (sum, group) =>
          sum +
          (group?.items ?? []).reduce(
            (groupSum, item) =>
              groupSum + calculateLineAmount(item?.quantity, item?.unit_price),
            0
          ),
        0
      ),
    [watchedGroups]
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
      attachment_note: '',
      groups: [],
    })
  }

  const handleFinish = async (values: UrgentFormValues) => {
    if (!values.groups?.length || values.groups.some((group) => !group.items?.length)) {
      message.error('加急单至少需要添加一个申请类型和一条明细')
      return
    }

    setSaving(true)
    try {
      const payload = buildUrgentPurchasePayload(values, category)
      const response = editingId
        ? await updatePurchaseRequest(editingId, {
            request_department: payload.request_department,
            request_date: payload.request_date,
            attachment_note: payload.attachment_note,
            items: payload.items,
          })
        : await createPurchaseRequest(payload)

      if (response.code !== 200) {
        message.error(response.message || '采购申请保存失败')
        return
      }
      message.success(editingId ? '加急申请已更新' : '加急申请已保存')
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
      attachment_note: record.attachment_note ?? '',
      groups: normalizeGroups(record),
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
    { title: '申请日期', dataIndex: 'request_date', key: 'request_date', width: 130 },
    { title: '申购部门', dataIndex: 'request_department', key: 'request_department', width: 180, ellipsis: true },
    { title: '合计', dataIndex: 'total_amount', key: 'total_amount', width: 120, render: (value: string | number) => formatMoney(value) },
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
            <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => setDetailRecord(record)}>查看</Button>
            {editable && <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>}
            {editable && (
              <Popconfirm
                title="确认提交到部门负责人审批？"
                okText="提交"
                cancelText="取消"
                onConfirm={() => handleSubmitFlow(record)}
              >
                <Button type="link" size="small" icon={<SendOutlined />} loading={submittingId === record.id}>提交</Button>
              </Popconfirm>
            )}
          </Space>
        )
      },
    },
  ]

  const detailColumns = [
    ...itemDetailColumns(true, category),
    { title: '用途', dataIndex: 'purpose', key: 'purpose', width: 160 },
    { title: '材质', dataIndex: 'material', key: 'material', width: 100 },
    { title: '品牌', dataIndex: 'brand', key: 'brand', width: 100 },
    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 90 },
    { title: '单位', dataIndex: 'unit', key: 'unit', width: 80 },
    { title: '单价（元）', dataIndex: 'unit_price', key: 'unit_price', width: 110, render: (value: string | number) => formatMoney(value) },
    { title: '总额（元）', dataIndex: 'total_amount', key: 'total_amount', width: 110, render: (value: string | number) => formatMoney(value) },
    { title: '备注', dataIndex: 'remarks', key: 'remarks', width: 180 },
  ]

  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">采购管理 / 采购申请</p>
        <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">{categoryLabel}采购申请</h1>
      </div>

      <Form
        form={form}
        layout="vertical"
        initialValues={{ request_date: dayjs(), attachment_note: '', groups: [] }}
        onFinish={handleFinish}
      >
        <Form.Item name="attachment_note" hidden><Input /></Form.Item>
        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)]">
          <div className="grid gap-4 border-b border-[var(--color-hairline)] bg-[var(--color-surface-soft)] px-4 py-4 md:grid-cols-3">
            <Form.Item name="request_department" label="申购部门" className="mb-0" rules={[{ required: true, message: '请输入申购部门' }]}>
              <Input placeholder="例如：102一车间" />
            </Form.Item>
            <Form.Item name="request_date" label="申请日期（年 / 月 / 日）" className="mb-0" rules={[{ required: true, message: '请选择申请日期' }]}>
              <DatePicker className="w-full" format="YYYY年MM月DD日" />
            </Form.Item>
            <div className="flex items-end"><div className="pb-1 text-[14px] text-[var(--color-charcoal)]">分类：<span className="font-semibold">{categoryLabel}</span></div></div>
            <div className="flex items-end gap-3 md:col-span-3">
              <Button onClick={() => { setAttachmentNoteDraft(watchedAttachmentNote); setAttachmentNoteOpen(true) }}>
                附件说明{watchedAttachmentNote.trim() ? '（已填写）' : ''}
              </Button>
              <span className="text-[13px] text-[var(--color-stone)]">可添加多个申请类型，每类类型只能添加一个分组</span>
            </div>
          </div>

          <div className="space-y-4 p-4">
            <Form.List name="groups">
              {(groupFields, { add, remove: removeGroup }) => (
                <>
                  {groupFields.map((groupField, groupIndex) => {
                    const group = watchedGroups[groupIndex]
                    const groupValue = form.getFieldValue(['groups', groupField.name]) as
                      | UrgentGroup
                      | undefined
                    const groupCategory = (groupValue?.category ?? group?.category) as
                      | PurchaseRequestCategory
                      | undefined
                    if (!groupCategory || groupCategory === 'urgent') return null
                    const materialFields = usesMaterialFields(groupCategory)

                    return (
                      <section key={groupField.key} className="rounded-[10px] border border-[var(--color-hairline)] bg-[var(--color-surface-soft)] p-3">
                        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <Tag color="processing">申请类型</Tag>
                            <span className="font-semibold text-[var(--color-charcoal)]">{purchaseCategoryLabels[groupCategory]}</span>
                            <Form.Item name={[groupField.name, 'category']} hidden><Input /></Form.Item>
                          </div>
                          <Popconfirm title="删除该申请类型分组？" okText="删除" cancelText="取消" onConfirm={() => removeGroup(groupField.name)}>
                            <Button danger type="text" icon={<DeleteOutlined />}>删除类型</Button>
                          </Popconfirm>
                        </div>
                        <Form.List name={[groupField.name, 'items']}>
                          {(itemFields, { add: addItem, remove: removeItem }) => {
                            const editableRows = itemFields.map((field) => ({ key: field.key, name: field.name }))
                            const path = (rowName: number, key: string) => [groupField.name, 'items', rowName, key]
                            type LinkedFieldPath =
                              | ['groups', number, 'items', number, 'material_description']
                              | ['groups', number, 'items', number, 'rule_model']
                            const rootPath = (
                              rowName: number,
                              key: 'material_description' | 'rule_model',
                            ): LinkedFieldPath =>
                              ['groups', groupField.name, 'items', rowName, key] as LinkedFieldPath
                            const columns: TableProps<EditableItemRow>['columns'] = [
                              { title: '序号', key: 'sequence', width: 64, render: (_, __, index) => index + 1 },
                              ...(materialFields
                                ? [
                                    {
                                      title: '物料编码',
                                      key: 'material_code',
                                      width: 150,
                                      render: (_: unknown, row: EditableItemRow) => (
                                        <Form.Item
                                          name={path(row.name, 'material_code')}
                                          rules={[{ required: true, message: '请输入物料编码' }]}
                                          className="mb-0"
                                        >
                                          <MaterialCodeAutocomplete
                                            onUserChange={() => {
                                              form.setFieldValue(
                                                rootPath(row.name, 'material_description'),
                                                '',
                                              )
                                              form.setFieldValue(
                                                rootPath(row.name, 'rule_model'),
                                                '',
                                              )
                                            }}
                                            onSelectMaterial={(option) => {
                                              form.setFieldValue(
                                                rootPath(row.name, 'material_description'),
                                                option.material_description,
                                              )
                                              form.setFieldValue(
                                                rootPath(row.name, 'rule_model'),
                                                option.rule_model,
                                              )
                                            }}
                                          />
                                        </Form.Item>
                                      ),
                                    },
                                    { title: '物料说明', key: 'material_description', width: 180, render: (_: unknown, row: EditableItemRow) => <Form.Item name={path(row.name, 'material_description')} rules={[{ required: true, message: '请输入物料说明' }]} className="mb-0"><Input /></Form.Item> },
                                    { title: '规格型号', key: 'rule_model', width: 150, render: (_: unknown, row: EditableItemRow) => <Form.Item name={path(row.name, 'rule_model')} className="mb-0"><Input /></Form.Item> },
                                  ]
                                : [
                                    { title: '商品名称', key: 'product_name', width: 160, render: (_: unknown, row: EditableItemRow) => <Form.Item name={path(row.name, 'product_name')} rules={[{ required: true, message: '请输入商品名称' }]} className="mb-0"><Input /></Form.Item> },
                                    { title: '规格', key: 'specification', width: 130, render: (_: unknown, row: EditableItemRow) => <Form.Item name={path(row.name, 'specification')} className="mb-0"><Input /></Form.Item> },
                                  ]),
                              { title: '用途', key: 'purpose', width: 160, render: (_, row) => <Form.Item name={path(row.name, 'purpose')} className="mb-0"><Input /></Form.Item> },
                              { title: '材质', key: 'material', width: 110, render: (_, row) => <Form.Item name={path(row.name, 'material')} className="mb-0"><Input /></Form.Item> },
                              { title: '品牌', key: 'brand', width: 110, render: (_, row) => <Form.Item name={path(row.name, 'brand')} className="mb-0"><Input /></Form.Item> },
                              { title: '数量', key: 'quantity', width: 110, render: (_, row) => <Form.Item name={path(row.name, 'quantity')} rules={[{ required: true, message: '请输入数量' }]} className="mb-0"><InputNumber className="w-full" min={0} precision={4} /></Form.Item> },
                              { title: '单位', key: 'unit', width: 90, render: (_, row) => <Form.Item name={path(row.name, 'unit')} className="mb-0"><Input /></Form.Item> },
                              { title: '单价（元）', key: 'unit_price', width: 120, render: (_, row) => <Form.Item name={path(row.name, 'unit_price')} rules={[{ required: true, message: '请输入单价' }]} className="mb-0"><InputNumber className="w-full" min={0} precision={4} /></Form.Item> },
                              { title: '总额（元）', key: 'total_amount', width: 120, render: (_, row) => <span className="font-medium text-[var(--color-charcoal)]">{formatMoney(calculateLineAmount(watchedGroups[groupIndex]?.items?.[row.name]?.quantity, watchedGroups[groupIndex]?.items?.[row.name]?.unit_price))}</span> },
                              { title: '备注', key: 'remarks', width: 180, render: (_, row) => <Form.Item name={path(row.name, 'remarks')} className="mb-0"><Input /></Form.Item> },
                              { title: '', key: 'actions', width: 70, fixed: 'right', render: (_, row) => <Button danger type="text" icon={<DeleteOutlined />} disabled={itemFields.length <= 1} onClick={() => removeItem(row.name)} /> },
                            ]
                            const fixedColumns = materialFields ? 10 : 9
                            return (
                              <div className="space-y-3">
                                <Table columns={columns} dataSource={editableRows} rowKey="key" pagination={false} bordered scroll={{ x: materialFields ? 1570 : 1370 }} summary={() => <Table.Summary.Row><Table.Summary.Cell index={0} colSpan={fixedColumns}><span className="font-semibold">分组小计</span></Table.Summary.Cell><Table.Summary.Cell index={fixedColumns}><span className="font-semibold">{formatMoney((watchedGroups[groupIndex]?.items ?? []).reduce((sum, item) => sum + calculateLineAmount(item?.quantity, item?.unit_price), 0))}</span></Table.Summary.Cell><Table.Summary.Cell index={fixedColumns + 1} colSpan={2} /></Table.Summary.Row>} />
                                <Button icon={<PlusOutlined />} onClick={() => addItem({ ...defaultPurchaseRequestItem })}>新增明细</Button>
                              </div>
                            )
                          }}
                        </Form.List>
                      </section>
                    )
                  })}
                  <Button
                    type="dashed"
                    icon={<PlusOutlined />}
                    onClick={() => { setCategoryToAdd(undefined); setCategoryPickerOpen(true) }}
                  >
                    添加申请类型
                  </Button>
                  <Modal
                    title="添加申请类型"
                    open={categoryPickerOpen}
                    okText="添加"
                    cancelText="取消"
                    onOk={() => {
                      if (!categoryToAdd) { message.error('请选择申请类型'); return }
                      if (watchedGroups.some((group) => group?.category === categoryToAdd)) { message.error('同一申请类型只能添加一个分组'); return }
                      add({ category: categoryToAdd, items: [{ ...defaultPurchaseRequestItem }] })
                      setCategoryPickerOpen(false)
                      setCategoryToAdd(undefined)
                    }}
                    onCancel={() => setCategoryPickerOpen(false)}
                  >
                    <Select className="w-full" placeholder="请选择申请类型" value={categoryToAdd} onChange={setCategoryToAdd} options={normalPurchaseCategories.filter((item) => !watchedGroups.some((group) => group?.category === item)).map((item) => ({ label: purchaseCategoryLabels[item], value: item }))} />
                  </Modal>
                </>
              )}
            </Form.List>
            <div className="flex justify-end border-t border-[var(--color-hairline-soft)] pt-3 text-[16px] font-semibold">合计：{formatMoney(totalAmount)}</div>
          </div>
        </section>

        <div className="flex justify-end gap-3">
          <Button onClick={resetForm}>重置</Button>
          <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>{editingId ? '更新申请' : '保存申请'}</Button>
        </div>
      </Form>

      <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-6">
        <div className="mb-4 flex items-center justify-between gap-4"><h2 className="text-[18px] font-semibold text-[var(--color-charcoal)]">申请记录</h2><Button loading={loading} onClick={() => loadRecords(page)}>刷新</Button></div>
        <Table columns={recordColumns} dataSource={records} rowKey="id" loading={loading} scroll={{ x: 900 }} pagination={{ current: page, pageSize: DEFAULT_PAGE_SIZE, total, showSizeChanger: false, showTotal: (value) => `共 ${value} 条`, onChange: (nextPage) => loadRecords(nextPage) }} />
      </section>

      <Modal title="采购申请详情" open={Boolean(detailRecord)} footer={null} width={1250} onCancel={() => setDetailRecord(null)}>
        {detailRecord && <div className="space-y-4">
          <Descriptions bordered size="small" column={3}>
            <Descriptions.Item label="分类">{categoryLabel}</Descriptions.Item>
            <Descriptions.Item label="申购部门">{detailRecord.request_department}</Descriptions.Item>
            <Descriptions.Item label="申请日期">{dayjs(detailRecord.request_date).format('YYYY-MM-DD')}</Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color={purchaseStatusColors[detailRecord.status]}>{purchaseStatusLabels[detailRecord.status]}</Tag></Descriptions.Item>
            <Descriptions.Item label="合计">{formatMoney(detailRecord.total_amount)}</Descriptions.Item>
            <Descriptions.Item label="附件说明" span={3}><span className="whitespace-pre-wrap">{detailRecord.attachment_note || '无'}</span></Descriptions.Item>
          </Descriptions>
          <Table columns={detailColumns} dataSource={detailRecord.items ?? []} rowKey="id" pagination={false} bordered scroll={{ x: 1550 }} />
        </div>}
      </Modal>

      <Modal title="附件说明" open={attachmentNoteOpen} okText="保存说明" cancelText="取消" onOk={() => { form.setFieldValue('attachment_note', attachmentNoteDraft.trim()); setAttachmentNoteOpen(false) }} onCancel={() => setAttachmentNoteOpen(false)}>
        <Input.TextArea value={attachmentNoteDraft} onChange={(event) => setAttachmentNoteDraft(event.target.value)} placeholder="请输入附件内容、份数或其他说明" rows={6} maxLength={4000} showCount />
      </Modal>
    </div>
  )
}
