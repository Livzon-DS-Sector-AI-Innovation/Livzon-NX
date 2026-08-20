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
  DatePicker,
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
  ExperimentOutlined,
  DownloadOutlined,
} from '@ant-design/icons'
import {getFermentationRecords,
  updateFermentationStatus,
  deleteFermentationRecord,} from '@/actions/production'
import type {
  FermentationRecord,
  FermentationFormData,
} from '@/types/production'
import { FERMENTATION_STATUS_OPTIONS } from '@/types/production'

const { Text } = Typography

// Helper to get status config
const getStatusConfig = (status: string) => {
  const option = FERMENTATION_STATUS_OPTIONS.find((o) => o.value === status)
  return option || { value: status, label: status, color: 'default' }
}

// 导出发酵记录数据为CSV
const exportFermentationToCsv = (records: FermentationRecord[]) => {
  const headers = ['批号', '产品名称', '发酵罐', '进罐日期', '放罐日期', '周期1', '周期2', '周期3', '周期4', '周期5', '周期6', '罐产', '状态', '备注']
  const rows = records.map(r => [
    r.batch_no,
    r.product_name,
    r.fermenter,
    r.entry_date,
    r.discharge_date || '',
    r.cycle_1 || '',
    r.cycle_2 || '',
    r.cycle_3 || '',
    r.cycle_4 || '',
    r.cycle_5 || '',
    r.cycle_6 || '',
    r.tank_yield || '',
    getStatusConfig(r.status).label,
    r.remarks || '',
  ])

  const csvContent = [headers, ...rows]
    .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')

  const BOM = '\uFEFF'
  const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `发酵记录_${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(link.href)
}

export default function FermentationPage() {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRecord, setEditingRecord] = useState<FermentationRecord | null>(null)
  const [records, setRecords] = useState<FermentationRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [searchBatchNo, setSearchBatchNo] = useState('')
  const [searchFermenter, setSearchFermenter] = useState('')
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [exportLoading, setExportLoading] = useState(false)

  const loadRecords = async () => {
    setLoading(true)
    try {
      const response = await getFermentationRecords({
        page,
        page_size: pageSize,
        batch_no: searchBatchNo || undefined,
        fermenter: searchFermenter || undefined,
        status: statusFilter,
      })
      if (response.code === 200) {
        setRecords(response.data)
        setTotal(response.meta?.total || 0)
      } else {
        message.error('加载发酵记录失败')
      }
    } catch (error) {
      message.error('加载发酵记录失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadRecords()
  }, [page, pageSize, statusFilter])

  const handleSearch = () => {
    setPage(1)
    loadRecords()
  }

  const handleAdd = () => {
    setEditingRecord(null)
    form.resetFields()
    form.setFieldsValue({ product_name: 'L-苯丙氨酸', status: 'in_progress' })
    setModalVisible(true)
  }

  const handleEdit = (record: FermentationRecord) => {
    setEditingRecord(record)
    form.setFieldsValue({
      batch_no: record.batch_no,
      product_name: record.product_name,
      fermenter: record.fermenter,
      entry_date: record.entry_date || null,
      discharge_date: record.discharge_date || null,
      cycle_1: record.cycle_1,
      cycle_2: record.cycle_2,
      cycle_3: record.cycle_3,
      cycle_4: record.cycle_4,
      cycle_5: record.cycle_5,
      cycle_6: record.cycle_6,
      tank_yield: record.tank_yield,
      status: record.status,
      remarks: record.remarks,
    })
    setModalVisible(true)
  }

  const handleDelete = (id: string) => {
    modal.confirm({
      title: '确认删除',
      content: '确定要删除这条发酵记录吗？',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          const response = await deleteFermentationRecord(id)
          if (response.code === 200) {
            message.success('删除成功')
            loadRecords()
          } else {
            message.error(response.message || '删除失败')
          }
        } catch (error) {
          message.error('删除失败')
        }
      },
    })
  }

  const handleStatusChange = async (id: string, status: string) => {
    try {
      const response = await updateFermentationStatus(id, status)
      if (response.code === 200) {
        message.success('状态更新成功')
        loadRecords()
      } else {
        message.error(response.message || '状态更新失败')
      }
    } catch (error) {
      message.error('状态更新失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const payload = {
        batch_no: values.batch_no,
        product_name: values.product_name || 'L-苯丙氨酸',
        fermenter: values.fermenter,
        entry_date: values.entry_date || '',
        discharge_date: values.discharge_date || null,
        cycle_1: values.cycle_1 ?? null,
        cycle_2: values.cycle_2 ?? null,
        cycle_3: values.cycle_3 ?? null,
        cycle_4: values.cycle_4 ?? null,
        cycle_5: values.cycle_5 ?? null,
        cycle_6: values.cycle_6 ?? null,
        tank_yield: values.tank_yield ?? null,
        status: values.status || 'in_progress',
        remarks: values.remarks || null,
      }

      // 直接调后端 API，绕过 Server Action，排查问题
      const API_BASE = 'http://localhost:8000'
      const url = editingRecord
        ? `${API_BASE}/api/v1/production/fermentation/${editingRecord.id}`
        : `${API_BASE}/api/v1/production/fermentation`
      const method = editingRecord ? 'PUT' : 'POST'
      const fetchRes = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const response = await fetchRes.json()
      alert('创建结果:\ncode=' + response.code + '\nmessage=' + response.message + '\n批号=' + (response.data?.batch_no || '无') + '\nID=' + (response.data?.id || '无'))

      if (response.code === 200) {
        message.success(editingRecord ? '更新成功' : '创建成功')
        setModalVisible(false)
        // 直接调后端刷新列表（加 _t 防浏览器缓存）
        const listRes = await fetch(`${API_BASE}/api/v1/production/fermentation?page=1&page_size=${pageSize}&_t=${Date.now()}`)
        const listData = await listRes.json()
        alert('刷新列表返回:\ncode=' + listData.code + '\ntotal=' + (listData.meta?.total || '无') + '\n条数=' + (listData.data?.length || 0) + '\n第一条批号=' + (listData.data?.[0]?.batch_no || '空'))
        if (listData.code === 200) {
          setRecords(listData.data)
          setTotal(listData.meta?.total || 0)
          setPage(1)
          setSearchBatchNo('')
          setSearchFermenter('')
          setStatusFilter(undefined)
        } else {
          message.error('刷新列表失败: ' + (listData.message || '未知错误'))
        }
      } else {
        message.error(response.message || '操作失败')
      }
    } catch (error) {
      message.error('操作失败: ' + (error instanceof Error ? error.message : String(error)))
    }
  }

  const handleExport = async () => {
    setExportLoading(true)
    try {
      const response = await getFermentationRecords({ page_size: 1000 })
      if (response.code === 200 && response.data) {
        exportFermentationToCsv(response.data)
        message.success('导出成功')
      } else {
        message.error('导出失败')
      }
    } catch (error) {
      message.error('导出失败')
    } finally {
      setExportLoading(false)
    }
  }

  const columns: ColumnsType<FermentationRecord> = [
    {
      title: '批号',
      dataIndex: 'batch_no',
      key: 'batch_no',
      width: 120,
    },
    {
      title: '产品名称',
      dataIndex: 'product_name',
      key: 'product_name',
      width: 120,
    },
    {
      title: '发酵罐',
      dataIndex: 'fermenter',
      key: 'fermenter',
      width: 100,
    },
    {
      title: '进罐日期',
      dataIndex: 'entry_date',
      key: 'entry_date',
      width: 100,
    },
    {
      title: '放罐日期',
      dataIndex: 'discharge_date',
      key: 'discharge_date',
      width: 100,
      render: (date: string) => date || '-',
    },
    {
      title: '周期',
      key: 'cycles',
      width: 180,
      render: (_, record) => {
        const cycles = [record.cycle_1, record.cycle_2, record.cycle_3, record.cycle_4, record.cycle_5, record.cycle_6]
          .filter(c => c !== null && c !== undefined)
          .map(c => c?.toFixed(1))
        return cycles.length > 0 ? cycles.join(' / ') : '-'
      },
    },
    {
      title: '罐产',
      dataIndex: 'tank_yield',
      key: 'tank_yield',
      width: 80,
      render: (value: number) => value ? value.toFixed(2) : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const config = getStatusConfig(status)
        return <Tag color={config.color}>{config.label}</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="编辑">
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          {record.status === 'in_progress' && (
            <Tooltip title="标记完成">
              <Button
                type="text"
                icon={<ExperimentOutlined />}
                onClick={() => handleStatusChange(record.id, 'completed')}
              />
            </Tooltip>
          )}
          <Tooltip title="删除">
            <Button
              type="text"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record.id)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <Typography.Title level={4} className="mb-1">发酵记录管理</Typography.Title>
          <Text type="secondary">发酵批次记录与周期管理</Text>
        </div>
        <Space>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleAdd}
          >
            新增记录
          </Button>
          <Button
            icon={<DownloadOutlined />}
            loading={exportLoading}
            onClick={handleExport}
          >
            导出
          </Button>
        </Space>
      </div>

      <Card variant="borderless" className="shadow-sm">
        <Space className="mb-4" wrap>
          <Input.Search
            placeholder="搜索批号"
            value={searchBatchNo}
            onChange={(e) => setSearchBatchNo(e.target.value)}
            onSearch={handleSearch}
            style={{ width: 200 }}
            allowClear
          />
          <Input.Search
            placeholder="搜索发酵罐"
            value={searchFermenter}
            onChange={(e) => setSearchFermenter(e.target.value)}
            onSearch={handleSearch}
            style={{ width: 200 }}
            allowClear
          />
          <Select
            placeholder="状态筛选"
            value={statusFilter}
            onChange={(value) => setStatusFilter(value)}
            style={{ width: 150 }}
            allowClear
            options={FERMENTATION_STATUS_OPTIONS.map(o => ({ value: o.value, label: o.label }))}
          />
          <Button icon={<SearchOutlined />} onClick={handleSearch}>
            搜索
          </Button>
        </Space>

        <Table
          columns={columns}
          dataSource={records}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1200 }}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (page, pageSize) => {
              setPage(page)
              setPageSize(pageSize)
            },
          }}
        />
      </Card>

      <Modal
        title={editingRecord ? '编辑发酵记录' : '新增发酵记录'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="batch_no"
                label="批号"
                rules={[{ required: true, message: '请输入批号' }]}
              >
                <Input placeholder="请输入批号" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="product_name"
                label="产品名称"
              >
                <Input placeholder="L-苯丙氨酸" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="fermenter"
                label="发酵罐"
                rules={[{ required: true, message: '请输入发酵罐' }]}
              >
                <Input placeholder="请输入发酵罐编号" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="status"
                label="状态"
              >
                <Select
                  options={FERMENTATION_STATUS_OPTIONS.map(o => ({ value: o.value, label: o.label }))}
                />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="entry_date"
                label="进罐日期"
                rules={[{ required: true, message: '请选择进罐日期' }]}
              >
                <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="discharge_date"
                label="放罐日期"
              >
                <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
              </Form.Item>
            </Col>
          </Row>

          <Typography.Text type="secondary" className="mb-2">发酵周期（小时）</Typography.Text>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="cycle_1" label="周期1">
                <InputNumber placeholder="周期1" precision={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="cycle_2" label="周期2">
                <InputNumber placeholder="周期2" precision={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="cycle_3" label="周期3">
                <InputNumber placeholder="周期3" precision={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="cycle_4" label="周期4">
                <InputNumber placeholder="周期4" precision={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="cycle_5" label="周期5">
                <InputNumber placeholder="周期5" precision={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="cycle_6" label="周期6">
                <InputNumber placeholder="周期6" precision={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="tank_yield" label="罐产">
                <InputNumber placeholder="罐产" precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="remarks" label="备注">
            <Input.TextArea rows={3} placeholder="请输入备注" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}