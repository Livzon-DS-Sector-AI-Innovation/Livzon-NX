'use client'

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react'
import { App, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { createOotLimitItem, createOotLimitProduct, deleteOotLimitItem, deleteOotLimitProduct, updateOotLimitItem, updateOotLimitProduct } from '@/actions/quality'
import { fetchOotLimitItems, fetchOotLimitProducts } from '@/lib/api/client/quality'

interface OotLimitProduct {
  id: string
  product_code: string
  product_name: string
  document_title: string
  document_year: number | null
  version_label: string | null
  source_file_name: string | null
  remark: string | null
}

interface OotLimitItem {
  id: string
  product_id: string
  display_order: number
  item_group: string | null
  item_name: string
  standard_value: string
  oot_limit_value: string
  remark: string | null
}

interface ProductFormValues {
  product_code: string
  product_name: string
  document_title: string
  document_year: number | null
  version_label: string
  source_file_name: string
  remark: string
}

interface ItemFormValues {
  display_order: number | null
  item_group: string
  item_name: string
  standard_value: string
  oot_limit_value: string
  remark: string
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function normalizeText(value: string | null | undefined): string {
  return value?.trim() || ''
}

const cellStyle: CSSProperties = {
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  verticalAlign: 'top',
}

export default function OotLimitManagementPage() {
  const { message } = App.useApp()
  const [products, setProducts] = useState<OotLimitProduct[]>([])
  const [items, setItems] = useState<OotLimitItem[]>([])
  const [loadingProducts, setLoadingProducts] = useState(false)
  const [loadingItems, setLoadingItems] = useState(false)
  const [savingProduct, setSavingProduct] = useState(false)
  const [savingItem, setSavingItem] = useState(false)
  const [selectedProductId, setSelectedProductId] = useState<string>()
  const [itemSearchKeyword, setItemSearchKeyword] = useState('')
  const [productModalVisible, setProductModalVisible] = useState(false)
  const [itemModalVisible, setItemModalVisible] = useState(false)
  const [editingProduct, setEditingProduct] = useState<OotLimitProduct | null>(null)
  const [editingItem, setEditingItem] = useState<OotLimitItem | null>(null)
  const [productForm] = Form.useForm<ProductFormValues>()
  const [itemForm] = Form.useForm<ItemFormValues>()

  const selectedProduct = useMemo(
    () => products.find((product) => product.id === selectedProductId) ?? null,
    [products, selectedProductId]
  )

  const loadProducts = useCallback(
    async (preferredProductId?: string) => {
      try {
        setLoadingProducts(true)
        const result = await fetchOotLimitProducts({ page: 1, page_size: 200 })
        const list = (result.data ?? []) as OotLimitProduct[]
        setProducts(list)

        if (list.length === 0) {
          setSelectedProductId(undefined)
          setItems([])
          return
        }

        setSelectedProductId((currentSelectedId) => {
          if (preferredProductId && list.some((item) => item.id === preferredProductId)) {
            return preferredProductId
          }
          if (currentSelectedId && list.some((item) => item.id === currentSelectedId)) {
            return currentSelectedId
          }
          return list[0].id
        })
      } catch (error: unknown) {
        message.error(getErrorMessage(error, '加载OOT限度产品失败'))
      } finally {
        setLoadingProducts(false)
      }
    },
    [message]
  )

  const loadItems = useCallback(
    async (productId?: string) => {
      if (!productId) {
        setItems([])
        return
      }
      try {
        setLoadingItems(true)
        const result = await fetchOotLimitItems({ product_id: productId, page: 1, page_size: 500 })
        setItems((result.data ?? []) as OotLimitItem[])
      } catch (error: unknown) {
        message.error(getErrorMessage(error, '加载OOT限度明细失败'))
      } finally {
        setLoadingItems(false)
      }
    },
    [message]
  )

  useEffect(() => {
    void loadProducts()
  }, [loadProducts])

  useEffect(() => {
    void loadItems(selectedProductId)
  }, [loadItems, selectedProductId])

  const openCreateProduct = useCallback(() => {
    setEditingProduct(null)
    productForm.resetFields()
    productForm.setFieldsValue({ document_year: 2026 })
    setProductModalVisible(true)
  }, [productForm])

  const openEditProduct = useCallback(() => {
    if (!selectedProduct) {
      message.warning('请先选择产品')
      return
    }
    setEditingProduct(selectedProduct)
    productForm.setFieldsValue({
      product_code: selectedProduct.product_code,
      product_name: selectedProduct.product_name,
      document_title: selectedProduct.document_title,
      document_year: selectedProduct.document_year,
      version_label: selectedProduct.version_label ?? '',
      source_file_name: selectedProduct.source_file_name ?? '',
      remark: selectedProduct.remark ?? '',
    })
    setProductModalVisible(true)
  }, [message, productForm, selectedProduct])

  const closeProductModal = useCallback(() => {
    setProductModalVisible(false)
    setEditingProduct(null)
    productForm.resetFields()
  }, [productForm])

  const openCreateItem = useCallback(() => {
    if (!selectedProductId) {
      message.warning('请先选择产品')
      return
    }
    setEditingItem(null)
    itemForm.resetFields()
    itemForm.setFieldsValue({ display_order: items.length + 1 })
    setItemModalVisible(true)
  }, [itemForm, items.length, message, selectedProductId])

  const openEditItem = useCallback((record: OotLimitItem) => {
    setEditingItem(record)
    itemForm.setFieldsValue({
      display_order: record.display_order,
      item_group: record.item_group ?? '',
      item_name: record.item_name,
      standard_value: record.standard_value,
      oot_limit_value: record.oot_limit_value,
      remark: record.remark ?? '',
    })
    setItemModalVisible(true)
  }, [itemForm])

  const closeItemModal = useCallback(() => {
    setItemModalVisible(false)
    setEditingItem(null)
    itemForm.resetFields()
  }, [itemForm])

  const handleSubmitProduct = useCallback(async () => {
    const values = await productForm.validateFields()
    try {
      setSavingProduct(true)
      const payload = {
        product_code: normalizeText(values.product_code),
        product_name: normalizeText(values.product_name),
        document_title: normalizeText(values.document_title),
        document_year: values.document_year ?? null,
        version_label: normalizeText(values.version_label) || null,
        source_file_name: normalizeText(values.source_file_name) || null,
        remark: normalizeText(values.remark) || null,
      }

      if (editingProduct) {
        const updated: any = await updateOotLimitProduct(editingProduct.id, payload)
        message.success('OOT限度产品已更新')
        closeProductModal()
        await loadProducts(updated?.id || editingProduct.id)
      } else {
        const created: any = await createOotLimitProduct(payload)
        message.success('OOT限度产品已创建')
        closeProductModal()
        await loadProducts(created?.id)
      }
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存OOT限度产品失败'))
    } finally {
      setSavingProduct(false)
    }
  }, [closeProductModal, editingProduct, loadProducts, message, productForm])

  const handleDeleteProduct = useCallback(async () => {
    if (!selectedProduct) {
      message.warning('请先选择产品')
      return
    }
    try {
      await deleteOotLimitProduct(selectedProduct.id)
      message.success('OOT限度产品已删除')
      await loadProducts()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除OOT限度产品失败'))
    }
  }, [loadProducts, message, selectedProduct])

  const handleSubmitItem = useCallback(async () => {
    if (!selectedProductId) {
      message.warning('请先选择产品')
      return
    }
    const values = await itemForm.validateFields()
    try {
      setSavingItem(true)
      const payload = {
        product_id: selectedProductId,
        display_order: values.display_order ?? 1,
        item_group: normalizeText(values.item_group) || null,
        item_name: normalizeText(values.item_name),
        standard_value: normalizeText(values.standard_value),
        oot_limit_value: normalizeText(values.oot_limit_value),
        remark: normalizeText(values.remark) || null,
      }

      if (editingItem) {
        await updateOotLimitItem(editingItem.id, payload)
        message.success('OOT限度明细已更新')
      } else {
        await createOotLimitItem(payload)
        message.success('OOT限度明细已创建')
      }

      closeItemModal()
      await loadItems(selectedProductId)
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存OOT限度明细失败'))
    } finally {
      setSavingItem(false)
    }
  }, [closeItemModal, editingItem, itemForm, loadItems, message, selectedProductId])

  const handleDeleteItem = useCallback(
    async (itemId: string) => {
      try {
        await deleteOotLimitItem(itemId)
        message.success('OOT限度明细已删除')
        await loadItems(selectedProductId)
      } catch (error: unknown) {
        message.error(getErrorMessage(error, '删除OOT限度明细失败'))
      }
    },
    [loadItems, message, selectedProductId]
  )

  const filteredItems = useMemo(() => {
    if (!itemSearchKeyword.trim()) return items
    const keyword = itemSearchKeyword.toLowerCase()
    return items.filter((item) =>
      [item.item_group, item.item_name, item.standard_value, item.oot_limit_value, item.remark]
        .some((value) => (value ?? '').toLowerCase().includes(keyword))
    )
  }, [itemSearchKeyword, items])

  const productOptions = useMemo(
    () =>
      products.map((product) => ({
        label: `${product.product_code} - ${product.product_name}${product.version_label ? `（${product.version_label}）` : ''}`,
        value: product.id,
      })),
    [products]
  )

  const columns: ColumnsType<OotLimitItem> = [
    {
      title: '序号',
      dataIndex: 'display_order',
      key: 'display_order',
      width: 70,
      onCell: () => ({ style: cellStyle }),
    },
    {
      title: '一级项目',
      dataIndex: 'item_group',
      key: 'item_group',
      width: 140,
      render: (value: string | null) => value || '-',
      onCell: () => ({ style: cellStyle }),
    },
    {
      title: '项目',
      dataIndex: 'item_name',
      key: 'item_name',
      width: 180,
      onCell: () => ({ style: cellStyle }),
    },
    {
      title: '标准',
      dataIndex: 'standard_value',
      key: 'standard_value',
      width: 220,
      onCell: () => ({ style: cellStyle }),
    },
    {
      title: 'OOT限度',
      dataIndex: 'oot_limit_value',
      key: 'oot_limit_value',
      width: 220,
      onCell: () => ({ style: cellStyle }),
    },
    {
      title: '备注',
      dataIndex: 'remark',
      key: 'remark',
      width: 180,
      render: (value: string | null) => value || '-',
      onCell: () => ({ style: cellStyle }),
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button type="link" onClick={() => openEditItem(record)}>修改</Button>
          <Popconfirm
            title="确认删除这条OOT限度明细？"
            okText="删除"
            cancelText="取消"
            onConfirm={() => void handleDeleteItem(record.id)}
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
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / OOS/OOT管理 / 各产品OOT限度</p>
        <Typography.Title level={3} style={{ margin: 0 }}>各产品OOT限度</Typography.Title>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
          <Space wrap>
            <Select
              showSearch
              placeholder="请选择产品"
              style={{ width: 360 }}
              value={selectedProductId}
              loading={loadingProducts}
              onChange={(value) => setSelectedProductId(value)}
              options={productOptions}
              optionFilterProp="label"
            />
            <Button type="primary" onClick={openCreateProduct}>新增产品</Button>
            <Button onClick={openEditProduct} disabled={!selectedProduct}>修改当前产品</Button>
            <Popconfirm
              title={`确认删除产品“${selectedProduct?.product_name || ''}”？`}
              okText="删除"
              cancelText="取消"
              onConfirm={() => void handleDeleteProduct()}
              disabled={!selectedProduct}
            >
              <Button danger disabled={!selectedProduct}>删除当前产品</Button>
            </Popconfirm>
            <Button type="primary" onClick={openCreateItem} disabled={!selectedProductId}>新增限度明细</Button>
          </Space>
          <Input.Search
            allowClear
            placeholder="搜索一级项目、项目、标准、OOT限度..."
            style={{ width: 320 }}
            value={itemSearchKeyword}
            onChange={(event) => setItemSearchKeyword(event.target.value)}
          />
        </div>

        {selectedProduct ? (
          <div style={{ fontSize: 13, color: 'var(--color-stone)' }}>
            当前产品：{selectedProduct.product_name}
            {selectedProduct.version_label ? `（${selectedProduct.version_label}）` : ''}
            {' · '}
            文件：{selectedProduct.source_file_name || '-'}
            {' · '}
            标题：{selectedProduct.document_title}
          </div>
        ) : (
          <div style={{ fontSize: 13, color: 'var(--color-stone)' }}>当前暂无产品数据，可先新增产品。</div>
        )}
      </Card>

      <Card>
        <Table<OotLimitItem>
          rowKey="id"
          size="small"
          tableLayout="fixed"
          loading={loadingItems}
          columns={columns}
          dataSource={filteredItems}
          pagination={false}
          scroll={{ x: 1150 }}
        />
      </Card>

      <Modal
        title={editingProduct ? '修改OOT限度产品' : '新增OOT限度产品'}
        open={productModalVisible}
        onOk={() => void handleSubmitProduct()}
        onCancel={closeProductModal}
        confirmLoading={savingProduct}
        destroyOnHidden
        width={720}
      >
        <Form form={productForm} layout="vertical">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16 }}>
            <Form.Item name="product_code" label="产品编码" rules={[{ required: true, message: '请输入产品编码' }]}>
              <Input placeholder="如 LV、MV、DLS" />
            </Form.Item>
            <Form.Item name="product_name" label="产品名称" rules={[{ required: true, message: '请输入产品名称' }]}>
              <Input placeholder="请输入产品名称" />
            </Form.Item>
            <Form.Item name="document_year" label="年份">
              <InputNumber style={{ width: '100%' }} placeholder="请输入年份" />
            </Form.Item>
            <Form.Item name="version_label" label="版本标签">
              <Input placeholder="如 高规、内控" />
            </Form.Item>
          </div>
          <Form.Item name="document_title" label="通知单标题" rules={[{ required: true, message: '请输入通知单标题' }]}>
            <Input placeholder="请输入通知单标题" />
          </Form.Item>
          <Form.Item name="source_file_name" label="源文件名">
            <Input placeholder="请输入源文件名" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} placeholder="请输入备注" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingItem ? '修改OOT限度明细' : '新增OOT限度明细'}
        open={itemModalVisible}
        onOk={() => void handleSubmitItem()}
        onCancel={closeItemModal}
        confirmLoading={savingItem}
        destroyOnHidden
        width={760}
      >
        <Form form={itemForm} layout="vertical">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16 }}>
            <Form.Item name="display_order" label="显示顺序" rules={[{ required: true, message: '请输入显示顺序' }]}>
              <InputNumber style={{ width: '100%' }} min={1} precision={0} />
            </Form.Item>
            <Form.Item name="item_group" label="一级项目">
              <Input placeholder="如 有关物质、残留溶剂" />
            </Form.Item>
          </div>
          <Form.Item name="item_name" label="项目" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="请输入项目名称" />
          </Form.Item>
          <Form.Item name="standard_value" label="标准" rules={[{ required: true, message: '请输入标准值' }]}>
            <Input placeholder="请输入标准值" />
          </Form.Item>
          <Form.Item name="oot_limit_value" label="OOT限度" rules={[{ required: true, message: '请输入OOT限度' }]}>
            <Input placeholder="请输入OOT限度" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} placeholder="请输入备注" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
