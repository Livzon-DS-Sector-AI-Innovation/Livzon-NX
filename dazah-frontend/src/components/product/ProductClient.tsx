'use client'

import { useState, useCallback, useEffect } from 'react'
import { App, Table, Input, Select, Tag, Button, Space, Modal, Form } from 'antd'
import { SearchOutlined, SyncOutlined, PlusOutlined, EditOutlined } from '@ant-design/icons'
import { Product } from '@/types/product'
import { fetchProducts, syncProductsFromFeishu } from '@/lib/api/product'
import { createProduct, updateProduct } from '@/actions/product'

interface ProductClientProps {
  initialProducts: Product[]
  initialTotal: number
}

const categoryColorMap: Record<string, string> = {
  'SM': 'blue',
  'FSM': 'cyan'
}

export default function ProductClient({ initialProducts, initialTotal }: ProductClientProps) {
  const { message } = App.useApp()

  const [products, setProducts] = useState<Product[]>(initialProducts)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterType, setFilterType] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editingProduct, setEditingProduct] = useState<Product | null>(null)
  const [form] = Form.useForm()

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchProducts({
        keyword: keyword || undefined,
        category: filterCategory || undefined,
        product_type: filterType || undefined,
        page,
        page_size: pageSize
      })
      setProducts(res.data)
      setTotal(res.meta?.total || 0)
    } catch (err) {
      message.error(err.message || '加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [keyword, filterCategory, filterType, page, pageSize])

  useEffect(() => {
    loadData()
     
  }, [keyword, filterCategory, filterType, page, pageSize, loadData])

  const handlePageChange = (newPage: number, newPageSize: number) => {
    setPage(newPage)
    setPageSize(newPageSize)
  }

  const handleSyncFromFeishu = async () => {
    setSyncing(true)
    try {
      const res = await syncProductsFromFeishu()
      message.success(res.message)
      loadData()
    } catch (err) {
      message.error(err.message || '同步失败')
    } finally {
      setSyncing(false)
    }
  }

  const openCreateModal = () => {
    setEditingProduct(null)
    form.resetFields()
    setModalOpen(true)
  }

  const openEditModal = (product: Product) => {
    setEditingProduct(product)
    form.setFieldsValue({
      name: product.name,
      major_category: product.major_category,
      formulation_code: product.formulation_code,
      product_type: product.product_type,
      spec: product.spec,
      capacity_range: product.capacity_range,
      unit: product.unit,
      indication: product.indication
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      if (editingProduct) {
        await updateProduct(editingProduct.id, values)
        message.success('修改成功')
      } else {
        await createProduct(values)
        message.success('新增成功')
      }
      setModalOpen(false)
      loadData()
    } catch (err) {
      if (err.errorFields) return
      message.error(err.message || '操作失败')
    } finally {
      setSaving(false)
    }
  }

  const categories = Array.from(new Set(products.map((p) => p.major_category).filter(Boolean)))
  const types = Array.from(new Set(products.map((p) => p.product_type).filter(Boolean)))

  const columns = [
    {
      title: '产品名称',
      dataIndex: 'name',
      key: 'name',
      width: 180,
      fixed: 'left' as const
    },
    {
      title: '产品代码',
      dataIndex: 'major_category',
      key: 'major_category',
      width: 100,
      render: (val: string) => val ? <Tag color={categoryColorMap[val] || 'default'}>{val}</Tag> : '-'
    },
    {
      title: '制剂代码',
      dataIndex: 'formulation_code',
      key: 'formulation_code',
      width: 100
    },
    {
      title: '产品剂型',
      dataIndex: 'product_type',
      key: 'product_type',
      width: 100
    },
    {
      title: '生产规格',
      dataIndex: 'spec',
      key: 'spec',
      width: 140
    },
    {
      title: '生产批量',
      dataIndex: 'capacity_range',
      key: 'capacity_range',
      width: 140
    },
    {
      title: '单位',
      dataIndex: 'unit',
      key: 'unit',
      width: 70
    },
    {
      title: '适应症',
      dataIndex: 'indication',
      key: 'indication',
      width: 120
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      fixed: 'right' as const,
      render: (_: any, record: Product) => (
        <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEditModal(record)}>
          修改
        </Button>
      )
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
          产品信息
        </h1>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
            新增产品
          </Button>
          <Button
            icon={<SyncOutlined spin={syncing} />}
            loading={syncing}
            onClick={handleSyncFromFeishu}
          >
            从飞书同步
          </Button>
        </Space>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <Input
          placeholder="搜索产品名称或制剂代码"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          prefix={<SearchOutlined />}
          className="w-64"
          allowClear
        />
        <Select
          placeholder="产品代码"
          value={filterCategory || undefined}
          onChange={(value) => setFilterCategory(value || '')}
          allowClear
          className="w-32"
          options={categories.map((c) => ({ value: c, label: c }))}
        />
        <Select
          placeholder="产品剂型"
          value={filterType || undefined}
          onChange={(value) => setFilterType(value || '')}
          allowClear
          className="w-32"
          options={types.map((t) => ({ value: t, label: t }))}
        />
      </div>

      <Table
        columns={columns}
        dataSource={products}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: handlePageChange
        }}
        scroll={{ x: 1200 }}
        size="small"
        bordered
      />

      <Modal
        title={editingProduct ? '修改产品' : '新增产品'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        confirmLoading={saving}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" className="mt-4">
          <Form.Item
            name="name"
            label="产品名称"
            rules={[{ required: true, message: '请输入产品名称' }]}
          >
            <Input placeholder="请输入产品名称" />
          </Form.Item>
          <Form.Item name="major_category" label="产品代码">
            <Input placeholder="请输入产品代码，如 SM、FSM" />
          </Form.Item>
          <Form.Item name="formulation_code" label="制剂代码">
            <Input placeholder="请输入制剂代码，如 AA、AB、AC" />
          </Form.Item>
          <Form.Item name="product_type" label="产品剂型">
            <Input placeholder="请输入产品剂型，如 API、制品、包装" />
          </Form.Item>
          <Form.Item name="spec" label="生产规格">
            <Input placeholder="请输入生产规格" />
          </Form.Item>
          <Form.Item name="capacity_range" label="生产批量">
            <Input placeholder="请输入生产批量" />
          </Form.Item>
          <Form.Item name="unit" label="单位">
            <Input placeholder="请输入单位，如 支、g、批" />
          </Form.Item>
          <Form.Item name="indication" label="适应症">
            <Input placeholder="请输入适应症" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
