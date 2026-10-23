'use client'

import { useMemo, useState } from 'react'
import {
  App,
  Button,
  Input,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { RcFile } from 'antd/es/upload'
import { ImportOutlined, InboxOutlined, ReloadOutlined } from '@ant-design/icons'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { importHazardLedger, parseHazardLedgerImport } from '@/actions/safety'
import type {
  HazardImportPreview,
  HazardImportResult,
  HazardImportSheetInfo,
} from '@/types/safety'

const { Text } = Typography

const FORMAT_TAG_COLORS: Record<string, string> = {
  activity: 'blue',
  facility: 'geekblue',
  key_risk: 'purple',
  legacy: 'gold',
}

const MAX_FILE_SIZE = 10 * 1024 * 1024

interface Props {
  open: boolean
  onClose: () => void
  onImported: () => void
}

export default function HazardLedgerImportModal({ open, onClose, onImported }: Props) {
  const { message } = App.useApp()
  const [file, setFile] = useState<RcFile | null>(null)
  const [parsing, setParsing] = useState(false)
  const [preview, setPreview] = useState<HazardImportPreview | null>(null)
  const [department, setDepartment] = useState('')
  const [selectedSheets, setSelectedSheets] = useState<string[]>([])
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<HazardImportResult | null>(null)

  const resetState = () => {
    setFile(null)
    setParsing(false)
    setPreview(null)
    setDepartment('')
    setSelectedSheets([])
    setImporting(false)
    setResult(null)
  }

  const importableCount = useMemo(
    () => (preview?.sheets ?? []).filter((sheet) => !sheet.skipped && sheet.row_count > 0).length,
    [preview]
  )

  const handleFile = async (selected: RcFile) => {
    const ext = selected.name.toLowerCase()
    if (!ext.endsWith('.xlsx') && !ext.endsWith('.xls')) {
      message.error('仅支持 .xlsx / .xls 格式的车间表格')
      return
    }
    if (selected.size > MAX_FILE_SIZE) {
      message.error('文件大小不能超过 10MB')
      return
    }
    setFile(selected)
    setResult(null)
    setPreview(null)
    setParsing(true)
    try {
      const res = await parseHazardLedgerImport(selected)
      if (res.code === 200 && res.data) {
        const data = res.data as HazardImportPreview
        setPreview(data)
        setDepartment(data.department_guess || '')
        setSelectedSheets(
          data.sheets.filter((s) => !s.skipped && s.row_count > 0).map((s) => s.name)
        )
        if (data.total_valid_rows === 0) {
          message.warning('未从该文件解析出有效数据行，请检查表格格式')
        }
      } else {
        message.error(res.message || '解析失败')
        setFile(null)
      }
    } catch {
      message.error('解析失败，请稍后重试')
      setFile(null)
    } finally {
      setParsing(false)
    }
  }

  const handleImport = async () => {
    if (!file || selectedSheets.length === 0) return
    setImporting(true)
    try {
      const res = await importHazardLedger(file, department.trim(), selectedSheets)
      if (res.code === 200 && res.data) {
        setResult(res.data as HazardImportResult)
      } else {
        message.error(res.message || '导入失败')
      }
    } catch {
      message.error('导入失败，请稍后重试')
    } finally {
      setImporting(false)
    }
  }

  const handleClose = () => {
    if (result && result.imported > 0) {
      onImported()
    }
    onClose()
    resetState()
  }

  const columns: ColumnsType<HazardImportSheetInfo> = [
    { title: '子表', dataIndex: 'name', key: 'name', width: 130, ellipsis: true },
    {
      title: '识别格式',
      dataIndex: 'format_label',
      key: 'format_label',
      width: 150,
      render: (label: string | null | undefined, record) =>
        label ? (
          <Tag color={FORMAT_TAG_COLORS[record.format || ''] || 'default'}>{label}</Tag>
        ) : (
          <Text type="secondary">-</Text>
        ),
    },
    { title: '有效行数', dataIndex: 'row_count', key: 'row_count', width: 85 },
    {
      title: '状态',
      key: 'status',
      render: (_, record) =>
        record.skipped ? (
          <Text type="warning">{record.skip_reason || '跳过'}</Text>
        ) : (
          <Text type="success">可导入</Text>
        ),
    },
  ]

  const sheetTable = preview && (
    <Table
      size="small"
      columns={columns}
      dataSource={preview.sheets}
      rowKey="name"
      pagination={false}
      rowSelection={{
        selectedRowKeys: selectedSheets,
        onChange: (keys) => setSelectedSheets(keys as string[]),
        getCheckboxProps: (record) => ({ disabled: record.skipped || record.row_count === 0 }),
      }}
      expandable={{
        rowExpandable: (record) => (record.sample_rows?.length ?? 0) > 0,
        expandedRowRender: (record) => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {record.sample_rows.map((sample, idx) => (
              <Text key={idx} style={{ fontSize: 12 }}>
                {idx + 1}. {sample.name || '-'}｜{sample.step || '-'}｜
                危险源：{(sample.hazard_desc || '-').slice(0, 40)}｜
                L={sample.l ?? '-'} E={sample.e ?? '-'} C={sample.c ?? '-'} D={sample.d ?? '-'}｜
                {sample.level || '-'}
              </Text>
            ))}
            <Text type="secondary" style={{ fontSize: 12 }}>
              展开行仅为前 3 行样例，导入时按勾选子表全量写入。
            </Text>
          </div>
        ),
      }}
    />
  )

  return (
    <Modal
      title={
        <span>
          <ImportOutlined style={{ marginRight: 8, color: '#5645D4' }} />
          导入车间危险源辨识表格
        </span>
      }
      open={open}
      onCancel={handleClose}
      width={760}
      footer={
        result ? (
          <Button type="primary" onClick={handleClose}>
            完成
          </Button>
        ) : (
          <Space>
            <Button onClick={handleClose}>取消</Button>
            <Button
              type="primary"
              icon={<ImportOutlined />}
              loading={importing}
              disabled={!file || selectedSheets.length === 0 || parsing}
              onClick={handleImport}
            >
              导入选中子表（{selectedSheets.length} 个）
            </Button>
          </Space>
        )
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {result ? (
          <>
            <PlatformNotice
              type={result.imported > 0 ? 'success' : 'warning'}
              showIcon
              message={
                result.imported > 0
                  ? `成功导入 ${result.imported} 条危险源辨识记录`
                  : '没有新记录被导入'
              }
              description={
                <Space direction="vertical" size={2}>
                  <Text style={{ fontSize: 12 }}>已存在自动跳过：{result.skipped_existing} 条</Text>
                  <Text style={{ fontSize: 12 }}>文件内重复去重：{result.duplicate_in_file} 条</Text>
                  {result.failed_sheets.map((failure) => (
                    <Text key={failure.sheet} type="warning" style={{ fontSize: 12 }}>
                      子表「{failure.sheet}」导入失败：{failure.reason}
                    </Text>
                  ))}
                </Space>
              }
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              原始文件已存档（{result.archive_path || 'uploads/safety/hazard-import'}），可在记录详情的附件中追溯。
            </Text>
          </>
        ) : (
          <>
            <Upload.Dragger
              accept=".xlsx,.xls"
              multiple={false}
              showUploadList={!!file && { showRemoveIcon: false }}
              fileList={file ? [{ uid: '-1', name: file.name, status: 'done' }] : []}
              beforeUpload={(selected) => {
                queueMicrotask(() => handleFile(selected))
                return false
              }}
              disabled={parsing || importing}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">
                {parsing ? '正在解析子表结构…' : '点击或拖入车间 Excel 文件'}
              </p>
              <p className="ant-upload-hint" style={{ fontSize: 12 }}>
                支持多子表工作簿：作业活动 / 设备设施分级管控清单、重点风险管控措施清单、
                危险源辨识评价表（.xls），单文件 ≤ 10MB
              </p>
            </Upload.Dragger>

            {preview && (
              <>
                <div>
                  <Text strong style={{ display: 'block', marginBottom: 6 }}>
                    部门 / 车间（写入每条记录，可在台账中按部门筛选）
                  </Text>
                  <Space.Compact style={{ width: '100%' }}>
                    <Input
                      placeholder={
                        preview.department_guess
                          ? `默认取文件名推断：${preview.department_guess}`
                          : '文件名未识别出车间，请手动填写'
                      }
                      value={department}
                      onChange={(e) => setDepartment(e.target.value)}
                    />
                    <Button
                      icon={<ReloadOutlined />}
                      disabled={!file || parsing}
                      onClick={() => file && handleFile(file)}
                    >
                      重新解析
                    </Button>
                  </Space.Compact>
                </div>

                <div>
                  <Space style={{ marginBottom: 8 }}>
                    <Text strong>识别到 {preview.sheets.length} 个子表</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      可导入 {importableCount} 个、共 {preview.total_valid_rows} 行有效数据，勾选后导入
                    </Text>
                  </Space>
                  {sheetTable}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </Modal>
  )
}
