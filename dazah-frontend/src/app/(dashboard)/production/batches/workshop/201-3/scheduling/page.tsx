'use client'
// 提炼车间 — 排产：放罐/接罐计划
// 数据源：102 发酵车间排产 Excel 的放罐计划（后端解析），即提炼车间接罐计划
// 接罐执行确认：待接罐 → 确认接罐 / 填报延期 →（无资质）待班组长审批

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, App, Button, Card, Col, Descriptions, Form, Input, Modal, Row, Select, Space, Spin, Statistic, Table, Tag, Typography, Upload } from 'antd'
import { BellOutlined, CalendarOutlined, ScheduleOutlined, UploadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'

const { Title, Text } = Typography

const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

// 延期原因选项（单选）
const DELAY_REASONS = ['等料', '等水', '等蒸汽', '人员不足', '设备问题', '其他']

// 接罐任务状态展示（task_status）
const TASK_STATUS_META: Record<string, { color: string; label: string }> = {
  pending: { color: 'blue', label: '待接罐' },
  confirmed: { color: 'green', label: '已确认' },
  delayed: { color: 'red', label: '已延期' },
  pending_approval: { color: 'purple', label: '待班组长审批' },
  cancelled: { color: 'default', label: '已取消' },
}

interface DumpPlan {
  batch_no: string
  tank_no: string
  product_type: string
  dump_date: string
  year: number
  month: number
  day: number
  in_db: boolean
  is_past: boolean
  status: string
  task_status: string | null
  actual_time: string | null
  confirmed_by: string | null
  actual_tank_no: string | null
  delay_reason: string | null
}

interface DumpResponse {
  version: { file: string; sheet: string; upload_time?: string } | null
  today: string
  items: DumpPlan[]
  summary: { total: number; past: number; upcoming: number }
}

export default function Scheduling2013Page() {
  const { message } = App.useApp()
  const [data, setData] = useState<DumpResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // 默认显示当前月份（如数据里无当前月份则回退为全部）
  const [month, setMonth] = useState(dayjs().format('YYYY-MM'))
  const [tank, setTank] = useState('')
  const [status, setStatus] = useState('')

  // 三个操作弹窗的目标行 + 表单
  const [confirmTarget, setConfirmTarget] = useState<DumpPlan | null>(null)
  const [delayTarget, setDelayTarget] = useState<DumpPlan | null>(null)
  const [approveTarget, setApproveTarget] = useState<DumpPlan | null>(null)
  const [actualTank, setActualTank] = useState('')
  const [confirmNote, setConfirmNote] = useState('')
  const [delayReason, setDelayReason] = useState('')
  const [delayNote, setDelayNote] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const loadData = useCallback(() => {
    setLoading(true)
    setError('')
    fetch(`${API}/api/v1/production/dr/schedule/dump-plans`)
      .then((r) => r.json())
      .then((json) => {
        if (json.code === 200) setData(json.data)
        else setError(json.message || '加载失败')
      })
      .catch((e) => setError(e.message || '网络错误'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadData() }, [loadData]) // eslint-disable-line react-hooks/set-state-in-effect

  // 计划员上传最新排产 Excel → 后端保存到 schedule_data，上传后刷新列表
  const handleUploadExcel = async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await fetch(`${API}/api/v1/production/dr/schedule/upload`, { method: 'POST', body: fd })
      const json = await res.json()
      if (json.code === 200) {
        message.success(json.message || '排产已更新')
        loadData()
      } else {
        message.error(json.message || '上传失败')
      }
    } catch (e: any) {
      message.error('上传失败：' + (e?.message || '网络错误'))
    }
    return false // 阻止 antd 默认上传
  }

  // ── 接罐操作 ──
  const submitConfirm = async () => {
    if (!confirmTarget) return
    setSubmitting(true)
    try {
      const res = await fetch(`${API}/api/v1/production/dr/schedule/tasks/${encodeURIComponent(confirmTarget.batch_no)}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actual_tank_no: actualTank || confirmTarget.tank_no, note: confirmNote }),
      })
      const json = await res.json()
      if (json.code === 200) {
        message.success(json.message)
        setConfirmTarget(null); setActualTank(''); setConfirmNote('')
        loadData()
      } else {
        message.error(json.message || '确认失败')
      }
    } catch {
      message.error('网络错误，确认失败')
    } finally {
      setSubmitting(false)
    }
  }

  const submitDelay = async () => {
    if (!delayTarget) return
    if (!delayReason) {
      message.warning('请选择延期原因')
      return
    }
    setSubmitting(true)
    try {
      const res = await fetch(`${API}/api/v1/production/dr/schedule/tasks/${encodeURIComponent(delayTarget.batch_no)}/delay`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ delay_reason: delayReason, note: delayNote }),
      })
      const json = await res.json()
      if (json.code === 200) {
        message.success(json.message)
        setDelayTarget(null); setDelayReason(''); setDelayNote('')
        loadData()
      } else {
        message.error(json.message || '提交失败')
      }
    } catch {
      message.error('网络错误，提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  const submitApprove = async (approve: boolean) => {
    if (!approveTarget) return
    setSubmitting(true)
    try {
      const res = await fetch(`${API}/api/v1/production/dr/schedule/tasks/${encodeURIComponent(approveTarget.batch_no)}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approve }),
      })
      const json = await res.json()
      if (json.code === 200) {
        message.success(json.message)
        setApproveTarget(null)
        loadData()
      } else {
        message.error(json.message || '审批失败')
      }
    } catch {
      message.error('网络错误，审批失败')
    } finally {
      setSubmitting(false)
    }
  }

  const today = dayjs()
  const weekEnd = today.add(7, 'day')

   
   
  const items = data?.items || [] // eslint-disable-line react-hooks/exhaustive-deps
  const monthOptions = useMemo(() => {
    const set = new Set<string>()
    items.forEach((i) => set.add(`${i.year}-${String(i.month).padStart(2, '0')}`))
    return [...set].sort()
  }, [items])

  // 数据加载后：若当前月份不在可选项（当月无排产），回退显示全部
  useEffect(() => {
    if (month && monthOptions.length > 0 && !monthOptions.includes(month)) {
      setMonth('') // eslint-disable-line react-hooks/set-state-in-effect
    }
  }, [month, monthOptions])
  const tankOptions = useMemo(() => [...new Set(items.map((i) => i.tank_no))].sort(), [items])

  const filtered = useMemo(() => items.filter((i) => {
    if (month && `${i.year}-${String(i.month).padStart(2, '0')}` !== month) return false
    if (tank && i.tank_no !== tank) return false
    if (status === 'upcoming' && i.is_past) return false
    if (status === 'completed' && !i.is_past) return false
    if (status === 'soon') {
      const d = dayjs(i.dump_date)
      if (i.is_past || d.isAfter(weekEnd)) return false
    }
    // 接罐任务状态筛选
    if (status === 'task_pending' && !(i.task_status === null || i.task_status === 'pending')) return false
    if (status === 'task_confirmed' && i.task_status !== 'confirmed') return false
    if (status === 'task_delayed' && i.task_status !== 'delayed') return false
    if (status === 'task_approval' && i.task_status !== 'pending_approval') return false
    return true
  }), [items, month, tank, status, weekEnd])

  // 统计卡随筛选联动：基于当前筛选结果（月份/罐号/状态）计算
  const filteredPast = filtered.filter((i) => i.is_past).length
  const filteredSoon = filtered.filter((i) => {
    const d = dayjs(i.dump_date)
    return !i.is_past && !d.isAfter(weekEnd)
  }).length

  const columns: ColumnsType<DumpPlan> = [
    {
      title: '放罐日期',
      dataIndex: 'dump_date',
      key: 'dump_date',
      width: 110,
      sorter: (a, b) => a.dump_date.localeCompare(b.dump_date),
      defaultSortOrder: 'ascend',
    },
    { title: '批号', dataIndex: 'batch_no', key: 'batch_no', render: (t) => <Text strong>{t}</Text> },
    { title: '罐号', dataIndex: 'tank_no', key: 'tank_no', width: 90 },
    {
      title: '类型',
      dataIndex: 'product_type',
      key: 'product_type',
      width: 80,
      render: (t) => <Tag color={t === '正式批' ? 'blue' : 'purple'}>{t}</Tag>,
    },
    {
      title: 'DB状态',
      dataIndex: 'in_db',
      key: 'in_db',
      width: 100,
      render: (v) => (v ? <Tag color="green">已投产</Tag> : <Tag>未投产</Tag>),
    },
    {
      title: '状态',
      key: 'status',
      width: 110,
      render: (_, r) => {
        if (r.is_past) return <Tag color="default">已放罐</Tag>
        const d = dayjs(r.dump_date)
        if (d.isSame(today, 'day')) return <Tag color="volcano">今日接罐</Tag>
        if (!d.isAfter(weekEnd)) return <Tag color="red">即将接罐</Tag>
        return <Tag color="processing">待放罐</Tag>
      },
    },
    {
      title: '接罐状态',
      key: 'task_status',
      width: 130,
      render: (_, r) => {
        const meta = r.task_status ? TASK_STATUS_META[r.task_status] : null
        if (!meta) return <Tag>未生成</Tag>
        return (
          <Space size={4} direction="vertical" style={{ rowGap: 2 }}>
            <Tag color={meta.color}>{meta.label}</Tag>
            {(r.task_status === 'confirmed' && r.actual_time) && (
              <Text type="secondary" style={{ fontSize: 12 }}>{r.actual_time.slice(5, 16)}</Text>
            )}
          </Space>
        )
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_, r) => {
        if (r.task_status === 'confirmed') {
          return <Text type="secondary" style={{ fontSize: 12 }}>{r.confirmed_by || '已确认'}</Text>
        }
        if (r.task_status === 'delayed') {
          return <Tag color="orange">{r.delay_reason || '延期'}</Tag>
        }
        if (r.task_status === 'pending_approval') {
          return <Button size="small" color="purple" variant="outlined" onClick={() => setApproveTarget(r)}>审批</Button>
        }
        // pending / 未生成：可确认或延期
        return (
          <Space size={4}>
            <Button size="small" type="primary" onClick={() => setConfirmTarget(r)}>确认接罐</Button>
            <Button size="small" onClick={() => setDelayTarget(r)}>延期</Button>
          </Space>
        )
      },
    },
  ]

  return (
    <div className="p-6">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <ScheduleOutlined className="mr-2" />排产 — 放罐/接罐计划
          </Title>
          <Text type="secondary">
            102 发酵车间排产放罐计划 = 提炼车间接罐计划（数据源：排产 Excel 最新版）
          </Text>
        </div>
        <Upload accept=".xlsx" showUploadList={false} beforeUpload={handleUploadExcel}>
          <Button type="primary" icon={<UploadOutlined />}>更新排产</Button>
        </Upload>
      </div>

      {error && <Alert type="error" title={error} showIcon className="mb-4" />}

      {loading ? (
        <div className="flex justify-center py-20"><Spin size="large" /></div>
      ) : data ? (
        <>
          <Alert
            type={filteredSoon > 0 ? 'warning' : 'info'}
            showIcon
            icon={<BellOutlined />}
            className="mb-4"
            title={`未来 7 天内有 ${filteredSoon} 批待接罐`}
            description={data.version
              ? `排产版本：${data.version.file}${data.version.upload_time ? `（上传时间：${data.version.upload_time}）` : ''}`
              : ''}
          />

          <Row gutter={16} className="mb-4">
            <Col span={6}>
              <Card><Statistic title="放罐计划总数" value={filtered.length} suffix="批" /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title="已放罐" value={filteredPast} suffix="批" valueStyle={{ color: '#999' }} /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title="待放罐" value={filtered.length - filteredPast} suffix="批" valueStyle={{ color: '#1677ff' }} /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title="未来7天待接罐" value={filteredSoon} suffix="批" valueStyle={{ color: filteredSoon > 0 ? '#f5222d' : '#52c41a' }} /></Card>
            </Col>
          </Row>

          <Card
            title={<Space><CalendarOutlined />接罐列表</Space>}
            extra={(
              <Space wrap>
                <Select placeholder="全部月份" allowClear style={{ width: 120 }} value={month || undefined}
                  options={monthOptions.map((m) => ({ value: m, label: m }))} onChange={setMonth} />
                <Select placeholder="全部罐号" allowClear style={{ width: 110 }} value={tank || undefined}
                  options={tankOptions.map((t) => ({ value: t, label: t }))} onChange={setTank} />
                <Select placeholder="全部状态" allowClear style={{ width: 130 }} value={status || undefined}
                  options={[
                    { value: 'soon', label: '未来7天' },
                    { value: 'upcoming', label: '待放罐' },
                    { value: 'completed', label: '已放罐' },
                    { value: 'task_pending', label: '待接罐' },
                    { value: 'task_confirmed', label: '已确认' },
                    { value: 'task_delayed', label: '已延期' },
                    { value: 'task_approval', label: '待审批' },
                  ]}
                  onChange={setStatus} />
              </Space>
            )}
          >
            <Table
              rowKey={(r) => `${r.dump_date}-${r.batch_no}`}
              columns={columns}
              dataSource={filtered}
              size="small"
              pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
              rowClassName={(r) => {
                const d = dayjs(r.dump_date)
                if (!r.is_past && !d.isAfter(weekEnd)) return 'soon-row'
                return ''
              }}
            />
          </Card>

          <style>{`
            .soon-row > td { background: #fff1f0 !important; }
          `}</style>
        </>
      ) : (
        <div className="text-center py-10 text-gray-400">暂无排产数据（请在排产 Excel 目录放置最新计划文件）</div>
      )}

      {/* ── 确认接罐弹窗 ── */}
      <Modal
        title="确认接罐"
        open={Boolean(confirmTarget)}
        onCancel={() => { setConfirmTarget(null); setActualTank(''); setConfirmNote('') }}
        onOk={submitConfirm}
        confirmLoading={submitting}
        okText="确认接罐"
        width={460}
      >
        {confirmTarget && (
          <Descriptions size="small" column={1} style={{ marginBottom: 12 }}>
            <Descriptions.Item label="批号">{confirmTarget.batch_no}</Descriptions.Item>
            <Descriptions.Item label="计划罐号">{confirmTarget.tank_no}</Descriptions.Item>
            <Descriptions.Item label="计划日期">{confirmTarget.dump_date}</Descriptions.Item>
          </Descriptions>
        )}
        <Form layout="vertical">
          <Form.Item label="实测罐号" extra="不选则默认取计划罐号">
            <Select
              placeholder="选择实测罐号"
              allowClear
              value={actualTank || undefined}
              onChange={setActualTank}
              options={[
                ...new Set([...(confirmTarget ? [confirmTarget.tank_no] : []), ...tankOptions]),
              ].map((t) => ({ value: t, label: t }))}
            />
          </Form.Item>
          <Form.Item label="备注">
            <Input.TextArea rows={2} value={confirmNote} onChange={(e) => setConfirmNote(e.target.value)} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── 填报延期弹窗 ── */}
      <Modal
        title="填报延期原因"
        open={Boolean(delayTarget)}
        onCancel={() => { setDelayTarget(null); setDelayReason(''); setDelayNote('') }}
        onOk={submitDelay}
        confirmLoading={submitting}
        okText="提交延期"
        width={460}
      >
        {delayTarget && (
          <Descriptions size="small" column={1} style={{ marginBottom: 12 }}>
            <Descriptions.Item label="批号">{delayTarget.batch_no}</Descriptions.Item>
            <Descriptions.Item label="计划罐号">{delayTarget.tank_no}</Descriptions.Item>
            <Descriptions.Item label="计划日期">{delayTarget.dump_date}</Descriptions.Item>
          </Descriptions>
        )}
        <Form layout="vertical">
          <Form.Item label="延期原因" required>
            <Select
              placeholder="选择延期原因"
              value={delayReason || undefined}
              onChange={setDelayReason}
              options={DELAY_REASONS.map((r) => ({ value: r, label: r }))}
            />
          </Form.Item>
          <Form.Item label="备注">
            <Input.TextArea rows={2} value={delayNote} onChange={(e) => setDelayNote(e.target.value)} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── 班组长审批弹窗 ── */}
      <Modal
        title="班组长审批 — 接罐确认"
        open={Boolean(approveTarget)}
        onCancel={() => setApproveTarget(null)}
        confirmLoading={submitting}
        width={460}
        footer={[
          <Button key="reject" danger disabled={submitting} onClick={() => submitApprove(false)}>驳回</Button>,
          <Button key="ok" type="primary" loading={submitting} onClick={() => submitApprove(true)}>批准接罐</Button>,
        ]}
      >
        {approveTarget && (
          <>
            <Descriptions size="small" column={1} style={{ marginBottom: 12 }}>
              <Descriptions.Item label="批号">{approveTarget.batch_no}</Descriptions.Item>
              <Descriptions.Item label="计划罐号">{approveTarget.tank_no}</Descriptions.Item>
              <Descriptions.Item label="计划日期">{approveTarget.dump_date}</Descriptions.Item>
              <Descriptions.Item label="确认人">{approveTarget.confirmed_by || '—'}</Descriptions.Item>
              <Descriptions.Item label="实测罐号">{approveTarget.actual_tank_no || '—'}</Descriptions.Item>
            </Descriptions>
            <Text type="secondary">该批次接罐确认由现场人员提交，需班组长审批通过后生效。</Text>
          </>
        )}
      </Modal>
    </div>
  )
}
