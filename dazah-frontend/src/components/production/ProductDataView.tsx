'use client'

import { useEffect, useState } from 'react'
import {
  Table,
  Button,
  Space,
  Input,
  Select,
  Modal,
  Form,
  InputNumber,
  Tag,
  Card,
  Row,
  Col,
  Statistic,
  Typography,
  Tooltip,
  App,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  PlusOutlined,
  SearchOutlined,
  EditOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  PieChartOutlined,
  BarChartOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import { getBatches, createBatch, updateBatch, deleteBatch } from '@/actions/production'
import type { Batch, BatchFormData, BatchStatus } from '@/types/production'
import { BatchStatus as BatchStatusEnum, BATCH_STATUS_OPTIONS } from '@/types/production'

const { Text, Title } = Typography

function getProductionPeriodLabel(): string {
  const now = new Date()
  const day = now.getDate()
  const year = now.getFullYear()
  const month = now.getMonth()
  let start: Date, end: Date
  if (day >= 27) {
    start = new Date(year, month, 27)
    end = new Date(year, month + 1, 26)
  } else {
    start = new Date(year, month - 1, 27)
    end = new Date(year, month, 26)
  }
  const fmt = (d: Date) => `${d.getMonth() + 1}月${d.getDate()}日`
  const prodMonth = end.getMonth() + 1
  return `${prodMonth}月生产批次数据查看与管理（${fmt(start)}-${fmt(end)}）`
}

// Helper to get status color
const getStatusColor = (status: BatchStatus) => {
  const option = BATCH_STATUS_OPTIONS.find((o) => o.value === status)
  return option?.color || 'default'
}

// Helper to get status label
const getStatusLabel = (status: BatchStatus) => {
  const option = BATCH_STATUS_OPTIONS.find((o) => o.value === status)
  return option?.label || status
}

// 导出批次数据为CSV
const exportBatchesToCsv = (batches: Batch[], productName: string) => {
  const headers = ['批次号', '产品编码', '产品名称', '规格', '计划数量', '实际产出', '投入数量', '状态', '生产线', '开始时间', '结束时间']
  const rows = batches.map(b => [
    b.batch_no,
    b.product_code,
    b.product_name || '',
    b.specification || '',
    b.planned_qty || '',
    b.actual_qty || '',
    b.input_qty || '',
    getStatusLabel(b.status),
    b.production_line || '',
    b.start_time ? new Date(b.start_time).toLocaleString('zh-CN') : '',
    b.end_time ? new Date(b.end_time).toLocaleString('zh-CN') : '',
  ])

  const csvContent = [headers, ...rows]
    .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')

  const BOM = '﻿'
  const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${productName}_批次数据_${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(link.href)
}

interface ProductDataViewProps {
  productName: string
}

export default function ProductDataView({ productName }: ProductDataViewProps) {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [batches, setBatches] = useState<Batch[]>([])
  const [allBatches, setAllBatches] = useState<Batch[]>([])
  const [modalVisible, setModalVisible] = useState(false)
  const [editingBatch, setEditingBatch] = useState<Batch | null>(null)
  const [searchText, setSearchText] = useState('')
  const [statusFilter, setStatusFilter] = useState<BatchStatus | undefined>()
  const [exportLoading, setExportLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  // 统计数据
  const stats = {
    total: allBatches.length,
    targetYield: allBatches.reduce((sum, b) => sum + (b.planned_qty || 0), 0),
    inProgress: allBatches.filter(b => b.status === BatchStatusEnum.IN_PROGRESS).length,
    completed: allBatches.filter(b => b.status === BatchStatusEnum.COMPLETED).length,
    totalYield: allBatches
      .filter(b => b.status === BatchStatusEnum.COMPLETED)
      .reduce((sum, b) => sum + (b.actual_qty || 0), 0),
    draft: allBatches.filter(b => b.status === BatchStatusEnum.DRAFT).length,
  }

  const loadBatches = async () => {
    setLoading(true)
    try {
      const response = await getBatches({ page: 1, page_size: 10000 })
      if (response.code === 200) {
        const filtered = response.data.filter(
          (b: Batch) => b.product_name === productName
        )
        setAllBatches(filtered)
      }
    } catch {
      message.error('加载批次数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadBatches()
  }, [productName])

  // 前端分页和筛选
  useEffect(() => {
    let result = [...allBatches]
    if (statusFilter) {
      result = result.filter(b => b.status === statusFilter)
    }
    if (searchText) {
      result = result.filter(b =>
        b.batch_no.toLowerCase().includes(searchText.toLowerCase())
      )
    }
    setBatches(result)
  }, [allBatches, statusFilter, searchText])

  const paginatedBatches = batches.slice((page - 1) * pageSize, page * pageSize)

  const handleAdd = () => {
    setEditingBatch(null)
    form.resetFields()
    form.setFieldsValue({ product_name: productName })
    setModalVisible(true)
  }

  const handleEdit = (record: Batch) => {
    setEditingBatch(record)
    editForm.setFieldsValue(record)
    setModalVisible(true)
  }

  const handleDelete = async (id: string) => {
    modal.confirm({
      title: '确认删除',
      content: '确定要删除这个批次吗？',
      onOk: async () => {
        try {
          const response = await deleteBatch(id)
          if (response.code === 200) {
            message.success('删除成功')
            loadBatches()
          } else {
            message.error(response.message || '删除失败')
          }
        } catch {
          message.error('删除失败')
        }
      },
    })
  }

  const handleSubmit = async () => {
    try {
      const values = editingBatch
        ? await editForm.validateFields()
        : await form.validateFields()

      if (editingBatch) {
        const response = await updateBatch(editingBatch.id, {
          ...values,
          product_name: productName,
        })
        if (response.code === 200) {
          message.success('更新成功')
          setModalVisible(false)
          loadBatches()
        } else {
          message.error(response.message || '更新失败')
        }
      } else {
        const response = await createBatch({
          ...values,
          product_name: productName,
        } as BatchFormData)
        if (response.code === 200) {
          message.success('创建成功')
          setModalVisible(false)
          form.resetFields()
          loadBatches()
        } else {
          message.error(response.message || '创建失败')
        }
      }
    } catch (error) {
      console.error('表单验证失败:', error)
    }
  }

  const handleExport = async () => {
    setExportLoading(true)
    try {
      if (batches.length > 0) {
        exportBatchesToCsv(batches, productName)
        message.success(`已导出 ${batches.length} 条批次数据`)
      } else {
        message.warning('没有可导出的批次数据')
      }
    } catch {
      message.error('导出失败')
    } finally {
      setExportLoading(false)
    }
  }

  const columns: ColumnsType<Batch> = [
    {
      title: '批次号',
      dataIndex: 'batch_no',
      key: 'batch_no',
      width: 150,
      fixed: 'left',
    },
    {
      title: '产品编码',
      dataIndex: 'product_code',
      key: 'product_code',
      width: 120,
    },
    {
      title: '规格',
      dataIndex: 'specification',
      key: 'specification',
      width: 100,
    },
    {
      title: '计划数量',
      dataIndex: 'planned_qty',
      key: 'planned_qty',
      width: 100,
    },
    {
      title: '实际产出',
      dataIndex: 'actual_qty',
      key: 'actual_qty',
      width: 100,
    },
    {
      title: '投入数量',
      dataIndex: 'input_qty',
      key: 'input_qty',
      width: 100,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: BatchStatus) => (
        <Tag color={getStatusColor(status)}>{getStatusLabel(status)}</Tag>
      ),
    },
    {
      title: '生产线',
      dataIndex: 'production_line',
      key: 'production_line',
      width: 100,
    },
    {
      title: '开始时间',
      dataIndex: 'start_time',
      key: 'start_time',
      width: 160,
      render: (time: string) => time ? new Date(time).toLocaleString('zh-CN') : '-',
    },
    {
      title: '结束时间',
      dataIndex: 'end_time',
      key: 'end_time',
      width: 160,
      render: (time: string) => time ? new Date(time).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record.id)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div className="p-6">
      {/* 页面标题 */}
      <div className="mb-6">
        <Title level={4} style={{ margin: 0 }}>
          <ExperimentOutlined className="mr-2" />
          {productName} - 数据管理
        </Title>
        <Text type="secondary">{getProductionPeriodLabel()}</Text>
      </div>

      {/* 统计卡片 */}
      <Row gutter={16} className="mb-6">
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="总批次"
              value={stats.total}
              prefix={<BarChartOutlined />}
              styles={{ content: { color: '#1677ff' }}}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="计划产量"
              value={stats.targetYield}
              prefix={<PieChartOutlined />}
              styles={{ content: { color: '#13c2c2' }}}
              suffix="kg"
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="执行中"
              value={stats.inProgress}
              prefix={<ClockCircleOutlined />}
              styles={{ content: { color: '#faad14' }}}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="已完成"
              value={stats.completed}
              prefix={<CheckCircleOutlined />}
              styles={{ content: { color: '#52c41a' }}}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="总产量"
              value={stats.totalYield}
              prefix={<CheckCircleOutlined />}
              styles={{ content: { color: '#722ed1' }}}
              suffix="kg"
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="完成率"
              value={stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0}
              prefix={<BarChartOutlined />}
              styles={{ content: { color: stats.completed > 0 ? '#52c41a' : '#999' }}}
              suffix="%"
            />
          </Card>
        </Col>
      </Row>

      {/* 批次列表 */}
      <Card
        title={`${productName} - 批次列表`}
        extra={
          <Space>
            <Tooltip title="导出当前筛选结果的批次数据">
              <Button icon={<DownloadOutlined />} onClick={handleExport} loading={exportLoading}>
                导出
              </Button>
            </Tooltip>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
              新建批次
            </Button>
          </Space>
        }
      >
        <Row gutter={16} className="mb-4">
          <Col span={6}>
            <Input
              placeholder="搜索批次号"
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              allowClear
            />
          </Col>
          <Col span={4}>
            <Select
              placeholder="状态筛选"
              allowClear
              value={statusFilter}
              onChange={(value) => {
                setStatusFilter(value)
                setPage(1)
              }}
              style={{ width: '100%' }}
              options={[
                { value: 'draft', label: '草稿' },
                { value: 'released', label: '已下达' },
                { value: 'in_progress', label: '执行中' },
                { value: 'completed', label: '已完成' },
                { value: 'cancelled', label: '已取消' },
              ]}
            />
          </Col>
        </Row>

        <Table
          columns={columns}
          dataSource={paginatedBatches}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1400 }}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: batches.length,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
          }}
        />
      </Card>

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editingBatch ? `编辑批次 - ${productName}` : `新建批次 - ${productName}`}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
        okText="确认"
        cancelText="取消"
      >
        <Form
          form={editingBatch ? editForm : form}
          layout="vertical"
          initialValues={editingBatch || { product_name: productName }}
        >
          <Form.Item
            name="batch_no"
            label="批次号"
            rules={[{ required: true, message: '请输入批次号' }]}
          >
            <Input placeholder="请输入批次号" disabled={!!editingBatch} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="product_code"
                label="产品编码"
                rules={[{ required: true, message: '请输入产品编码' }]}
              >
                <Input placeholder="请输入产品编码" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="product_name" label="产品名称">
                <Input placeholder={productName} disabled value={productName} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="specification" label="规格">
                <Input placeholder="请输入规格" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="unit" label="单位">
                <Input placeholder="请输入单位" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="planned_qty" label="计划数量">
                <InputNumber min={0} style={{ width: '100%' }} placeholder="计划数量" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="input_qty" label="投入数量">
                <InputNumber min={0} style={{ width: '100%' }} placeholder="投入数量" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="actual_qty" label="实际产出">
                <InputNumber min={0} style={{ width: '100%' }} placeholder="实际产出" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="production_line" label="生产线">
                <Select placeholder="请选择生产线" allowClear>
                  <Select.Option value="A线">A线</Select.Option>
                  <Select.Option value="B线">B线</Select.Option>
                  <Select.Option value="C线">C线</Select.Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={3} placeholder="请输入备注" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
