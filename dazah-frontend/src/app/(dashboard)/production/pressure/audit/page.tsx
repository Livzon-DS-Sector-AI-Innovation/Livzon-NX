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
  Modal,
  Row,
  Col,
  Statistic
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckOutlined,
  CloseOutlined,
  ReloadOutlined,
  SearchOutlined
} from '@ant-design/icons'
import {
  getPressureRecords,
  auditPressureRecord,
  batchAuditPressureRecords,
  getAuditStats
} from '@/actions/pressure'
import { AREA_OPTIONS, AUDIT_STATUS_OPTIONS } from '@/types/pressure'
import type { PressureRecord, AuditStats } from '@/types/pressure'
import dayjs from 'dayjs'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

export default function AuditManagementPage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [records, setRecords] = useState<PressureRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [area, setArea] = useState<string>()
  const [status, setStatus] = useState<string>('pending')
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [auditStats, setAuditStats] = useState<AuditStats>({ pending_count: 0, today_approved_count: 0, rejected_count: 0 })
  const [rejectModalOpen, setRejectModalOpen] = useState(false)
  const [rejectTarget, setRejectTarget] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize, status }
      if (area) params.area = area
      if (dateRange) {
        params.start_date = dateRange[0].startOf('day').toISOString()
        params.end_date = dateRange[1].endOf('day').toISOString()
      }
      const [recordsRes, statsRes] = await Promise.all([
        getPressureRecords(params),
        getAuditStats(),
      ])
      if (recordsRes.code === 200) {
        setRecords(recordsRes.data || [])
        setTotal(recordsRes.meta?.total || 0)
      }
      if (statsRes.code === 200) {
        setAuditStats(statsRes.data)
      }
    } catch {
      message.error('加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, area, status, dateRange])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleApprove = async (id: string) => {
    const res = await auditPressureRecord(id, { status: 'approved' })
    if (res.code === 200) {
      message.success('审核通过')
      loadData()
    }
  }

  const handleReject = async () => {
    if (!rejectTarget || !rejectReason.trim()) {
      message.warning('请填写驳回原因')
      return
    }
    const res = await auditPressureRecord(rejectTarget, {
      status: 'rejected',
      reject_reason: rejectReason
    })
    if (res.code === 200) {
      message.success('已驳回')
      setRejectModalOpen(false)
      setRejectTarget(null)
      setRejectReason('')
      loadData()
    }
  }

  const handleBatchApprove = async () => {
    const res = await batchAuditPressureRecords({
      ids: selectedRowKeys as string[],
      status: 'approved'
    })
    if (res.code === 200) {
      message.success(`批量通过 ${res.data?.success_count || 0} 条`)
      setSelectedRowKeys([])
      loadData()
    }
  }

  const getStatusTag = (s: string) => {
    const config = AUDIT_STATUS_OPTIONS.find((o) => o.value === s)
    return <Tag color={config?.color}>{config?.label || s}</Tag>
  }

  const columns: ColumnsType<PressureRecord> = [
    { title: '位点编号', dataIndex: 'point_id', key: 'point_id', width: 120, render: (t: string) => <Text strong>{t}</Text> },
    { title: '区域', dataIndex: 'area', key: 'area', width: 100 },
    { title: '压差值 (Pa)', dataIndex: 'pressure_value', key: 'pressure_value', width: 110, align: 'center' },
    { title: '标准压差', dataIndex: 'standard_pressure', key: 'standard_pressure', width: 100, align: 'center' },
    { title: '记录时间', dataIndex: 'record_time', key: 'record_time', width: 170, render: (t: string) => new Date(t).toLocaleString('zh-CN') },
    { title: '时段', dataIndex: 'time_slot', key: 'time_slot', width: 80 },
    { title: '录入方式', dataIndex: 'input_type', key: 'input_type', width: 90, render: (t: string) => (t === 'ocr' ? <Tag color="purple">OCR</Tag> : <Tag>手动</Tag>) },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (s: string) => getStatusTag(s) },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: any, record: PressureRecord) =>
        record.status === 'pending' ? (
          <Space>
            <Button type="link" size="small" icon={<CheckOutlined />} style={{ color: '#52c41a' }} onClick={() => handleApprove(record.id)} />
            <Button type="link" size="small" danger icon={<CloseOutlined />} onClick={() => { setRejectTarget(record.id); setRejectModalOpen(true) }} />
          </Space>
        ) : null
    },
  ]

  return (
    <div className="space-y-4">
      <Title level={4}>审核管理</Title>

      <Row gutter={16}>
        <Col span={8}>
          <Card variant="borderless" className="shadow-sm">
            <Statistic title="待审核" value={auditStats.pending_count} styles={{ content: { color: '#dd5b00' } }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card variant="borderless" className="shadow-sm">
            <Statistic title="今日已通过" value={auditStats.today_approved_count} styles={{ content: { color: '#52c41a' } }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card variant="borderless" className="shadow-sm">
            <Statistic title="已驳回" value={auditStats.rejected_count} styles={{ content: { color: '#ff4d4f' } }} />
          </Card>
        </Col>
      </Row>

      <Card variant="borderless" className="shadow-sm">
        <Space wrap className="mb-4">
          <Select
            placeholder="区域"
            allowClear
            style={{ width: 140 }}
            options={AREA_OPTIONS.map((a) => ({ value: a, label: a }))}
            onChange={(v) => { setArea(v); setPage(1) }}
          />
          <Select
            value={status}
            style={{ width: 140 }}
            options={AUDIT_STATUS_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            onChange={(v) => { setStatus(v); setPage(1) }}
          />
          <RangePicker
            onChange={(dates) => {
              setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs] | null)
              setPage(1)
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          {selectedRowKeys.length > 0 && (
            <Popconfirm title={`确认通过 ${selectedRowKeys.length} 条记录？`} onConfirm={handleBatchApprove}>
              <Button type="primary" icon={<CheckOutlined />}>批量通过 ({selectedRowKeys.length})</Button>
            </Popconfirm>
          )}
        </Space>

        <Table
          columns={columns}
          dataSource={records}
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
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
            getCheckboxProps: (record) => ({ disabled: record.status !== 'pending' })
          }}
          size="middle"
        />
      </Card>

      <Modal
        title="驳回记录"
        open={rejectModalOpen}
        onOk={handleReject}
        onCancel={() => { setRejectModalOpen(false); setRejectTarget(null); setRejectReason('') }}
      >
        <Input.TextArea
          rows={3}
          placeholder="请填写驳回原因"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
      </Modal>
    </div>
  )
}
