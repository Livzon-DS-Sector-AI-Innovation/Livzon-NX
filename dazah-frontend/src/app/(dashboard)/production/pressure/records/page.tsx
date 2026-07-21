'use client'

import { useEffect, useState, useCallback } from 'react'
import { App,
  Table,
  Button,
  Space,
  Select,
  Card,
  Typography,
  Tag,
  DatePicker,
  Input,
  Popconfirm,
  Modal
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  ReloadOutlined,
  DeleteOutlined,
  ExportOutlined,
  SearchOutlined
} from '@ant-design/icons'
import {
  getMergedPressureRecords,
  deleteMergedRow,
  batchDeleteMergedRows,
  exportByArea
} from '@/actions/pressure'
import { AREA_OPTIONS } from '@/types/pressure'
import type { MergedPressureRow } from '@/types/pressure'
import dayjs from 'dayjs'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

export default function PressureRecordsPage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [records, setRecords] = useState<MergedPressureRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [area, setArea] = useState<string>()
  const [pointId, setPointId] = useState<string>()
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize }
      if (area) params.area = area
      if (pointId) params.point_id = pointId
      if (dateRange) {
        params.start_date = dateRange[0].startOf('day').toISOString()
        params.end_date = dateRange[1].endOf('day').toISOString()
      }
      const res = await getMergedPressureRecords(params)
      if (res.code === 200) {
        setRecords(res.data || [])
        setTotal(res.meta?.total || 0)
      }
    } catch {
      message.error('加载记录失败')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, area, pointId, dateRange])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleDelete = async (record: MergedPressureRow) => {
    const res = await deleteMergedRow({ point_id: record.point_id, date: record.date })
    if (res.code === 200) {
      message.success('删除成功')
      loadData()
    } else {
      message.error('删除失败')
    }
  }

  const handleBatchDelete = async () => {
    const rows = selectedRowKeys.map((key) => {
      const record = records.find((r) => `${r.point_id}-${r.date}` === key)!
      return { point_id: record.point_id, date: record.date }
    })
    const res = await batchDeleteMergedRows(rows)
    if (res.code === 200) {
      message.success(`成功删除 ${res.data?.success_count || 0} 条`)
      setSelectedRowKeys([])
      loadData()
    }
  }

  const handleExport = async () => {
    const params: any = {}
    if (area) params.area = area
    if (dateRange) {
      params.start_date = dateRange[0].startOf('day').toISOString()
      params.end_date = dateRange[1].endOf('day').toISOString()
    }
    const res = await exportByArea(params)
    if (res.code === 200 && res.data) {
      message.success('导出成功，请查看下载')
    }
  }

  const getStatusTag = (status: string) => {
    const map: Record<string, { color: string; label: string }> = {
      pending: { color: 'warning', label: '待审核' },
      approved: { color: 'success', label: '已通过' },
      rejected: { color: 'error', label: '已驳回' }
    }
    const config = map[status] || { color: 'default', label: status }
    return <Tag color={config.color}>{config.label}</Tag>
  }

  const columns: ColumnsType<MergedPressureRow> = [
    {
      title: '位点编号',
      dataIndex: 'point_id',
      key: 'point_id',
      width: 120,
      render: (text: string) => <Text strong>{text}</Text>
    },
    {
      title: '区域',
      dataIndex: 'area',
      key: 'area',
      width: 100
    },
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
      width: 120
    },
    {
      title: '标准压差 (Pa)',
      dataIndex: 'standard_pressure',
      key: 'standard_pressure',
      width: 120,
      align: 'center'
    },
    {
      title: '各时段压差值',
      key: 'values',
      render: (_: any, record: MergedPressureRow) => (
        <Space wrap>
          {Object.entries(record.time_slot_values).map(([slot, value]) => (
            <Tag key={slot} color={value !== null && Math.abs((value || 0) - record.standard_pressure) > 5 ? 'error' : 'blue'}>
              {slot}: {value ?? '-'} Pa
            </Tag>
          ))}
        </Space>
      )
    },
    {
      title: '录入方式',
      dataIndex: 'input_type',
      key: 'input_type',
      width: 90,
      render: (type: string) => (type === 'ocr' ? <Tag color="purple">OCR</Tag> : <Tag>手动</Tag>)
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => getStatusTag(status)
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: any, record: MergedPressureRow) => (
        <Popconfirm title="确认删除该记录？" onConfirm={() => handleDelete(record)}>
          <Button type="link" danger size="small" icon={<DeleteOutlined />} />
        </Popconfirm>
      )
    },
  ]

  return (
    <div className="space-y-4">
      <Title level={4}>数据记录</Title>

      <Card variant="borderless" className="shadow-sm">
        <Space wrap className="mb-4">
          <Select
            placeholder="区域筛选"
            allowClear
            style={{ width: 140 }}
            options={AREA_OPTIONS.map((a) => ({ value: a, label: a }))}
            onChange={(v) => { setArea(v); setPage(1) }}
          />
          <Input
            placeholder="位点编号"
            prefix={<SearchOutlined />}
            allowClear
            style={{ width: 160 }}
            onChange={(e) => { setPointId(e.target.value); setPage(1) }}
          />
          <RangePicker
            onChange={(dates) => {
              setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs] | null)
              setPage(1)
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          <Button icon={<ExportOutlined />} onClick={handleExport}>导出</Button>
          {selectedRowKeys.length > 0 && (
            <Popconfirm title={`确认删除 ${selectedRowKeys.length} 条记录？`} onConfirm={handleBatchDelete}>
              <Button danger icon={<DeleteOutlined />}>批量删除 ({selectedRowKeys.length})</Button>
            </Popconfirm>
          )}
        </Space>

        <Table
          columns={columns}
          dataSource={records}
          rowKey={(r) => `${r.point_id}-${r.date}`}
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps) }
          }}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys
          }}
          size="middle"
        />
      </Card>
    </div>
  )
}
