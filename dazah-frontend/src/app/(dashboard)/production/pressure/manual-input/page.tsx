'use client'

import { useEffect, useState } from 'react'
import {
  Card,
  Typography,
  Select,
  DatePicker,
  Button,
  Table,
  InputNumber,
  Space,
  Spin,
  Modal,
  Form,
  Input,
  Empty,
  App,
} from 'antd'
import { SendOutlined, ReloadOutlined, PlusOutlined } from '@ant-design/icons'
import {
  getPointMappings,
  createPointMapping,
  checkPointIdUnique,
  createBatchManualRecord,
} from '@/actions/pressure'
import { AREA_OPTIONS } from '@/types/pressure'
import type { PointMapping } from '@/types/pressure'
import dayjs from 'dayjs'

const { Title, Text } = Typography

export default function ManualInputPage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [area, setArea] = useState<string>('无菌区')
  const [selectedDate, setSelectedDate] = useState<dayjs.Dayjs>(dayjs())
  const [points, setPoints] = useState<PointMapping[]>([])
  const [values, setValues] = useState<Record<string, number | null>>({})
  const [timeSlots, setTimeSlots] = useState<string[]>(['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'])
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [addForm] = Form.useForm()

  useEffect(() => {
    // eslint-disable-next-line react-hooks/immutability
    loadPoints()
  }, [area])

  async function loadPoints() {
    setLoading(true)
    try {
      const res = await getPointMappings({ area, page_size: 200 })
      if (res.code === 200) {
        const data = res.data || []
        setPoints(data)
        const initial: Record<string, number | null> = {}
        for (const p of data) {
          for (const slot of timeSlots) {
            initial[`${p.point_id}::${slot}`] = null
          }
        }
        setValues(initial)
      }
    } catch {
      message.error('加载位点失败')
    } finally {
      setLoading(false)
    }
  }

  const handleAddPoint = async () => {
    try {
      const values = await addForm.validateFields()
      const check = await checkPointIdUnique(values.point_id)
      if (check.data?.exists) {
        message.error(`位点编号 ${values.point_id} 已存在`)
        return
      }
      const res = await createPointMapping({
        ...values,
        area,
      })
      if (res.code === 200) {
        message.success('位点添加成功')
        setAddModalOpen(false)
        addForm.resetFields()
        loadPoints()
      } else {
        message.error(res.message || '添加失败')
      }
    } catch {
      // validation error
    }
  }

  const handleSubmit = async () => {
    const filledValues: Record<string, number | null> = {}
    let hasValue = false
    for (const [key, val] of Object.entries(values)) {
      if (val !== null && val !== undefined) {
        filledValues[key] = val
        hasValue = true
      }
    }
    if (!hasValue) {
      message.warning('请至少填写一个压差值')
      return
    }

    setSubmitting(true)
    try {
      const res = await createBatchManualRecord({
        area,
        rows: [{ date: selectedDate.format('YYYY-MM-DD'), values: filledValues }],
        time_slots: timeSlots,
      })
      if (res.code === 200) {
        message.success(`成功提交 ${res.data?.success_count || 0} 条记录`)
        const cleared: Record<string, number | null> = {}
        for (const key of Object.keys(values)) {
          cleared[key] = null
        }
        setValues(cleared)
      } else {
        message.error(res.message || '提交失败')
      }
    } catch {
      message.error('提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  const columns = [
    {
      title: '位点编号',
      dataIndex: 'point_id',
      key: 'point_id',
      width: 150,
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '标准压差 (Pa)',
      dataIndex: 'standard_pressure',
      key: 'standard_pressure',
      width: 120,
      align: 'center' as const,
    },
    ...timeSlots.map((slot) => ({
      title: slot,
      key: slot,
      width: 120,
      align: 'center' as const,
      render: (_: any, record: PointMapping) => {
        const key = `${record.point_id}::${slot}`
        return (
          <InputNumber
            size="small"
            value={values[key] ?? undefined}
            onChange={(v) => setValues({ ...values, [key]: v })}
            placeholder="-"
            style={{ width: 80 }}
          />
        )
      },
    })),
  ]

  return (
    <div className="space-y-4">
      <Title level={4}>手动录入</Title>

      <Card variant="borderless" className="shadow-sm">
        <Space wrap className="mb-4">
          <Select
            value={area}
            style={{ width: 140 }}
            options={AREA_OPTIONS.map((a) => ({ value: a, label: a }))}
            onChange={(v) => setArea(v)}
          />
          <DatePicker
            value={selectedDate}
            onChange={(d) => d && setSelectedDate(d)}
          />
          <Button icon={<ReloadOutlined />} onClick={loadPoints}>刷新位点</Button>
          <Button icon={<PlusOutlined />} onClick={() => setAddModalOpen(true)}>
            新增位点
          </Button>
          <Button type="primary" icon={<SendOutlined />} loading={submitting} onClick={handleSubmit}>
            提交
          </Button>
        </Space>

        <div className="mb-2">
          <Text type="secondary">时段列：</Text>
          <Space>
            {timeSlots.map((slot, idx) => (
              <Input
                key={idx}
                size="small"
                value={slot}
                onChange={(e) => {
                  const newSlots = [...timeSlots]
                  newSlots[idx] = e.target.value
                  setTimeSlots(newSlots)
                }}
                style={{ width: 80 }}
              />
            ))}
          </Space>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <Spin size="large" />
          </div>
        ) : points.length === 0 ? (
          <Empty
            description="该区域暂无位点，请先添加位点"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Table
            columns={columns}
            dataSource={points}
            rowKey="id"
            pagination={false}
            size="small"
            scroll={{ y: 500 }}
          />
        )}
      </Card>

      <Modal
        title="新增位点"
        open={addModalOpen}
        onOk={handleAddPoint}
        onCancel={() => { setAddModalOpen(false); addForm.resetFields() }}
      >
        <Form form={addForm} layout="vertical">
          <Form.Item
            name="point_id"
            label="位点编号"
            rules={[{ required: true, message: '请输入位点编号' }]}
          >
            <Input placeholder="如 PD-0101" />
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
