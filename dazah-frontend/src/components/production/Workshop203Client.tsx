'use client'

import { useMemo, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons'

import {
  completeProcessExecutionRecord,
  createProcessExecutionRecord,
  deleteProcessExecutionRecord,
  getBatchProgress,
  getProcessExecutionRecords,
  updateProcessExecutionRecord,
} from '@/actions/production'
import type { components } from '@/types/generated/schema'

type BatchProgress = components['schemas']['BatchProgressResponse']
type BatchProgressItem = components['schemas']['BatchProgressItem']
type ProcessRecord = components['schemas']['ProcessExecutionRecordResponse']
type ProcessRecordCreate = components['schemas']['ProcessExecutionRecordCreate']
type ProcessRecordUpdate = components['schemas']['ProcessExecutionRecordUpdate']
type ProcessDefinition = components['schemas']['ProcessDefinition']
type ProcessFieldDefinition = components['schemas']['ProcessFieldDefinition']

interface Workshop203ClientProps {
  initialProgress: BatchProgress
  initialRecords: ProcessRecord[]
  processCatalog: ProcessDefinition[]
}

interface ProcessFormValues {
  batch_no: string
  process_code: string
  status: 'draft' | 'in_progress' | 'completed'
  recorded_at: Dayjs
  data: Record<string, unknown>
  remarks?: string
}

const PROCESS_OPTIONS = [
  ['receive', '发酵液接收'],
  ['pretreat', '预处理'],
  ['ceramic', '陶瓷膜过滤'],
  ['decolor1', '一次脱色'],
  ['filter1', '一次板框过滤'],
  ['conc1', '一次浓缩'],
  ['centrifuge1', '一次离心'],
  ['recrystallize', '二次重结晶脱色'],
  ['filter2', '二次板框过滤'],
  ['conc2', '二次浓缩'],
  ['centrifuge2', '二次离心'],
  ['dry', '烘干'],
  ['pack', '包装'],
] as const

const PROCESS_LABELS = Object.fromEntries(PROCESS_OPTIONS)

const emptyProgress: BatchProgress = {
  batches: [],
  steps: [],
  summary: {
    total_batches: 0,
    in_progress: 0,
    completed: 0,
    today_pack_count: 0,
    monthly_output_kg: 0,
    bottlenecks: [],
  },
}

function processFieldInput(field: ProcessFieldDefinition) {
  if (field.kind === 'number') return <InputNumber className="!w-full" />
  if (field.kind === 'date') return <Input type="date" />
  if (field.kind === 'boolean') {
    return <Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} />
  }
  if (field.kind === 'textarea') return <Input.TextArea rows={3} />
  if (field.kind === 'select' && field.name === 'substage') {
    return (
      <Select
        options={[
          { value: 'feed', label: '进料' },
          { value: 'operations', label: '膜运行参数' },
          { value: 'clean', label: '膜清洗' },
          { value: 'separation', label: '物料分离' },
          { value: 'equipment', label: '设备运行' },
        ]}
      />
    )
  }
  return <Input />
}

export function Workshop203Client({
  initialProgress,
  initialRecords,
  processCatalog,
}: Workshop203ClientProps) {
  const { message } = App.useApp()
  const [progress, setProgress] = useState(initialProgress || emptyProgress)
  const [records, setRecords] = useState(initialRecords)
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<ProcessRecord | null>(null)
  const [form] = Form.useForm<ProcessFormValues>()
  const selectedProcessCode = Form.useWatch('process_code', form)

  const processOptions = useMemo(
    () => (processCatalog.length > 0
      ? processCatalog.map(({ code: value, label }) => ({ value, label }))
      : PROCESS_OPTIONS.map(([value, label]) => ({ value, label }))),
    [processCatalog],
  )
  const selectedDefinition = processCatalog.find(item => item.code === selectedProcessCode)

  const refresh = async () => {
    setLoading(true)
    try {
      const [progressResponse, recordsResponse] = await Promise.all([
        getBatchProgress('203'),
        getProcessExecutionRecords({ workshop_code: '203', page_size: 200 }),
      ])
      if (progressResponse.code === 200 && progressResponse.data) {
        setProgress(progressResponse.data)
      }
      if (recordsResponse.code === 200 && recordsResponse.data) {
        setRecords(recordsResponse.data)
      }
    } finally {
      setLoading(false)
    }
  }

  const openCreate = () => {
    setEditing(null)
    form.setFieldsValue({
      batch_no: '',
      process_code: 'receive',
      status: 'draft',
      recorded_at: dayjs(),
      data: {},
      remarks: '',
    })
    setModalOpen(true)
  }

  const openEdit = (record: ProcessRecord) => {
    setEditing(record)
    form.setFieldsValue({
      batch_no: record.batch_no,
      process_code: record.process_code,
      status: record.status,
      recorded_at: dayjs(record.recorded_at),
      data: record.data || {},
      remarks: record.remarks || '',
    })
    setModalOpen(true)
  }

  const handleProcessChange = () => {
    if (!editing) {
      form.setFieldValue('data', {})
    }
  }

  const saveRecord = async () => {
    try {
      const values = await form.validateFields()
      const common = {
        status: values.status,
        recorded_at: values.recorded_at.toISOString(),
        data: values.data || {},
        remarks: values.remarks?.trim() || null,
      }
      const response = editing
        ? await updateProcessExecutionRecord(editing.id, common satisfies ProcessRecordUpdate)
        : await createProcessExecutionRecord({
            ...common,
            batch_no: values.batch_no.trim(),
            workshop_code: '203',
            process_code: values.process_code,
            source: 'manual',
          } satisfies ProcessRecordCreate)
      if (response.code !== 200 || !response.data) {
        message.error(response.message || '保存工序记录失败')
        return
      }
      message.success('工序记录已保存')
      setModalOpen(false)
      await refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '工序数据校验失败')
    }
  }

  const completeRecord = async (record: ProcessRecord) => {
    const response = await completeProcessExecutionRecord(record.id)
    if (response.code !== 200) {
      message.error(response.message || '完成工序失败')
      return
    }
    message.success('工序已完成')
    await refresh()
  }

  const removeRecord = async (record: ProcessRecord) => {
    const response = await deleteProcessExecutionRecord(record.id)
    if (response.code !== 200) {
      message.error(response.message || '删除工序记录失败')
      return
    }
    message.success('工序记录已删除')
    await refresh()
  }

  const progressColumns: ColumnsType<BatchProgressItem> = [
    { title: '批次', dataIndex: 'batch_no', fixed: 'left', width: 150 },
    {
      title: '总体进度',
      key: 'progress',
      width: 210,
      render: (_, record) => (
        <Progress percent={record.progress_percent} size="small" />
      ),
    },
    ...PROCESS_OPTIONS.map<ColumnsType<BatchProgressItem>[number]>(([code, label]) => ({
      title: label,
      key: code,
      width: 100,
      align: 'center',
      render: (_, record) => {
        const step = record.steps.find((item) => item.code === code)
        return step?.completed ? (
          <Tag color="success">完成</Tag>
        ) : step?.has_record ? (
          <Tag color="processing">进行中</Tag>
        ) : (
          <Tag>未开始</Tag>
        )
      },
    })),
  ]

  const recordColumns: ColumnsType<ProcessRecord> = [
    { title: '批次', dataIndex: 'batch_no', width: 150 },
    {
      title: '工序',
      dataIndex: 'process_code',
      width: 160,
      render: (value: string) => PROCESS_LABELS[value] || value,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => (
        <Tag color={value === 'completed' ? 'success' : value === 'in_progress' ? 'processing' : 'default'}>
          {value === 'completed' ? '已完成' : value === 'in_progress' ? '进行中' : '草稿'}
        </Tag>
      ),
    },
    {
      title: '记录时间',
      dataIndex: 'recorded_at',
      width: 180,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '关键数据',
      dataIndex: 'data',
      ellipsis: true,
      render: (value: Record<string, unknown>, record) => {
        const definition = processCatalog.find(item => item.code === record.process_code)
        const labels = Object.fromEntries(
          (definition?.fields || []).map(field => [field.name, field.label]),
        )
        return Object.entries(value || {})
          .slice(0, 3)
          .map(([key, item]) => `${labels[key] || key}: ${item ?? '-'}`)
          .join(' · ')
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_, record) => (
        <Space>
          {record.status !== 'completed' && (
            <Button
              size="small"
              icon={<CheckOutlined />}
              onClick={() => completeRecord(record)}
            >
              完成
            </Button>
          )}
          {record.status !== 'completed' && (
            <>
              <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
                编辑
              </Button>
              <Popconfirm
                title="删除该工序记录？"
                okText="删除"
                cancelText="取消"
                onConfirm={() => removeRecord(record)}
              >
                <Button danger size="small" icon={<DeleteOutlined />} />
              </Popconfirm>
            </>
          )}
        </Space>
      ),
    },
  ]

  const overview = (
    <Space orientation="vertical" size={16} className="w-full">
      {progress.summary.bottlenecks.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message="检测到工序卡点"
          description={progress.summary.bottlenecks
            .map((item) => `${item.process_label}：${item.stuck_count} 个批次`)
            .join('；')}
        />
      )}
      <Table
        rowKey="batch_no"
        columns={progressColumns}
        dataSource={progress.batches}
        loading={loading}
        pagination={{ pageSize: 20 }}
        scroll={{ x: 1700 }}
      />
    </Space>
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Typography.Title level={3} className="!mb-1">
            203 车间工序工作台
          </Typography.Title>
          <Typography.Text type="secondary">
            按批次追踪发酵液接收到包装的 13 道工序
          </Typography.Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={refresh}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增工序记录
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}>
          <Card><Statistic title="跟踪批次" value={progress.summary.total_batches} /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="进行中" value={progress.summary.in_progress} /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="已完成" value={progress.summary.completed} /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="本月包装产量" value={progress.summary.monthly_output_kg} suffix="kg" /></Card>
        </Col>
      </Row>

      <Card>
        <Tabs
          items={[
            { key: 'overview', label: '批次进度', children: overview },
            {
              key: 'records',
              label: '工序记录',
              children: (
                <Table
                  rowKey="id"
                  columns={recordColumns}
                  dataSource={records}
                  loading={loading}
                  pagination={{ pageSize: 20 }}
                  scroll={{ x: 1100 }}
                />
              ),
            },
          ]}
        />
      </Card>

      <Modal
        open={modalOpen}
        title={editing ? '编辑工序记录' : '新增工序记录'}
        okText="保存"
        cancelText="取消"
        width={920}
        onCancel={() => setModalOpen(false)}
        onOk={saveRecord}
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="batch_no" label="批次号" rules={[{ required: true }]}>
                <Input disabled={Boolean(editing)} maxLength={128} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="process_code" label="工序" rules={[{ required: true }]}>
                <Select
                  disabled={Boolean(editing)}
                  options={processOptions}
                  onChange={handleProcessChange}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="status" label="状态" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: 'draft', label: '草稿' },
                    { value: 'in_progress', label: '进行中' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="recorded_at" label="记录时间" rules={[{ required: true }]}>
                <DatePicker showTime className="w-full" />
              </Form.Item>
            </Col>
          </Row>
          <Typography.Title level={5}>工艺数据</Typography.Title>
          <Typography.Paragraph type="secondary">
            字段随所选工序变化，数值字段会在服务端再次校验。完成后记录将锁定。
          </Typography.Paragraph>
          <Row gutter={16}>
            {(selectedDefinition?.fields || []).map(field => (
              <Col xs={24} md={field.kind === 'textarea' ? 24 : 12} key={field.name}>
                <Form.Item
                  name={['data', field.name]}
                  label={field.label}
                  rules={field.required ? [{ required: true, message: `请填写${field.label}` }] : undefined}
                >
                  {processFieldInput(field)}
                </Form.Item>
              </Col>
            ))}
          </Row>
          <Form.Item name="remarks" label="备注">
            <Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
