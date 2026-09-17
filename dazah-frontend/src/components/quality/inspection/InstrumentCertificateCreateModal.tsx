'use client'

import { useEffect, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import {
  Alert,
  Button,
  Col,
  DatePicker,
  Descriptions,
  Form,
  Input,
  Modal,
  Row,
  Space,
  Spin,
  Typography,
  Upload,
} from 'antd'
import { FileTextOutlined, RobotOutlined, UploadOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd'

import {
  analyzeInstrumentCertificate,
  rematchInstrumentCertificate,
} from '@/actions/quality-inspection'
import type { InstrumentCertificateAnalyzeResult } from '@/types/quality'

const MAX_CERTIFICATE_MB = 20
const ACCEPT_TYPES = '.pdf,.png,.jpg,.jpeg'

interface InstrumentCertificateCreateModalProps {
  open: boolean
  onClose: () => void
  /** 识别（含人工修正+重新匹配）完成后把预填字段交给外部校准表新增弹窗 */
  onApply: (mappedFields: Record<string, unknown>) => void
}

interface RematchFormValues {
  instrument_name?: string
  model?: string
  serial_no?: string
  calibration_date?: Dayjs | null
  next_calibration_date_stated?: Dayjs | null
}

/** 上传校准证书 → AI 识别 → 人工修正关键字段 → 重新匹配 → 填入新增表单。 */
export function InstrumentCertificateCreateModal({
  open,
  onClose,
  onApply,
}: InstrumentCertificateCreateModalProps) {
  const [form] = Form.useForm<RematchFormValues>()
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [analyzing, setAnalyzing] = useState(false)
  const [rematching, setRematching] = useState(false)
  const [result, setResult] = useState<InstrumentCertificateAnalyzeResult | null>(null)
  const [errorText, setErrorText] = useState<string | null>(null)
  const [uploadName, setUploadName] = useState<string>('')

  const reset = () => {
    setFileList([])
    setAnalyzing(false)
    setRematching(false)
    setResult(null)
    setErrorText(null)
    setUploadName('')
    form.resetFields()
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const beforeUpload = (file: File) => {
    const isValidType = /\.(pdf|png|jpe?g)$/i.test(file.name)
    if (!isValidType) {
      setErrorText('仅支持 PDF / PNG / JPG 格式的校准证书')
      return Upload.LIST_IGNORE
    }
    if (file.size > MAX_CERTIFICATE_MB * 1024 * 1024) {
      setErrorText(`证书文件不能超过 ${MAX_CERTIFICATE_MB}MB`)
      return Upload.LIST_IGNORE
    }
    setErrorText(null)
    setResult(null)
    return false // 手动控制上传时机
  }

  const applyResult = (updated: InstrumentCertificateAnalyzeResult) => {
    setResult(updated)
    form.setFieldsValue({
      instrument_name: updated.extracted.instrument_name ?? undefined,
      model: updated.extracted.model ?? undefined,
      serial_no: updated.extracted.serial_no ?? undefined,
      calibration_date: updated.extracted.calibration_date
        ? dayjs(updated.extracted.calibration_date)
        : undefined,
      next_calibration_date_stated: updated.extracted.next_calibration_date_stated
        ? dayjs(updated.extracted.next_calibration_date_stated)
        : undefined,
    })
  }

  useEffect(() => {
    if (result) {
      form.setFieldsValue({
        instrument_name: result.extracted.instrument_name ?? undefined,
        model: result.extracted.model ?? undefined,
        serial_no: result.extracted.serial_no ?? undefined,
        calibration_date: result.extracted.calibration_date
          ? dayjs(result.extracted.calibration_date)
          : undefined,
        next_calibration_date_stated:
          result.extracted.next_calibration_date_stated
            ? dayjs(result.extracted.next_calibration_date_stated)
            : undefined,
      })
    }
  }, [result, form])

  const handleAnalyze = async () => {
    const file = fileList[0]?.originFileObj
    if (!file) return
    setAnalyzing(true)
    setErrorText(null)
    setUploadName(file.name)
    try {
      applyResult(await analyzeInstrumentCertificate(file))
    } catch (err) {
      setErrorText(err instanceof Error ? err.message : '证书识别失败，请重试')
    } finally {
      setAnalyzing(false)
    }
  }

  const handleRematch = async () => {
    if (!result) return
    try {
      const values = await form.validateFields()
      setRematching(true)
      setErrorText(null)
      applyResult(
        await rematchInstrumentCertificate({
          instrument_name: values.instrument_name || null,
          model: values.model || null,
          serial_no: values.serial_no || null,
          calibration_date: values.calibration_date
            ? values.calibration_date.format('YYYY-MM-DD')
            : null,
          next_calibration_date_stated: values.next_calibration_date_stated
            ? values.next_calibration_date_stated.format('YYYY-MM-DD')
            : null,
          certificate_no: result.extracted.certificate_no ?? null,
          calibration_agency: result.extracted.calibration_agency ?? null,
          conclusion: result.extracted.conclusion ?? null,
          attachment_file_token: result.attachment_file_token ?? null,
          attachment_name: uploadName || null,
        }),
      )
    } catch (err) {
      if (err instanceof Error) setErrorText(err.message)
    } finally {
      setRematching(false)
    }
  }

  const directory = result?.directory ?? { matched: false }

  return (
    <Modal
      title="上传校准证书识别新增"
      open={open}
      onCancel={handleClose}
      width={620}
      footer={
        <Space>
          <Button onClick={handleClose}>关闭</Button>
          {result && (
            <Button
              icon={<RobotOutlined />}
              loading={rematching}
              disabled={analyzing}
              onClick={handleRematch}
            >
              重新匹配
            </Button>
          )}
          {!result && (
            <Button
              type="primary"
              icon={<RobotOutlined />}
              loading={analyzing}
              disabled={fileList.length === 0}
              onClick={handleAnalyze}
            >
              开始识别
            </Button>
          )}
          {result && (
            <Button
              type="primary"
              icon={<FileTextOutlined />}
              disabled={rematching}
              onClick={() => {
                const mapped = result.mapped_fields ?? {}
                reset()
                onApply(mapped)
              }}
            >
              填入新增表单
            </Button>
          )}
        </Space>
      }
    >
      <Spin spinning={analyzing || rematching} tip={rematching ? '重新匹配中…' : 'AI 识别中，请稍候…'}>
        <Upload.Dragger
          accept={ACCEPT_TYPES}
          maxCount={1}
          beforeUpload={beforeUpload}
          fileList={fileList}
          onRemove={() => {
            setFileList([])
            setResult(null)
          }}
          onChange={({ fileList: next }) => setFileList(next)}
          disabled={analyzing || rematching || result !== null}
        >
          <p className="ant-upload-drag-icon">
            <UploadOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽校准证书到此处</p>
          <p className="ant-upload-hint">
            支持 PDF / PNG / JPG，单个文件不超过 {MAX_CERTIFICATE_MB}MB
          </p>
        </Upload.Dragger>

        {errorText && (
          <Alert type="error" showIcon message={errorText} style={{ marginTop: 12 }} />
        )}

        {result && (
          <div style={{ marginTop: 16 }}>
            <Typography.Title level={5} style={{ marginTop: 0 }}>
              识别结果（可修改后点「重新匹配」）
            </Typography.Title>
            <Form form={form} layout="vertical" size="small">
              <Row gutter={8}>
                <Col span={12}>
                  <Form.Item name="instrument_name" label="器具名称" style={{ marginBottom: 8 }}>
                    <Input allowClear />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="model" label="型号/规格" style={{ marginBottom: 8 }}>
                    <Input allowClear />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="serial_no"
                    label="出厂编号"
                    style={{ marginBottom: 8 }}
                    extra="识别有误时直接改正后点「重新匹配」，将按修正值重新查目录"
                  >
                    <Input allowClear />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item name="calibration_date" label="检定日期" style={{ marginBottom: 8 }}>
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item
                    name="next_calibration_date_stated"
                    label="有效期至"
                    style={{ marginBottom: 8 }}
                  >
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
            </Form>
            <Descriptions
              size="small"
              column={1}
              bordered
              items={[
                {
                  key: 'next',
                  label: '下次检定日期（推算）',
                  children: result.computed_next_calibration_date ?? '-',
                },
                {
                  key: 'location',
                  label: '使用地点（目录）',
                  children: directory.matched
                    ? (directory.location ?? '-')
                    : '未匹配到设备',
                },
                {
                  key: 'period',
                  label: '检定周期（目录）',
                  children: directory.matched
                    ? directory.period_months
                      ? `${directory.period_months} 个月`
                      : '-'
                    : '未匹配到设备',
                },
                {
                  key: 'match',
                  label: '目录匹配依据',
                  children: directory.matched ? (directory.match_by ?? '-') : '-',
                },
                {
                  key: 'agency',
                  label: '检定机构',
                  children: result.extracted.calibration_agency ?? '-',
                },
                { key: 'cert_no', label: '证书编号', children: result.extracted.certificate_no ?? '-' },
                { key: 'conclusion', label: '结论', children: result.extracted.conclusion ?? '-' },
              ]}
            />
            {(result.warnings ?? []).length > 0 && (
              <Alert
                type="warning"
                showIcon
                message="识别提示"
                description={
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {(result.warnings ?? []).map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                }
                style={{ marginTop: 12 }}
              />
            )}
          </div>
        )}
      </Spin>
    </Modal>
  )
}
