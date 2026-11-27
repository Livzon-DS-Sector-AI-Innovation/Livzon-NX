'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  DatePicker,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { Dayjs } from 'dayjs'
import dayjs from 'dayjs'
import {
  createScheduleAnomaly,
  getScheduleAnomalies,
} from '@/actions/production'
import type {
  ApiResponse,
  ScheduleAnomalyInput,
  ScheduleAnomalyRecord,
  ScheduleAnomalyType,
} from '@/types/production'
import { useProductContextStore } from '@/stores/product-context'

const { Text } = Typography
const { TextArea } = Input

const ANOMALY_TYPE_OPTIONS: { value: ScheduleAnomalyType; label: string }[] = [
  { value: 'delayed', label: '延后' },
  { value: 'reduced', label: '减批' },
  { value: 'reseeded', label: '补种' },
  { value: 'contamination', label: '染菌' },
  { value: 'other', label: '其他' },
]

const ANOMALY_TYPE_COLORS: Record<ScheduleAnomalyType, string> = {
  delayed: 'orange',
  reduced: 'red',
  reseeded: 'cyan',
  contamination: 'volcano',
  other: 'default',
}

interface TableRow extends ScheduleAnomalyRecord {
  key: string
}

const tableColumns: ColumnsType<TableRow> = [
  {
    title: '类型',
    dataIndex: 'anomaly_type',
    key: 'anomaly_type',
    width: 90,
    render: (value: ScheduleAnomalyType, row) => (
      <Tag color={ANOMALY_TYPE_COLORS[value] ?? 'default'} style={{ marginRight: 0 }}>
        {row.anomaly_type_label}
      </Tag>
    ),
  },
  { title: '批号', dataIndex: 'batch_no', key: 'batch_no', width: 120 },
  {
    title: '罐号',
    dataIndex: 'tank_no',
    key: 'tank_no',
    width: 90,
    render: (v?: string | null) => v || '—',
  },
  {
    title: '发生日期',
    dataIndex: 'event_date',
    key: 'event_date',
    width: 110,
    render: (v?: string | null) => (v ? v.slice(5) : '—'),
  },
  {
    title: '原因',
    dataIndex: 'reason',
    key: 'reason',
    ellipsis: { showTitle: false },
    render: (v: string) =>
      v ? (
        <Tooltip title={v} placement="topLeft">
          {v}
        </Tooltip>
      ) : (
        '—'
      ),
  },
  {
    title: '备注',
    dataIndex: 'remark',
    key: 'remark',
    ellipsis: { showTitle: false },
    render: (v?: string | null) =>
      v ? (
        <Tooltip title={v} placement="topLeft">
          {v}
        </Tooltip>
      ) : (
        '—'
      ),
  },
  {
    title: '标记人',
    dataIndex: 'created_by_name',
    key: 'created_by_name',
    width: 110,
    render: (v?: string | null) => v || '—',
  },
  {
    title: '标记时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 150,
    render: (v?: string | null) => (v ? dayjs(v).format('MM-DD HH:mm') : '—'),
  },
]

interface AnomalyFormValues {
  batch_no: string
  tank_no?: string
  anomaly_type: ScheduleAnomalyType
  event_date: Dayjs
  reason: string
  remark?: string
}

/**
 * 排产异常台账：登记计划外的延后/减批/补种/染菌等异常并按条件查询。
 * 当前产品由页面级产品导航（BoardNavBlocks）决定。
 * showHeader=false 时隐藏标题行，供概览页展开大卡片等嵌入场景复用。
 */
export default function ScheduleAnomalyLedger({
  visibleProducts,
  canOperate,
  showHeader = true,
}: {
  /** 当前用户可见的产品（页面已按权限过滤） */
  visibleProducts: ReadonlyArray<{ key: string; label: string }>
  canOperate: boolean
  /** 是否渲染组件自带标题行（嵌入卡片场景由外部卡片提供标题） */
  showHeader?: boolean
}) {
  const { message } = App.useApp()
  const selectedProduct = useProductContextStore((state) => state.productCode)
  const productCode =
    visibleProducts.find((item) => item.key === selectedProduct)?.key ??
    visibleProducts[0]?.key ??
    ''

  const [rows, setRows] = useState<TableRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [filterBatchNo, setFilterBatchNo] = useState('')
  const [filterType, setFilterType] = useState<ScheduleAnomalyType | undefined>()
  const [filterRange, setFilterRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)

  const [modalOpen, setModalOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<AnomalyFormValues>()

  const loadRows = useCallback(
    async (
      targetPage: number,
      targetSize: number,
      product: string,
    ): Promise<ApiResponse<ScheduleAnomalyRecord[]> | null> => {
      setLoading(true)
      setLoadError(null)
      try {
        const response = await getScheduleAnomalies({
          product,
          page: targetPage,
          page_size: targetSize,
          batch_no: filterBatchNo.trim() || undefined,
          anomaly_type: filterType,
          date_from: filterRange?.[0]?.format('YYYY-MM-DD') || undefined,
          date_to: filterRange?.[1]?.format('YYYY-MM-DD') || undefined,
        })
        if (response.code !== 200) {
          setLoadError(response.message || '加载失败，请重试')
          return response
        }
        setRows(response.data.map((item) => ({ ...item, key: item.id })))
        setTotal(response.meta?.total ?? response.data.length)
        setPage(targetPage)
        setPageSize(targetSize)
        setLoaded(true)
        return response
      } finally {
        setLoading(false)
      }
    },
    [filterBatchNo, filterRange, filterType],
  )

  useEffect(() => {
    if (!productCode) return
    // 推迟到微任务，避免 effect 内同步 setState 触发级联渲染
    void Promise.resolve().then(() => loadRows(1, pageSize, productCode))
    // 初始加载与产品切换时拉取；筛选条件只在点击查询时生效
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productCode])

  const handleQuery = () => {
    void loadRows(1, pageSize, productCode)
  }

  // 导出与列表同筛选口径；相对路径经前端代理下载（带会话 Cookie）
  const exportUrl = () => {
    const params = new URLSearchParams()
    params.set('product', productCode)
    if (filterBatchNo.trim()) params.set('batch_no', filterBatchNo.trim())
    if (filterType) params.set('anomaly_type', filterType)
    if (filterRange?.[0]) params.set('date_from', filterRange[0].format('YYYY-MM-DD'))
    if (filterRange?.[1]) params.set('date_to', filterRange[1].format('YYYY-MM-DD'))
    return `/api/v1/production/schedule-anomalies/export?${params.toString()}`
  }

  const handleReset = () => {
    setFilterBatchNo('')
    setFilterType(undefined)
    setFilterRange(null)
    void loadRows(1, pageSize, productCode)
  }

  const handleSubmit = async (values: AnomalyFormValues) => {
    setSubmitting(true)
    try {
      const input: ScheduleAnomalyInput = {
        product_code: productCode,
        batch_no: values.batch_no.trim(),
        tank_no: values.tank_no?.trim() || null,
        anomaly_type: values.anomaly_type,
        event_date: values.event_date.format('YYYY-MM-DD'),
        reason: values.reason.trim(),
        remark: values.remark?.trim() || null,
      }
      const response = await createScheduleAnomaly(input)
      if (response.code !== 200) {
        message.error(response.message || '登记失败，请重试')
        return
      }
      message.success('异常已登记')
      setModalOpen(false)
      form.resetFields()
      await loadRows(page, pageSize, productCode)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {showHeader && (
        <Text strong style={{ fontSize: 16 }}>
          {visibleProducts.find((item) => item.key === productCode)?.label ?? ''}
          异常记录
        </Text>
      )}

      <Space wrap size={8}>
        <Input
          allowClear
          placeholder="批号"
          style={{ width: 160 }}
          value={filterBatchNo}
          onChange={(event) => setFilterBatchNo(event.target.value)}
          onPressEnter={handleQuery}
        />
        <Select
          allowClear
          placeholder="异常类型"
          style={{ width: 130 }}
          value={filterType}
          onChange={(next: ScheduleAnomalyType | undefined) => setFilterType(next)}
          options={ANOMALY_TYPE_OPTIONS}
        />
        <DatePicker.RangePicker
          value={filterRange}
          onChange={(range) => setFilterRange(range)}
        />
        <Button onClick={handleQuery}>查询</Button>
        <Button onClick={handleReset}>重置</Button>
        {canOperate && (
          <Button type="primary" onClick={() => setModalOpen(true)}>
            登记异常
          </Button>
        )}
        <Button
          icon={<DownloadOutlined />}
          href={exportUrl()}
          data-testid="anomaly-ledger-export"
        >
          导出 Excel
        </Button>
      </Space>

      <Table
        size="middle"
        loading={loading}
        rowKey="key"
        dataSource={rows}
        columns={tableColumns}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (count: number) => `共 ${count} 条`,
          onChange: (nextPage: number, nextSize: number) => {
            void loadRows(nextPage, nextSize, productCode)
          },
        }}
        locale={{
          emptyText: loadError
            ? loadError
            : loaded
              ? '当前筛选无异常记录'
              : '加载中…',
        }}
      />

      <Modal
        title="登记异常"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={submitting}
        okText="登记"
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{ event_date: dayjs() }}
        >
          <Form.Item
            name="batch_no"
            label="批号"
            rules={[
              { required: true, message: '请输入批号' },
              { max: 64, message: '批号不能超过 64 个字符' },
            ]}
          >
            <Input placeholder="如 FA26314" />
          </Form.Item>
          <Form.Item name="tank_no" label="罐号（选填）">
            <Input placeholder="如 302A" />
          </Form.Item>
          <Form.Item
            name="anomaly_type"
            label="异常类型"
            rules={[{ required: true, message: '请选择异常类型' }]}
          >
            <Select options={ANOMALY_TYPE_OPTIONS} placeholder="请选择" />
          </Form.Item>
          <Form.Item
            name="event_date"
            label="发生日期"
            rules={[{ required: true, message: '请选择发生日期' }]}
          >
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="reason"
            label="原因"
            rules={[
              { required: true, message: '请填写原因' },
              { max: 255, message: '原因不能超过 255 个字符' },
            ]}
          >
            <TextArea rows={2} placeholder="为什么出现这个异常" />
          </Form.Item>
          <Form.Item name="remark" label="备注（选填）">
            <TextArea rows={2} placeholder="补充说明" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
