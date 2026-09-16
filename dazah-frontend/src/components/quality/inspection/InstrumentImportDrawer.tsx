'use client'

import { useRef, useState } from 'react'
import { Alert, App, Button, Drawer, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  confirmInstrumentImport,
  previewInstrumentImport,
} from '@/lib/api/client/quality'
import type { InstrumentImportPreview } from '@/types/quality'

const { Text } = Typography

interface InstrumentImportDrawerProps {
  open: boolean
  onClose: () => void
  /** 导入成功后刷新列表 */
  onSuccess: () => void
}

/** 仪器台账批量导入：选 xlsx → 预览（列映射/新增更新/告警）→ 确认写飞书。 */
export function InstrumentImportDrawer({
  open,
  onClose,
  onSuccess,
}: InstrumentImportDrawerProps) {
  const { message } = App.useApp()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<InstrumentImportPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [resultText, setResultText] = useState('')
  const [errorMsg, setErrorMsg] = useState('')

  const resetState = () => {
    setFile(null)
    setPreview(null)
    setPreviewing(false)
    setImporting(false)
    setResultText('')
    setErrorMsg('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleClose = () => {
    resetState()
    onClose()
  }

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0]
    if (!selected) return
    if (!selected.name.toLowerCase().endsWith('.xlsx')) {
      setErrorMsg('请上传 .xlsx 文件')
      return
    }
    setErrorMsg('')
    setFile(selected)
    setPreview(null)
    setResultText('')
  }

  const handlePreview = async () => {
    if (!file) {
      setErrorMsg('请先选择文件')
      return
    }
    setPreviewing(true)
    setErrorMsg('')
    try {
      setPreview(await previewInstrumentImport(file))
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '预览失败')
    } finally {
      setPreviewing(false)
    }
  }

  const handleConfirm = async () => {
    if (!file) return
    setImporting(true)
    setErrorMsg('')
    try {
      const result = await confirmInstrumentImport(file)
      if (result.failed > 0) {
        setResultText(
          `导入完成：新增 ${result.created} 条、更新 ${result.updated} 条，失败 ${result.failed} 条` +
            (result.error_details[0]
              ? `（如：第 ${result.error_details[0].row_number} 行 ${result.error_details[0].message}）`
              : ''),
        )
      } else {
        setResultText(
          `导入成功：新增 ${result.created} 条、更新 ${result.updated} 条`,
        )
        message.success('导入成功，已同步飞书')
      }
      setPreview(null)
      onSuccess()
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '导入失败')
    } finally {
      setImporting(false)
    }
  }

  const rowColumns: ColumnsType<InstrumentImportPreview['rows'][number]> = [
    { title: '行号', dataIndex: 'row_number', key: 'row_number', width: 64 },
    {
      title: '方式',
      dataIndex: 'mode',
      key: 'mode',
      width: 72,
      render: (mode: string) =>
        mode === 'update' ? <Tag color="blue">更新</Tag> : <Tag color="green">新增</Tag>,
    },
    {
      title: '设备编号',
      key: 'code',
      render: (_, record) => record.values['设备编号'] ?? '-',
    },
    {
      title: '设备名称',
      key: 'name',
      render: (_, record) => record.values['设备名称'] ?? '-',
    },
    {
      title: '说明',
      key: 'notes',
      render: (_, record) => {
        if (record.error) return <Text type="danger">{record.error}</Text>
        if (record.warnings.length > 0) {
          return <Text type="warning">{record.warnings.join('；')}</Text>
        }
        return '—'
      },
    },
  ]

  const importable = (preview?.create_count ?? 0) + (preview?.update_count ?? 0)

  return (
    <Drawer
      open={open}
      title="批量导入仪器台账"
      size={720}
      onClose={handleClose}
      destroyOnHidden
      footer={
        <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
          <Button onClick={handleClose} disabled={importing}>
            关闭
          </Button>
          <Button onClick={handlePreview} disabled={!file || previewing || importing}>
            {previewing ? '解析中…' : '预览数据'}
          </Button>
          {preview && importable > 0 && (
            <Button type="primary" onClick={handleConfirm} loading={importing}>
              确认导入（新增 {preview.create_count} / 更新 {preview.update_count}）
            </Button>
          )}
        </Space>
      }
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          title="按「设备编号」自动判新增/更新"
          description="表头自动识别（设备编号/名称/品牌/规格型号/用途/安装地点/负责人/入厂日期）；负责人按姓名匹配人事-飞书联系人；日期支持 2026-01-31、2026/1/31、20260131。"
        />
        <div className="rounded-lg border-2 border-dashed border-[var(--color-border)] p-5 text-center">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx"
            onChange={handleFileChange}
            className="hidden"
            id="instrument-import-file-input"
          />
          <label htmlFor="instrument-import-file-input" className="cursor-pointer">
            <div className="text-3xl mb-2">📄</div>
            <div className="text-sm">{file ? file.name : '点击选择 Excel 文件（.xlsx）'}</div>
          </label>
        </div>

        {errorMsg && <Alert type="error" showIcon title={errorMsg} />}
        {resultText && <Alert type="success" showIcon title={resultText} />}

        {preview && (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Space wrap>
              <Tag color="green">新增 {preview.create_count}</Tag>
              <Tag color="blue">更新 {preview.update_count}</Tag>
              {preview.error_count > 0 && <Tag color="red">错误 {preview.error_count}</Tag>}
              {preview.skipped_empty > 0 && (
                <Tag>空行跳过 {preview.skipped_empty}</Tag>
              )}
            </Space>
            <div>
              <Text strong>识别的列映射：</Text>
              <div style={{ marginTop: 4 }}>
                {Object.entries(preview.column_map).map(([field, header]) => (
                  <Tag key={field}>
                    {header} → {field}
                  </Tag>
                ))}
              </div>
            </div>
            {preview.unmatched_columns.length > 0 && (
              <Text type="secondary">
                未识别列（已忽略）：{preview.unmatched_columns.join('、')}
              </Text>
            )}
            {preview.person_unresolved.length > 0 && (
              <Alert
                type="warning"
                showIcon
                title={`未匹配到在职人员：${preview.person_unresolved.join('、')}（对应单元格将跳过）`}
              />
            )}
            <Table
              rowKey="row_number"
              size="small"
              columns={rowColumns}
              dataSource={preview.rows}
              pagination={preview.rows.length > 10 ? { pageSize: 10 } : false}
              scroll={{ x: 'max-content' }}
            />
          </Space>
        )}
      </Space>
    </Drawer>
  )
}