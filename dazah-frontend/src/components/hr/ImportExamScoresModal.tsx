'use client'

import { useState } from 'react'
import { App, Button, InputNumber, Modal, Table, Upload } from 'antd'
import { InboxOutlined, UploadOutlined } from '@ant-design/icons'
import { importExamScores, confirmExamScores } from '@/actions/hr'

interface ScoreItem {
  name: string
  score: string
}

interface Props {
  open: boolean
  recordId: string
  onClose: () => void
  onSuccess: () => void
}

export default function ImportExamScoresModal({ open, recordId, onClose, onSuccess }: Props) {
  const { message } = App.useApp()
  const [file, setFile] = useState<File | null>(null)
  const [parsing, setParsing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [scores, setScores] = useState<ScoreItem[]>([])

  const handleParse = async (f: File) => {
    setFile(f)
    setParsing(true)
    setScores([])
    try {
      const res = await importExamScores(f, recordId)
      setScores(res.data || [])
      message.success(res.message || `解析出 ${res.data?.length || 0} 条成绩`)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '解析文件失败')
    } finally {
      setParsing(false)
    }
  }

  const handleConfirm = async () => {
    if (!scores.length) {
      message.warning('没有可导入的成绩数据')
      return
    }
    setConfirming(true)
    try {
      const res = await confirmExamScores(recordId, scores)
      message.success(res.message || '成绩导入成功')
      onSuccess()
      handleClose()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '导入成绩失败')
    } finally {
      setConfirming(false)
    }
  }

  const handleClose = () => {
    setFile(null)
    setScores([])
    setParsing(false)
    setConfirming(false)
    onClose()
  }

  // 表格列定义
  const columns = [
    {
      title: '序号',
      width: 60,
      render: (_: unknown, __: unknown, index: number) => index + 1,
    },
    {
      title: '姓名',
      dataIndex: 'name',
      width: 120,
    },
    {
      title: '成绩',
      dataIndex: 'score',
      width: 120,
      render: (val: string, _: unknown, index: number) => (
        <InputNumber<number>
          size="small"
          value={Number(val) || 0}
          min={0}
          max={100}
          onChange={(v) => {
            const next = [...scores]
            next[index] = { ...next[index], score: String(v ?? '') }
            setScores(next)
          }}
        />
      ),
    },
  ]

  return (
    <Modal
      title="导入笔试成绩"
      open={open}
      onCancel={handleClose}
      width={520}
      footer={[
        <Button key="cancel" onClick={handleClose}>
          取消
        </Button>,
        <Button
          key="confirm"
          type="primary"
          loading={confirming}
          disabled={!scores.length}
          onClick={handleConfirm}
        >
          确认导入{scores.length ? `（${scores.length} 条）` : ''}
        </Button>,
      ]}
    >
      {/* 上传区域 */}
      <Upload.Dragger
        accept=".docx,.xlsx"
        showUploadList={false}
        beforeUpload={(f) => {
          handleParse(f)
          return false
        }}
        disabled={parsing}
      >
        <p className="ant-upload-drag-icon">
          {parsing ? <UploadOutlined spin /> : <InboxOutlined />}
        </p>
        <p className="ant-upload-text">
          {parsing ? '正在解析...' : '点击或拖拽文件到此处'}
        </p>
        <p className="ant-upload-hint">
          支持 .docx、.xlsx 格式，自动识别姓名和成绩
        </p>
      </Upload.Dragger>

      {/* 已选文件 */}
      {file && !parsing && (
        <div className="mt-2 text-sm text-gray-500">
          已选文件：{file.name}
        </div>
      )}

      {/* 解析结果表格 */}
      {scores.length > 0 && (
        <Table
          className="mt-3"
          dataSource={scores}
          columns={columns}
          rowKey={(_, i) => String(i)}
          size="small"
          pagination={scores.length > 10 ? { pageSize: 10, size: 'small' } : false}
          scroll={{ y: 320 }}
        />
      )}
    </Modal>
  )
}
