'use client'

import { useCallback, useState } from 'react'

import { InboxOutlined, FileTextOutlined } from '@ant-design/icons'
import { App, Button, Descriptions, Form, Input, Modal, Space, Spin, Typography, Upload } from 'antd'

import {
  importNoticeAction,
  parseNoticeAction,
} from '@/actions/administration'
import type { NoticeParsePreview } from '@/types/administration'

const { Text } = Typography

const ACCEPT =
  '.pdf,.doc,.docx,.png,.jpg,.jpeg'
const MAX_FILE_SIZE = 30 * 1024 * 1024
const ALLOWED_EXTENSIONS = ['.pdf', '.doc', '.docx', '.png', '.jpg', '.jpeg']

export interface NoticeImportModalProps {
  open: boolean
  onClose: () => void
  onImported: () => void
}

/**
 * 上传公告 → AI 识别元数据预填 → 人工确认导入。
 * 公告内容不回显（仅落库后经 operate 专用端点查看）。
 */
export default function NoticeImportModal({
  open,
  onClose,
  onImported,
}: NoticeImportModalProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<{
    notice_no: string
    title: string
    publisher: string
    published_at: string
    category: string
    remark: string
  }>()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<NoticeParsePreview | null>(null)
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
      const lowerName = selected.name.toLowerCase()
      if (!ALLOWED_EXTENSIONS.some((ext) => lowerName.endsWith(ext))) {
        message.error('仅支持 PDF/Word/图片格式的公告文件')
        return
      }
      if (selected.size > MAX_FILE_SIZE) {
        message.error('公告文件不能超过 30MB')
        return
      }
      setFile(selected)
      setPreview(null)
      setParsing(true)
      const res = await parseNoticeAction(selected)
      setParsing(false)
      if (res.code !== 200 || !res.data) {
        message.error(res.message || '识别失败，请重试或手动填写后导入')
        return
      }
      setPreview(res.data)
      const suggestion = res.data.suggestion
      form.setFieldsValue({
        notice_no: suggestion.notice_no ?? '',
        title: suggestion.title ?? '',
        publisher: suggestion.publisher ?? '',
        published_at: suggestion.published_at ?? '',
        category: suggestion.category ?? '',
        remark: suggestion.remark ?? '',
      })
    },
    [form, message],
  )

  const handleImport = useCallback(async () => {
    if (!file) return
    const values = await form.validateFields()
    setImporting(true)
    const res = await importNoticeAction(file, {
      notice_no: values.notice_no,
      title: values.title,
      publisher: values.publisher,
      published_at: values.published_at,
      category: values.category,
      remark: values.remark,
    })
    setImporting(false)
    if (res.code !== 200 || !res.data) {
      message.error(res.message || '导入失败，请重试')
      return
    }
    message.success('公告已录入台账（内容已识别归档，可查看原文存档）')
    reset()
    onImported()
  }, [file, form, message, onImported, reset])

  return (
    <Modal
      open={open}
      title="上传公告（AI 识别元数据）"
      width={720}
      onCancel={handleClose}
      destroyOnHidden
      footer={
        file ? (
          [
            <Button key="back" onClick={handleClose} disabled={importing}>
              取消
            </Button>,
            <Button key="import" type="primary" loading={importing} onClick={handleImport}>
              确认导入
            </Button>,
          ]
        ) : null
      }
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Upload.Dragger
          accept={ACCEPT}
          multiple={false}
          showUploadList={!!file && !preview}
          fileList={file && !preview ? [{ uid: '-1', name: file.name, status: 'done' }] : []}
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
            <Spin indicator={<FileTextOutlined style={{ fontSize: 32 }} spin />} />
          ) : (
            <InboxOutlined style={{ fontSize: 32 }} />
          )}
          <div style={{ marginTop: 8 }}>
            {parsing ? '正在识别公告内容…' : '点击或拖拽公告文件到此处'}
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            支持 PDF/Word/图片，≤30MB；AI 自动识别编号、标题、发布单位等
          </Text>
        </Upload.Dragger>

        {preview && (
          <Form form={form} layout="vertical" size="small">
            <Space style={{ width: '100%' }} size="small" wrap>
              <Form.Item
                name="notice_no"
                label="公告编号"
                style={{ marginBottom: 0, width: 200 }}
              >
                <Input placeholder="如 2026-第03号" />
              </Form.Item>
              <Form.Item
                name="published_at"
                label="发布日期"
                style={{ marginBottom: 0, width: 140 }}
              >
                <Input placeholder="YYYY-MM-DD" />
              </Form.Item>
              <Form.Item
                name="category"
                label="类别"
                style={{ marginBottom: 0, width: 140 }}
              >
                <Input placeholder="如 行政通知" />
              </Form.Item>
              <Form.Item
                name="publisher"
                label="发布单位"
                style={{ marginBottom: 0, width: 180 }}
              >
                <Input />
              </Form.Item>
            </Space>
            <Form.Item
              name="title"
              label="公告标题"
              required
              rules={[{ required: true, message: '请填写公告标题' }]}
              style={{ marginBottom: 0, marginTop: 8 }}
            >
              <Input />
            </Form.Item>
            <Form.Item name="remark" label="备注" style={{ marginBottom: 0, marginTop: 8 }}>
              <Input.TextArea rows={2} maxLength={2000} />
            </Form.Item>
            <Descriptions
              size="small"
              column={1}
              className="mt-2"
              items={[
                {
                  key: 'file',
                  label: '识别文件',
                  children: preview.file_name,
                },
              ]}
            />
          </Form>
        )}
      </Space>
    </Modal>
  )
}
