'use client'

import { useState } from 'react'
import {
  Card,
  Typography,
  Upload,
  Button,
  Table,
  InputNumber,
  Input,
  Space,
  Spin,
  App,
  Tag,
  Steps,
} from 'antd'
import { UploadOutlined, SendOutlined, CameraOutlined } from '@ant-design/icons'
import { createOcrTask, submitOcrTaskResult } from '@/actions/pressure'
import type { OcrResultRecord } from '@/types/pressure'

const { Title, Text } = Typography

export default function OcrInputPage() {
  const { message } = App.useApp()
  const [currentStep, setCurrentStep] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [imageUrl, setImageUrl] = useState('')
  const [records, setRecords] = useState<OcrResultRecord[]>([])
  const [editableRecords, setEditableRecords] = useState<OcrResultRecord[]>([])

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      // 简化处理：将图片转为 base64 URL（实际应上传到文件服务）
      const reader = new FileReader()
      reader.onload = async () => {
        const url = reader.result as string
        setImageUrl(url)

        const res = await createOcrTask({ image_url: url })
        if (res.code === 200 && res.data) {
          setTaskId(res.data.id)
          if (res.data.result?.records) {
            setRecords(res.data.result.records)
            setEditableRecords([...res.data.result.records])
          }
          setCurrentStep(1)
          message.success('OCR 识别完成，请核对结果')
        } else {
          message.error(res.message || '识别失败')
        }
        setUploading(false)
      }
      reader.readAsDataURL(file)
    } catch {
      message.error('上传失败')
      setUploading(false)
    }
    return false // prevent default upload
  }

  const handleSubmit = async () => {
    if (!taskId) return
    setSubmitting(true)
    try {
      const res = await submitOcrTaskResult(taskId, {
        records: editableRecords.map((r) => ({
          record_time: r.record_time,
          point_id: r.point_id,
          pressure_value: r.pressure_value,
          area: '其他',
          time_slot: r.time_slot,
        })),
      })
      if (res.code === 200) {
        message.success(`成功提交 ${res.data?.success_count || 0} 条记录`)
        setCurrentStep(2)
      } else {
        message.error(res.message || '提交失败')
      }
    } catch {
      message.error('提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleReset = () => {
    setCurrentStep(0)
    setTaskId(null)
    setImageUrl('')
    setRecords([])
    setEditableRecords([])
  }

  const updateRecord = (index: number, field: string, value: any) => {
    const updated = [...editableRecords]
    updated[index] = { ...updated[index], [field]: value }
    setEditableRecords(updated)
  }

  const columns = [
    {
      title: '位点编号',
      key: 'point_id',
      width: 130,
      render: (_: any, record: OcrResultRecord, index: number) => (
        <Input
          size="small"
          value={editableRecords[index]?.point_id}
          onChange={(e) => updateRecord(index, 'point_id', e.target.value)}
        />
      ),
    },
    {
      title: '压差值 (Pa)',
      key: 'pressure_value',
      width: 120,
      render: (_: any, record: OcrResultRecord, index: number) => (
        <InputNumber
          size="small"
          value={editableRecords[index]?.pressure_value}
          onChange={(v) => updateRecord(index, 'pressure_value', v)}
          style={{ width: 90 }}
        />
      ),
    },
    {
      title: '时段',
      key: 'time_slot',
      width: 100,
      render: (_: any, record: OcrResultRecord, index: number) => (
        <Input
          size="small"
          value={editableRecords[index]?.time_slot || ''}
          onChange={(e) => updateRecord(index, 'time_slot', e.target.value)}
        />
      ),
    },
    {
      title: '记录时间',
      key: 'record_time',
      width: 170,
      render: (_: any, record: OcrResultRecord, index: number) => (
        <Text>{editableRecords[index]?.record_time}</Text>
      ),
    },
    {
      title: '记录人',
      key: 'recorder',
      width: 100,
      render: (_: any, record: OcrResultRecord, index: number) => (
        <Text>{editableRecords[index]?.recorder}</Text>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <Title level={4}>OCR 识别录入</Title>

      <Card variant="borderless" className="shadow-sm">
        <Steps
          current={currentStep}
          items={[
            { title: '上传图片' },
            { title: '核对结果' },
            { title: '提交完成' },
          ]}
          className="mb-6"
        />

        {currentStep === 0 && (
          <div className="text-center py-12">
            {uploading ? (
              <Spin size="large" description="正在识别中..." />
            ) : (
              <Upload.Dragger
                accept="image/*"
                showUploadList={false}
                beforeUpload={handleUpload}
                className="max-w-md mx-auto"
              >
                <p className="text-4xl mb-4 text-[var(--color-primary)]">
                  <CameraOutlined />
                </p>
                <p className="text-lg mb-2">点击或拖拽上传图片</p>
                <p className="text-sm text-[var(--color-muted)]">
                  支持 JPG、PNG 格式，系统将自动识别压差记录
                </p>
              </Upload.Dragger>
            )}
          </div>
        )}

        {currentStep === 1 && (
          <div>
            <div className="mb-4 flex justify-between items-center">
              <Text>共识别到 {editableRecords.length} 条记录，请核对后提交</Text>
              <Space>
                <Button onClick={handleReset}>重新上传</Button>
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  loading={submitting}
                  onClick={handleSubmit}
                >
                  提交
                </Button>
              </Space>
            </div>
            <Table
              columns={columns}
              dataSource={editableRecords}
              rowKey={(_, index) => String(index)}
              pagination={false}
              size="small"
            />
          </div>
        )}

        {currentStep === 2 && (
          <div className="text-center py-12">
            <p className="text-4xl mb-4 text-green-500">✓</p>
            <p className="text-lg mb-4">提交成功！</p>
            <Button type="primary" onClick={handleReset}>
              继续录入
            </Button>
          </div>
        )}
      </Card>
    </div>
  )
}
