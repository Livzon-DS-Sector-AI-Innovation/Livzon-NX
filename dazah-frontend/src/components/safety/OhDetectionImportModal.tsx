'use client'

import { useCallback, useMemo, useState } from 'react'
import {
  App,
  Button,
  Collapse,
  Descriptions,
  Form,
  Input,
  Modal,
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
} from 'antd'
import { InboxOutlined, FilePdfOutlined } from '@ant-design/icons'
import PlatformNotice from '@/components/shared/PlatformNotice'
import {
  parseOhDetectionReport,
  importOhDetectionReport,
} from '@/actions/safety'
import {
  OH_DETECTION_FACTOR_CATEGORY_OPTIONS,
  OH_DETECTION_PARSE_MODE_OPTIONS,
  type OhDetectionParsePreview,
} from '@/types/safety'

const { Text } = Typography
const MAX_FILE_SIZE = 30 * 1024 * 1024

const CATEGORY_LABELS: Record<string, string> = Object.fromEntries(
  OH_DETECTION_FACTOR_CATEGORY_OPTIONS.map((o) => [o.value, o.label])
)

const MODE_LABELS: Record<string, { label: string; color: string }> =
  Object.fromEntries(
    OH_DETECTION_PARSE_MODE_OPTIONS.map((o) => [o.value, { label: o.label, color: 'blue' }])
  )

export interface OhDetectionImportModalProps {
  open: boolean
  onClose: () => void
  onImported: () => void
}

interface MetaFormValues {
  report_no: string
  report_name?: string
  company_name?: string
  detection_agency?: string
  detection_date?: string
  remark?: string
}

export default function OhDetectionImportModal({
  open,
  onClose,
  onImported,
}: OhDetectionImportModalProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<MetaFormValues>()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<OhDetectionParsePreview | null>(null)
  const [parsing, setParsing] = useState(false)
  const [importing, setImporting] = useState(false)

  const reset = useCallback(() => {
    setFile(null)
    setPreview(null)
    setParsing(false)
    setImporting(false)
    form.resetFields()
  }, [form])

  const handleClose = useCallback(() => {
    if (importing) return
    reset()
    onClose()
  }, [importing, reset, onClose])

  const handleFile = useCallback(
    async (selected: File) => {
      if (!selected.name.toLowerCase().endsWith('.pdf')) {
        message.error('仅支持 PDF 格式的检测报告')
        return
      }
      if (selected.size > MAX_FILE_SIZE) {
        message.error('检测报告文件不能超过 30MB')
        return
      }
      setFile(selected)
      setPreview(null)
      setParsing(true)
      const res = await parseOhDetectionReport(selected)
      setParsing(false)
      if (res.code !== 200 || !res.data) {
        message.error(res.message || '解析失败，请检查文件')
        return
      }
      setPreview(res.data)
      form.setFieldsValue({
        report_no: res.data.report_no,
        report_name: res.data.report_name,
        company_name: res.data.company_name,
        detection_agency: res.data.detection_agency,
        remark: undefined,
      })
    },
    [form, message]
  )

  const handleImport = useCallback(async () => {
    if (!file) return
    const values = await form.validateFields()
    setImporting(true)
    const res = await importOhDetectionReport(file, {
      report_no: values.report_no,
      report_name: values.report_name,
      company_name: values.company_name,
      detection_agency: values.detection_agency,
      detection_date: values.detection_date,
      remark: values.remark,
    })
    setImporting(false)
    if (res.code !== 200 || !res.data) {
      message.error(res.message || '导入失败，请重试')
      return
    }
    const skipped = res.data.skipped_tables || []
    message.success(
      `导入成功：${res.data.imported_count} 条检测记录` +
        (res.data.replaced ? '（已覆盖同编号报告）' : '') +
        (res.data.monitors_synced
          ? `，已同步 ${res.data.monitors_synced} 条车间监测记录`
          : '') +
        (skipped.length ? `，${skipped.length} 张表未识别已跳过` : '')
    )
    reset()
    onImported()
  }, [file, form, message, onImported, reset])

  const summaryItems = useMemo(() => {
    if (!preview) return []
    return preview.tables.map((table, index) => ({
      key: String(index),
      label: (
        <Space wrap size={4}>
          <Text strong>{table.table_ref || '未编号'}</Text>
          <Text>{table.table_title}</Text>
          <Tag color={table.mode === 'skipped' ? 'orange' : (MODE_LABELS[table.mode]?.color ?? 'blue')}>
            {table.mode === 'skipped' ? '跳过' : (MODE_LABELS[table.mode]?.label ?? table.mode)}
          </Tag>
          <Text type="secondary">{table.row_count} 条</Text>
          {table.warnings.length > 0 && (
            <Tag color="gold">{table.warnings.length} 条警告</Tag>
          )}
        </Space>
      ),
      children: (
        <div className="space-y-2">
          {table.warnings.length > 0 && (
            <PlatformNotice
              type="warning"
              showRulesLink={false}
              message={table.warnings.slice(0, 3).join('；')}
            />
          )}
          {table.sample_rows.length > 0 && (
            <Descriptions
              bordered
              size="small"
              column={3}
              items={[
                { key: 'c', label: '类别', children: CATEGORY_LABELS[table.sample_rows[0].factor_category] ?? table.sample_rows[0].factor_category },
                { key: 'f', label: '检测项目', children: table.sample_rows.map((r) => r.factor_name).filter((v, i, a) => a.indexOf(v) === i).slice(0, 3).join('、') },
                { key: 's', label: '样例点位', children: table.sample_rows[0].sample_point || table.sample_rows[0].post || '-' },
              ]}
            />
          )}
        </div>
      ),
    }))
  }, [preview])

  return (
    <Modal
      open={open}
      title="导入检测报告（PDF 自动识别）"
      width={760}
      onCancel={handleClose}
      destroyOnHidden
      footer={
        preview
          ? [
              <Button key="back" onClick={handleClose} disabled={importing}>
                取消
              </Button>,
              <Button
                key="import"
                type="primary"
                loading={importing}
                onClick={handleImport}
              >
                确认导入
              </Button>,
            ]
          : null
      }
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Upload.Dragger
          accept=".pdf"
          multiple={false}
          showUploadList={!!file && !preview}
          fileList={
            file && !preview
              ? [{ uid: '-1', name: file.name, status: 'done' }]
              : []
          }
          beforeUpload={(selected) => {
            void handleFile(selected)
            return false
          }}
          onRemove={() => {
            setFile(null)
            setPreview(null)
          }}
          disabled={parsing || importing}
        >
          {parsing ? (
            <Spin indicator={<FilePdfOutlined style={{ fontSize: 32 }} spin />} />
          ) : (
            <InboxOutlined style={{ fontSize: 32, color: '#1677ff' }} />
          )}
          <div style={{ marginTop: 8 }}>
            {parsing ? '正在识别报告内容…' : '点击或拖拽检测报告 PDF 到此处'}
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            支持第三方检测机构职业病危害因素检测报告，≤30MB
          </Text>
        </Upload.Dragger>

        {preview && (
          <>
            {preview.existing_report_id && (
              <PlatformNotice
                type="warning"
                showRulesLink={false}
                message={`报告编号已存在，导入将覆盖原 ${preview.existing_total_points} 条检测明细`}
              />
            )}
            <Descriptions
              bordered
              size="small"
              column={4}
              items={[
                { key: 'tables', label: '识别表格', children: `${preview.table_count} 张` },
                { key: 'points', label: '检测记录', children: `${preview.total_points} 条` },
                { key: 'exceed', label: '超标', children: <Text type={preview.exceed_points > 0 ? 'danger' : undefined}>{preview.exceed_points} 条</Text> },
                { key: 'noise', label: '噪声作业岗位', children: `${preview.noise_post_points} 条` },
              ]}
            />

            <Form form={form} layout="vertical" size="small">
              <Space style={{ width: '100%' }} size="small" wrap>
                <Form.Item
                  name="report_no"
                  label="报告编号"
                  rules={[{ required: true, message: '请填写报告编号' }]}
                  style={{ marginBottom: 0, width: 220 }}
                >
                  <Input placeholder="如 NZXZW-J-2026-141" />
                </Form.Item>
                <Form.Item name="detection_date" label="检测日期" style={{ marginBottom: 0, width: 140 }}>
                  <Input placeholder="YYYY-MM-DD" />
                </Form.Item>
                <Form.Item name="company_name" label="受检企业" style={{ marginBottom: 0, width: 200 }}>
                  <Input />
                </Form.Item>
                <Form.Item name="detection_agency" label="检测机构" style={{ marginBottom: 0, width: 200 }}>
                  <Input />
                </Form.Item>
              </Space>
              <Form.Item name="report_name" label="报告名称" style={{ marginBottom: 0, marginTop: 8 }}>
                <Input />
              </Form.Item>
              <Form.Item name="remark" label="备注" style={{ marginBottom: 0, marginTop: 8 }}>
                <Input.TextArea rows={1} />
              </Form.Item>
            </Form>

            <Collapse
              size="small"
              items={summaryItems}
              defaultActiveKey={['0']}
              destroyInactivePanel={false}
            />
          </>
        )}
      </Space>
    </Modal>
  )
}
