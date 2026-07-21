'use client'

import { useEffect, useState, useCallback } from 'react'
import { App,
  Table,
  Button,
  Space,
  Select,
  Card,
  Typography,
  Modal,
  Form,
  Input,
  InputNumber,
  Popconfirm
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import {
  getPointMappings,
  createPointMapping,
  updatePointMapping,
  deletePointMapping,
  checkPointIdUnique
} from '@/actions/pressure'
import { AREA_OPTIONS } from '@/types/pressure'
import type { PointMapping } from '@/types/pressure'

const { Title } = Typography

export default function PointManagementPage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [mappings, setMappings] = useState<PointMapping[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [area, setArea] = useState<string>()
  const [keyword, setKeyword] = useState<string>()
  const [modalOpen, setModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form] = Form.useForm()

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getPointMappings({ area, keyword, page, page_size: pageSize })
      if (res.code === 200) {
        setMappings(res.data || [])
        setTotal(res.meta?.total || 0)
      }
    } catch {
      message.error('加载位点列表失败')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, area, keyword])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingId) {
        const res = await updatePointMapping(editingId, {
          area: values.area,
          standard_pressure: values.standard_pressure
        })
        if (res.code === 200) {
          message.success('更新成功')
        } else {
          message.error(res.message || '更新失败')
        }
      } else {
        const check = await checkPointIdUnique(values.point_id)
        if (check.data?.exists) {
          message.error(`位点编号 ${values.point_id} 已存在`)
          return
        }
        const res = await createPointMapping(values)
        if (res.code === 200) {
          message.success('创建成功')
        } else {
          message.error(res.message || '创建失败')
        }
      }
      setModalOpen(false)
      form.resetFields()
      setEditingId(null)
      loadData()
    } catch {
      // validation error
    }
  }

  const handleEdit = (record: PointMapping) => {
    setEditingId(record.id)
    form.setFieldsValue({
      point_id: record.point_id,
      area: record.area,
      standard_pressure: record.standard_pressure
    })
    setModalOpen(true)
  }

  const handleDelete = async (id: string) => {
    const res = await deletePointMapping(id)
    if (res.code === 200) {
      message.success('删除成功')
      loadData()
    }
  }

  const columns: ColumnsType<PointMapping> = [
    { title: '位点编号', dataIndex: 'point_id', key: 'point_id', width: 150 },
    { title: '区域', dataIndex: 'area', key: 'area', width: 120 },
    { title: '标准压差 (Pa)', dataIndex: 'standard_pressure', key: 'standard_pressure', width: 130, align: 'center' },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: any, record: PointMapping) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button type="link" danger size="small" icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <Title level={4}>位点管理</Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => { setEditingId(null); form.resetFields(); setModalOpen(true) }}
        >
          新增位点
        </Button>
      </div>

      <Card variant="borderless" className="shadow-sm">
        <Space wrap className="mb-4">
          <Select
            placeholder="区域筛选"
            allowClear
            style={{ width: 140 }}
            options={AREA_OPTIONS.map((a) => ({ value: a, label: a }))}
            onChange={(v) => { setArea(v); setPage(1) }}
          />
          <Input.Search
            placeholder="搜索位点编号"
            allowClear
            style={{ width: 200 }}
            onSearch={(v) => { setKeyword(v); setPage(1) }}
          />
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        </Space>

        <Table
          columns={columns}
          dataSource={mappings}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps) }
          }}
          size="middle"
        />
      </Card>

      <Modal
        title={editingId ? '编辑位点' : '新增位点'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); setEditingId(null); form.resetFields() }}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="point_id"
            label="位点编号"
            rules={[{ required: true, message: '请输入位点编号' }]}
          >
            <Input placeholder="如 PD-0101" disabled={!!editingId} />
          </Form.Item>
          <Form.Item
            name="area"
            label="区域"
            rules={[{ required: true, message: '请选择区域' }]}
          >
            <Select options={AREA_OPTIONS.map((a) => ({ value: a, label: a }))} placeholder="选择区域" />
          </Form.Item>
          <Form.Item
            name="standard_pressure"
            label="标准压差 (Pa)"
            rules={[{ required: true, message: '请输入标准压差' }]}
          >
            <InputNumber style={{ width: '100%' }} placeholder="如 15" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
