'use client'

import { useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from 'antd'
import {
  DownloadOutlined,
  FileTextOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  createChemicalInventory,
  createHazardousChemical,
  deleteChemicalInventory,
  deleteHazardousChemical,
  downloadChemicalMsds,
  getChemicalInventories,
  getHazardousChemicals,
  updateChemicalInventory,
  updateHazardousChemical,
  uploadChemicalMsds,
  type ChemicalInventoryItem,
  type HazardousChemicalItem,
} from '@/actions/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'

const { Text, Title } = Typography

const T = {
  error: '#E03131',
  warning: '#DD5B00',
  success: '#1AAE39',
  charcoal: '#37352f',
  slate: '#5d5b54',
  steel: '#787671',
  muted: '#bbb8b1',
  hairline: '#e5e3df',
  surface: '#f6f5f4',
  mint: '#d9f3e1',
  rose: '#fde0ec',
  peach: '#ffe8d4',
}

export const CHEMICAL_CATEGORY_LABELS: Record<string, string> = {
  explosive: '爆炸物',
  flammable_gas: '易燃气体',
  oxidizing_gas: '氧化性气体',
  flammable_liquid: '易燃液体',
  flammable_solid: '易燃固体',
  self_reactive: '自反应物质',
  oxidizing_liquid: '氧化性液体',
  organic_peroxide: '有机过氧化物',
  toxic: '毒性物质',
  corrosive: '腐蚀性物质',
  other: '其他',
}

interface ChemicalFormValues {
  name: string
  alias?: string
  cas_no?: string
  category: string
  hazard_statements?: string
  storage_requirements?: string
  remark?: string
}

interface InventoryFormValues {
  chemical_id: string
  workshop: string
  quantity: number
  upper_limit?: number | null
  unit: string
  remark?: string
}

export default function HazchemPanel({
  pageKey,
  initialChemicals,
  initialInventories,
  initialError,
}: {
  pageKey: string
  initialChemicals: HazardousChemicalItem[]
  initialInventories: ChemicalInventoryItem[]
  initialError: string | null
}) {
  const { canOperate, canDelete } = usePagePermissions(pageKey)
  const { message } = App.useApp()

  const [chemicals, setChemicals] = useState<HazardousChemicalItem[]>(initialChemicals)
  const [chemTotal, setChemTotal] = useState(initialChemicals.length)
  const [inventories, setInventories] = useState<ChemicalInventoryItem[]>(initialInventories)
  const [invTotal, setInvTotal] = useState(initialInventories.length)
  const [error, setError] = useState<string | null>(initialError)
  const [loading, setLoading] = useState(false)
  const [chemKeyword, setChemKeyword] = useState('')
  const [overLimitOnly, setOverLimitOnly] = useState(false)

  const [chemFormOpen, setChemFormOpen] = useState(false)
  const [editingChemical, setEditingChemical] = useState<HazardousChemicalItem | null>(null)
  const [chemForm] = Form.useForm<ChemicalFormValues>()

  const [invFormOpen, setInvFormOpen] = useState(false)
  const [editingInventory, setEditingInventory] = useState<ChemicalInventoryItem | null>(null)
  const [invForm] = Form.useForm<InventoryFormValues>()

  useEffect(() => {
    setChemicals(initialChemicals)
    setChemTotal(initialChemicals.length)
    setInventories(initialInventories)
    setInvTotal(initialInventories.length)
    setError(initialError)
  }, [initialChemicals, initialInventories, initialError])

  const refreshChemicals = async (nextKeyword = chemKeyword) => {
    setLoading(true)
    try {
      const res = await getHazardousChemicals({ keyword: nextKeyword || undefined, page_size: 200 })
      if (res.code === 200 && res.data) {
        setChemicals(res.data.items)
        setChemTotal(res.data.total)
        setError(null)
      } else {
        setError(res.message || '加载危化品档案失败')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载危化品档案失败')
    } finally {
      setLoading(false)
    }
  }

  const refreshInventories = async (nextOverLimit = overLimitOnly) => {
    const res = await getChemicalInventories({
      over_limit_only: nextOverLimit || undefined,
      page_size: 200,
    })
    if (res.code === 200 && res.data) {
      setInventories(res.data.items)
      setInvTotal(res.data.total)
    }
  }

  const openChemCreate = () => {
    setEditingChemical(null)
    chemForm.setFieldsValue({
      name: '',
      alias: '',
      cas_no: '',
      category: 'flammable_liquid',
      hazard_statements: '',
      storage_requirements: '',
      remark: '',
    })
    setChemFormOpen(true)
  }

  const openChemEdit = (item: HazardousChemicalItem) => {
    setEditingChemical(item)
    chemForm.setFieldsValue({ ...item })
    setChemFormOpen(true)
  }

  const submitChemical = async () => {
    const values = await chemForm.validateFields()
    const payload = {
      name: values.name,
      alias: values.alias ?? '',
      cas_no: values.cas_no ?? '',
      category: values.category,
      hazard_statements: values.hazard_statements ?? '',
      storage_requirements: values.storage_requirements ?? '',
      remark: values.remark ?? '',
    }
    try {
      const res = editingChemical
        ? await updateHazardousChemical(editingChemical.id, payload)
        : await createHazardousChemical(payload)
      if (res.code === 200) {
        message.success(editingChemical ? '档案已更新' : '档案已创建')
        setChemFormOpen(false)
        await refreshChemicals()
      } else {
        message.error(res.message || '保存失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const handleChemDelete = async (item: HazardousChemicalItem) => {
    const res = await deleteHazardousChemical(item.id)
    if (res.code === 200) {
      message.success('档案已删除')
      await refreshChemicals()
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const openInvCreate = () => {
    setEditingInventory(null)
    invForm.setFieldsValue({
      chemical_id: chemicals[0]?.id,
      workshop: '',
      quantity: 0,
      upper_limit: null,
      unit: 'kg',
      remark: '',
    })
    setInvFormOpen(true)
  }

  const openInvEdit = (item: ChemicalInventoryItem) => {
    setEditingInventory(item)
    invForm.setFieldsValue({
      chemical_id: item.chemical_id,
      workshop: item.workshop,
      quantity: item.quantity,
      upper_limit: item.upper_limit,
      unit: item.unit,
      remark: item.remark,
    })
    setInvFormOpen(true)
  }

  const submitInventory = async () => {
    const values = await invForm.validateFields()
    const payload = {
      chemical_id: values.chemical_id,
      workshop: values.workshop,
      quantity: values.quantity,
      upper_limit: values.upper_limit ?? null,
      unit: values.unit ?? 'kg',
      remark: values.remark ?? '',
    }
    try {
      const res = editingInventory
        ? await updateChemicalInventory(editingInventory.id, payload)
        : await createChemicalInventory(payload)
      if (res.code === 200) {
        message.success('存量已保存')
        setInvFormOpen(false)
        await refreshInventories()
      } else {
        message.error(res.message || '保存失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const handleInvDelete = async (item: ChemicalInventoryItem) => {
    const res = await deleteChemicalInventory(item.id)
    if (res.code === 200) {
      message.success('存量记录已删除')
      await refreshInventories()
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const chemicalColumns: ColumnsType<HazardousChemicalItem> = [
    {
      title: '品名',
      dataIndex: 'name',
      key: 'name',
      render: (v, row) => (
        <div>
          <Text strong style={{ color: T.charcoal }}>{v}</Text>
          {row.alias && (
            <div>
              <Text style={{ color: T.steel, fontSize: 12 }}>{row.alias}</Text>
            </div>
          )}
        </div>
      ),
    },
    {
      title: 'CAS 号',
      dataIndex: 'cas_no',
      key: 'cas_no',
      width: 130,
      render: (v: string) => (
        <Text style={{ fontFamily: 'monospace', fontSize: 12, color: T.steel }}>{v || '-'}</Text>
      ),
    },
    {
      title: '危险性类别',
      dataIndex: 'category',
      key: 'category',
      width: 120,
      render: (v: string) => (
        <Tag style={{ borderRadius: 6, border: 'none', backgroundColor: T.peach, color: T.warning, fontWeight: 600 }}>
          {CHEMICAL_CATEGORY_LABELS[v] || v}
        </Tag>
      ),
    },
    {
      title: 'MSDS',
      key: 'msds',
      width: 150,
      render: (_, row) =>
        row.msds_file_path ? (
          <Button
            type="link"
            size="small"
            icon={<DownloadOutlined />}
            style={{ padding: 0 }}
            onClick={() =>
              downloadChemicalMsds(row.id, row.msds_file_name || `${row.name}-MSDS`).catch((err) =>
                message.error(err instanceof Error ? err.message : '下载失败')
              )
            }
          >
            {row.msds_file_name || '下载'}
          </Button>
        ) : (
          <Upload
            showUploadList={false}
            accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
            customRequest={async ({ file, onSuccess, onError }) => {
              try {
                const res = await uploadChemicalMsds(row.id, file as File)
                if (res.code === 200) {
                  message.success('MSDS 已上传')
                  onSuccess?.(res)
                  await refreshChemicals()
                } else {
                  message.error(res.message || '上传失败')
                  onError?.(new Error(res.message))
                }
              } catch (err) {
                message.error(err instanceof Error ? err.message : '上传失败')
                onError?.(err as Error)
              }
            }}
          >
            <Button type="link" size="small" icon={<UploadOutlined />} style={{ padding: 0 }} disabled={!canOperate}>
              上传
            </Button>
          </Upload>
        ),
    },
    {
      title: '储存要求',
      dataIndex: 'storage_requirements',
      key: 'storage_requirements',
      ellipsis: true,
      render: (v: string) => (
        <Text style={{ fontSize: 12, color: T.steel }}>{v || '-'}</Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" style={{ padding: 0 }} disabled={!canOperate} onClick={() => openChemEdit(row)}>
            编辑
          </Button>
          <Popconfirm title="确定删除该危化品档案？" onConfirm={() => handleChemDelete(row)} disabled={!canDelete}>
            <Button type="link" size="small" danger style={{ padding: 0 }} disabled={!canDelete}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const inventoryColumns: ColumnsType<ChemicalInventoryItem> = [
    { title: '品名', dataIndex: 'chemical_name', key: 'chemical_name' },
    { title: '车间/库房', dataIndex: 'workshop', key: 'workshop', width: 140 },
    {
      title: '存量/上限',
      key: 'stock',
      width: 160,
      render: (_, row) => (
        <Text style={{ color: T.charcoal }}>
          {row.quantity}{row.unit} / {row.upper_limit ?? '不限'}{row.upper_limit ? row.unit : ''}
        </Text>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 120,
      render: (_, row) =>
        row.over_limit ? (
          <Tag style={{ borderRadius: 6, border: 'none', backgroundColor: T.rose, color: T.error, fontWeight: 600 }}>
            超储{row.over_pct !== null ? ` ${row.over_pct}%` : ''}
          </Tag>
        ) : (
          <Tag style={{ borderRadius: 6, border: 'none', backgroundColor: T.mint, color: T.success, fontWeight: 600 }}>
            正常
          </Tag>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" style={{ padding: 0 }} disabled={!canOperate} onClick={() => openInvEdit(row)}>
            更新存量
          </Button>
          <Popconfirm title="确定删除该存量记录？" onConfirm={() => handleInvDelete(row)} disabled={!canDelete}>
            <Button type="link" size="small" danger style={{ padding: 0 }} disabled={!canDelete}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4 pb-8">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <Title level={4} className="!mb-1">危化品与 MSDS 管理</Title>
          <Text style={{ color: T.slate, fontSize: 13 }}>
            危化品档案、MSDS 附件与车间存量上限（超储预警）
          </Text>
        </div>
      </div>

      {error && (
        <Card variant="borderless" style={{ borderRadius: 12, border: `1px solid ${T.error}33` }}>
          <Text style={{ color: T.error }}>{error}</Text>
        </Card>
      )}

      <Card variant="borderless" style={{ borderRadius: 12, border: `1px solid ${T.hairline}` }}>
        <Tabs
          defaultActiveKey="chemicals"
          items={[
            {
              key: 'chemicals',
              label: '危化品档案',
              children: (
                <>
                  <div className="flex items-center gap-3 mb-3 flex-wrap">
                    <Input.Search
                      placeholder="搜索品名/别名/CAS"
                      allowClear
                      style={{ maxWidth: 260 }}
                      onSearch={(v) => {
                        setChemKeyword(v)
                        refreshChemicals(v)
                      }}
                    />
                    <Button type="primary" disabled={!canOperate} onClick={openChemCreate}>
                      新增危化品
                    </Button>
                    <Text style={{ color: T.muted, fontSize: 12, marginLeft: 'auto' }}>共 {chemTotal} 条</Text>
                  </div>
                  <Table<HazardousChemicalItem>
                    rowKey="id"
                    columns={chemicalColumns}
                    dataSource={chemicals}
                    loading={loading}
                    pagination={{ pageSize: 20, showSizeChanger: false }}
                    size="middle"
                  />
                </>
              ),
            },
            {
              key: 'inventory',
              label: '车间库存/超储',
              children: (
                <>
                  <div className="flex items-center gap-3 mb-3 flex-wrap">
                    <Button
                      type={overLimitOnly ? 'primary' : 'default'}
                      icon={<FileTextOutlined />}
                      onClick={() => {
                        const next = !overLimitOnly
                        setOverLimitOnly(next)
                        refreshInventories(next)
                      }}
                    >
                      只看超储
                    </Button>
                    <Button type="primary" disabled={!canOperate} onClick={openInvCreate}>
                      新增存量记录
                    </Button>
                    <Text style={{ color: T.muted, fontSize: 12, marginLeft: 'auto' }}>共 {invTotal} 条</Text>
                  </div>
                  <Table<ChemicalInventoryItem>
                    rowKey="id"
                    columns={inventoryColumns}
                    dataSource={inventories}
                    pagination={{ pageSize: 20, showSizeChanger: false }}
                    size="middle"
                    rowClassName={(row) => (row.over_limit ? 'bg-red-50' : '')}
                  />
                </>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={editingChemical ? '编辑危化品档案' : '新增危化品档案'}
        open={chemFormOpen}
        onOk={submitChemical}
        onCancel={() => setChemFormOpen(false)}
        width={640}
        destroyOnHidden
      >
        <Form<ChemicalFormValues> form={chemForm} layout="vertical" className="mt-3">
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="name" label="化学品名称" rules={[{ required: true, message: '请填写品名' }]}>
              <Input placeholder="如：乙醇" />
            </Form.Item>
            <Form.Item name="alias" label="别名/商品名">
              <Input />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="cas_no" label="CAS 号">
              <Input placeholder="如 64-17-5" />
            </Form.Item>
            <Form.Item name="category" label="危险性类别" rules={[{ required: true }]}>
              <Select
                options={Object.entries(CHEMICAL_CATEGORY_LABELS).map(([value, label]) => ({
                  value,
                  label,
                }))}
              />
            </Form.Item>
          </div>
          <Form.Item name="hazard_statements" label="危险性概述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="storage_requirements" label="储存要求">
            <Input.TextArea rows={2} placeholder="温度/禁配/防爆等要求" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingInventory ? '更新车间存量' : '新增存量记录'}
        open={invFormOpen}
        onOk={submitInventory}
        onCancel={() => setInvFormOpen(false)}
        destroyOnHidden
      >
        <Form<InventoryFormValues> form={invForm} layout="vertical" className="mt-3">
          <Form.Item name="chemical_id" label="危化品" rules={[{ required: true, message: '请选择危化品' }]}>
            <Select
              showSearch
              optionFilterProp="label"
              disabled={editingInventory !== null}
              options={chemicals.map((c) => ({ label: c.name, value: c.id }))}
            />
          </Form.Item>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="workshop" label="车间/库房" rules={[{ required: true, message: '请填写车间' }]}>
              <Input placeholder="如 203车间 / 301仓库" />
            </Form.Item>
            <Form.Item name="unit" label="单位">
              <Input placeholder="kg / L / 桶" />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="quantity" label="当前存量" rules={[{ required: true }]}>
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="upper_limit" label="存量上限（留空不设限）">
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
