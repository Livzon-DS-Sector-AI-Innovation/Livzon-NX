'use client'

import { useState } from 'react'
import { App, Button, Modal, Space, Typography, Upload } from 'antd'
import PlatformNotice from '@/components/shared/PlatformNotice'

const { Text } = Typography

export interface TargetImportModalProps {
  open: boolean
  onClose: () => void
  title: string
  templateHint: string
  downloadLabel: string
  onDownload: () => Promise<void>
  onImport: (file: File) => Promise<{ ok: boolean; lines: string[] }>
  /** 额外的导入参数区（如考核年度/季度选择） */
  extra?: React.ReactNode
}

export default function TargetImportModal({
  open,
  onClose,
  title,
  templateHint,
  downloadLabel,
  onDownload,
  onImport,
  extra,
}: TargetImportModalProps) {
  const { message } = App.useApp()
  const [file, setFile] = useState<File | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; lines: string[] } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleDownload = async () => {
    setDownloading(true)
    try {
      await onDownload()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '模板下载失败')
    } finally {
      setDownloading(false)
    }
  }

  const handleImport = async () => {
    if (!file) return
    setImporting(true)
    setError(null)
    setResult(null)
    try {
      const res = await onImport(file)
      setResult(res)
      if (res.ok) setFile(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '导入失败')
    } finally {
      setImporting(false)
    }
  }

  const handleClose = () => {
    setFile(null)
    setResult(null)
    setError(null)
    onClose()
  }

  return (
    <Modal
      title={title}
      open={open}
      onCancel={handleClose}
      width={640}
      destroyOnHidden
      footer={[
        <Button key="cancel" onClick={handleClose}>
          关闭
        </Button>,
        <Button
          key="import"
          type="primary"
          disabled={!file}
          loading={importing}
          onClick={handleImport}
        >
          开始导入
        </Button>,
      ]}
    >
      <div className="space-y-3 mt-3">
        <PlatformNotice
          type="info"
          message={templateHint}
          showRulesLink={false}
        />
        <Space wrap>
          <Button onClick={handleDownload} loading={downloading}>
            {downloadLabel}
          </Button>
          <Upload
            maxCount={1}
            accept=".xlsx"
            beforeUpload={() => false}
            onChange={(info) => {
              const raw = (info.file?.originFileObj ?? info.file) as
                | File
                | undefined
              setFile(raw ?? null)
              setResult(null)
              setError(null)
            }}
          >
            <Button>选择填写好的 Excel</Button>
          </Upload>
          {file && <Text style={{ fontSize: 12 }}>{file.name}</Text>}
        </Space>
        {extra}
        {error && (
          <PlatformNotice type="error" message={error} showRulesLink={false} />
        )}
        {result && (
          <PlatformNotice
            type={result.ok ? 'success' : 'warning'}
            message={result.ok ? '导入完成' : '导入完成（部分未成功）'}
            description={result.lines.join('\n')}
            showRulesLink={false}
          />
        )}
      </div>
    </Modal>
  )
}
