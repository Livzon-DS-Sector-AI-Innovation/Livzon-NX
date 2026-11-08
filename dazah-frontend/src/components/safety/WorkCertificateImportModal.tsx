'use client'

import { useMemo, useState } from 'react'
import { App, Button, Modal, Space, Table, Tag, Typography, Upload } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { RcFile } from 'antd/es/upload'
import { ImportOutlined, InboxOutlined } from '@ant-design/icons'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { importCertificates, parseCertificateImport } from '@/actions/safety'
import type {
  CertificateImportPreview,
  CertificateImportResult,
  CertificateImportSheetInfo,
} from '@/types/safety'

const { Text } = Typography

const MAX_FILE_SIZE = 10 * 1024 * 1024

interface Props {
  open: boolean
  onClose: () => void
  onImported: () => void
}

export default function WorkCertificateImportModal({ open, onClose, onImported }: Props) {
  const { message } = App.useApp()
  const [file, setFile] = useState<RcFile | null>(null)
  const [parsing, setParsing] = useState(false)
  const [preview, setPreview] = useState<CertificateImportPreview | null>(null)
  const [selectedSheets, setSelectedSheets] = useState<string[]>([])
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<CertificateImportResult | null>(null)

  const resetState = () => {
    setFile(null)
    setParsing(false)
    setPreview(null)
    setSelectedSheets([])
    setImporting(false)
    setResult(null)
  }

  const importableCount = useMemo(
    () => (preview?.sheets ?? []).filter((sheet) => sheet.row_count > 0).length,
    [preview]
  )

  const handleFile = async (selected: RcFile) => {
    const ext = selected.name.toLowerCase()
    if (!ext.endsWith('.xlsx') && !ext.endsWith('.xls')) {
      message.error('仅支持 .xlsx / .xls 格式的汇总表')
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
      const res = await parseCertificateImport(selected)
      if (res.code === 200 && res.data) {
        const data = res.data as CertificateImportPreview
        setPreview(data)
        setSelectedSheets(
          data.sheets.filter((sheet) => sheet.row_count > 0).map((sheet) => sheet.sheet)
        )
        if (data.sheets.every((sheet) => sheet.row_count === 0)) {
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
      const res = await importCertificates(file, selectedSheets)
      if (res.code === 200 && res.data) {
        setResult(res.data as CertificateImportResult)
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
    if (result && (result.created > 0 || result.updated > 0)) {
      onImported()
    }
    onClose()
    resetState()
  }

  const columns: ColumnsType<CertificateImportSheetInfo> = [
    { title: '子表', dataIndex: 'sheet', key: 'sheet', width: 160, ellipsis: true },
    {
      title: '证件类别',
      key: 'category',
      width: 190,
      render: (_, record) =>
        record.certificate_category_label ? (
          <Tag color="blue">{record.certificate_category_label}</Tag>
        ) : (
          <Text type="secondary">-</Text>
        ),
    },
    { title: '有效行数', dataIndex: 'row_count', key: 'row_count', width: 85 },
  ]

  const sheetTable = preview && (
    <Table
      size="small"
      columns={columns}
      dataSource={preview.sheets}
      rowKey="sheet"
      pagination={false}
      rowSelection={{
        selectedRowKeys: selectedSheets,
        onChange: (keys) => setSelectedSheets(keys as string[]),
        getCheckboxProps: (record) => ({ disabled: record.row_count === 0 }),
      }}
      expandable={{
        rowExpandable: (record) => record.sample.length > 0 || record.errors.length > 0,
        expandedRowRender: (record) => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {record.sample.map((sample, idx) => (
              <Text key={idx} style={{ fontSize: 12 }}>
                {idx + 1}. {sample.person_name}｜{sample.certificate_no || '无证件号'}｜
                {sample.department || '-'}｜有效期至：{sample.expiry_date || '-'}
                {sample.qualification_scope ? `｜${sample.qualification_scope}` : ''}
              </Text>
            ))}
            {record.errors.map((error) => (
              <Text key={`e${error.row}`} type="warning" style={{ fontSize: 12 }}>
                第 {error.row} 行：{error.reason}
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
          导入持证人员汇总表
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
              type={result.created + result.updated > 0 ? 'success' : 'warning'}
              showIcon
              message={
                result.created + result.updated > 0
                  ? `导入完成：新建 ${result.created} 条、更新 ${result.updated} 条`
                  : '没有数据变化'
              }
              description={
                <Space direction="vertical" size={2}>
                  <Text style={{ fontSize: 12 }}>解析有效记录：{result.total_parsed} 条</Text>
                  <Text style={{ fontSize: 12 }}>与台账一致无变化：{result.unchanged} 条</Text>
                  {result.skipped_sheets.map((failure) => (
                    <Text key={failure.sheet} type="warning" style={{ fontSize: 12 }}>
                      子表「{failure.sheet}」跳过：{failure.reason}
                    </Text>
                  ))}
                  {result.row_errors.map((error, idx) => (
                    <Text key={idx} type="warning" style={{ fontSize: 12 }}>
                      {error.sheet} 第 {error.row} 行：{error.reason}
                    </Text>
                  ))}
                </Space>
              }
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              原始文件已存档（{result.archive_path || 'uploads/safety/certificate-import'}），
              同一证件重复导入会更新已有记录而不是重复新建。
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
                {parsing ? '正在解析子表结构…' : '点击或拖入持证人员汇总表 Excel'}
              </p>
              <p className="ant-upload-hint" style={{ fontSize: 12 }}>
                支持多子表工作簿：管理人员 / 电焊 / 高处 / 受限空间 / 电工（高·低）/ 仪表 /
                司炉工 / 水质化验 / 叉车 / 压力容器 / 特种设备管理（A证）/ 起重，单文件 ≤ 10MB
              </p>
            </Upload.Dragger>

            {preview && (
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <Text strong>识别到 {preview.sheets.length} 个子表</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    可导入 {importableCount} 个、共{' '}
                    {preview.sheets.reduce((sum, sheet) => sum + sheet.row_count, 0)} 行有效数据，
                    勾选后导入
                  </Text>
                </Space>
                {sheetTable}
                {preview.skipped_sheets.length > 0 && (
                  <Space direction="vertical" size={2} style={{ marginTop: 8 }}>
                    {preview.skipped_sheets.map((skipped) => (
                      <Text key={skipped.sheet} type="secondary" style={{ fontSize: 12 }}>
                        子表「{skipped.sheet}」未识别：{skipped.reason}
                      </Text>
                    ))}
                  </Space>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </Modal>
  )
}
