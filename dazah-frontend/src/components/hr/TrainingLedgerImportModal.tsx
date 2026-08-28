'use client'

import { useState } from 'react'
import { App, Button, Checkbox, Modal, Select, Spin, Table, Tag, Upload } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import type { components } from '@/types/generated/schema'
import { previewTrainingImport, confirmTrainingImport } from '@/actions/hr'

type ImportSheetPreview = components['schemas']['ImportSheetPreview']
type FieldCatalogItem = { key: string; label: string }

interface Props {
  open: boolean
  department: string
  onClose: () => void
  onSuccess: () => void
}

const SOURCE_TAG: Record<string, { color: string; label: string }> = {
  memory: { color: 'purple', label: '记忆命中' },
  rule: { color: 'green', label: '规则识别' },
  ai: { color: 'blue', label: 'AI识别' },
  none: { color: 'default', label: '未识别' },
}

export default function TrainingLedgerImportModal({ open, department, onClose, onSuccess }: Props) {
  const { message } = App.useApp()
  const [file, setFile] = useState<File | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [sheets, setSheets] = useState<ImportSheetPreview[]>([])
  const [fieldCatalog, setFieldCatalog] = useState<FieldCatalogItem[]>([])
  // sheetName -> { 列索引 -> 字段名（''表示不映射） }
  const [editableMapping, setEditableMapping] = useState<Record<string, Record<string, string>>>({})
  const [selectedSheets, setSelectedSheets] = useState<Record<string, boolean>>({})

  const handleFile = async (f: File) => {
    setFile(f)
    setAnalyzing(true)
    setSheets([])
    try {
      const res = await previewTrainingImport(f, department)
      const data = res.data || { sheets: [], field_catalog: [] }
      setSheets(data.sheets || [])
      setFieldCatalog((data.field_catalog || []) as FieldCatalogItem[])

      const mappingInit: Record<string, Record<string, string>> = {}
      const selectedInit: Record<string, boolean> = {}
      for (const s of data.sheets || []) {
        mappingInit[s.name] = { ...(s.mapping || {}) }
        // 默认勾选：识别成功且有数据；AI 判断建议跳过的不勾选
        const skip = s.ai_judgment && s.ai_judgment.includes('跳过')
        selectedInit[s.name] =
          !skip && s.source !== 'none' && Object.keys(s.mapping || {}).length > 0 && s.data_row_count > 0
      }
      setEditableMapping(mappingInit)
      setSelectedSheets(selectedInit)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '文件分析失败')
    } finally {
      setAnalyzing(false)
    }
  }

  const handleMappingChange = (sheetName: string, colIdx: string, field: string) => {
    setEditableMapping((prev) => ({
      ...prev,
      [sheetName]: { ...prev[sheetName], [colIdx]: field },
    }))
  }

  const handleConfirm = async () => {
    if (!file) return
    const payload = sheets
      .filter((s) => selectedSheets[s.name])
      .map((s) => {
        const mapping = Object.fromEntries(
          Object.entries(editableMapping[s.name] || {}).filter(([, v]) => v)
        )
        return { name: s.name, header_row: s.header_row, mapping }
      })
      .filter((s) => Object.keys(s.mapping).length > 0)

    if (payload.length === 0) {
      message.warning('请至少勾选一个工作表并配置列映射')
      return
    }

    setImporting(true)
    try {
      const res = await confirmTrainingImport(file, department, payload)
      message.success(res.message || '导入成功')
      onSuccess()
      handleReset()
      onClose()
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  const handleReset = () => {
    setFile(null)
    setSheets([])
    setFieldCatalog([])
    setEditableMapping({})
    setSelectedSheets({})
  }

  const fieldOptions = [
    { value: '', label: '— 不映射 —' },
    ...fieldCatalog.map((f) => ({ value: f.key, label: f.label })),
  ]

  return (
    <Modal
      title={`导入培训统计（${department}）`}
      open={open}
      onCancel={() => {
        handleReset()
        onClose()
      }}
      width={960}
      footer={
        sheets.length > 0
          ? [
              <Button key="reupload" onClick={handleReset}>
                重新选择文件
              </Button>,
              <Button key="confirm" type="primary" loading={importing} onClick={handleConfirm}>
                确认导入
              </Button>,
            ]
          : null
      }
    >
      {sheets.length === 0 ? (
        <div className="py-8">
          <Upload.Dragger
            accept=".xlsx,.xls"
            showUploadList={false}
            beforeUpload={(f) => {
              handleFile(f)
              return false
            }}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽 Excel 文件到此处</p>
            <p className="ant-upload-hint">
              系统将自动识别表格式（支持各部门不同表头），识别后需人工确认再导入
            </p>
          </Upload.Dragger>
          {analyzing && (
            <div className="flex items-center justify-center gap-2 pt-6 text-[var(--color-steel)]">
              <Spin /> 正在分析文件（规范格式秒级识别，新格式需 AI 分析约几秒）…
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
          {sheets.map((s) => {
            const tag = SOURCE_TAG[s.source] || SOURCE_TAG.none
            const mapping = editableMapping[s.name] || {}
            const headers = s.headers || []
            const sampleRows = s.sample_rows || []
            const headerCols = Object.keys(mapping).length > 0
              ? Object.keys(mapping)
              : headers.map((_: string, i: number) => String(i)).slice(0, 20)
            return (
              <div key={s.name} className="border border-[var(--color-hairline)] rounded-lg p-4">
                <div className="flex items-center gap-3 mb-3">
                  <Checkbox
                    checked={!!selectedSheets[s.name]}
                    disabled={s.source === 'none'}
                    onChange={(e) =>
                      setSelectedSheets((prev) => ({ ...prev, [s.name]: e.target.checked }))
                    }
                  >
                    <span className="font-medium">{s.name}</span>
                  </Checkbox>
                  <Tag color={tag.color}>{tag.label}</Tag>
                  {s.source !== 'none' && (
                    <span className="text-[12px] text-[var(--color-steel)]">
                      可导入 {s.data_row_count} 行
                    </span>
                  )}
                  {s.ai_judgment && (
                    <Tag color={s.ai_judgment.includes('跳过') ? 'red' : 'orange'}>
                      {s.ai_judgment}
                    </Tag>
                  )}
                </div>

                {s.source === 'none' ? (
                  <p className="text-[12px] text-[var(--color-steel)]">
                    无法识别该工作表结构（可能为非培训数据）。如表头为：
                    {headers.filter(Boolean).slice(0, 10).join('、') || '（空）'}
                  </p>
                ) : (
                  <>
                    <div className="grid grid-cols-3 gap-2 mb-3">
                      {headerCols.map((colIdx: string) => {
                        const headerText = headers[Number(colIdx)] || `第${Number(colIdx) + 1}列`
                        return (
                          <div key={colIdx} className="flex items-center gap-1">
                            <span
                              className="text-[12px] text-[var(--color-steel)] truncate flex-1"
                              title={headerText}
                            >
                              {headerText}
                            </span>
                            <Select
                              size="small"
                              style={{ width: 150 }}
                              value={mapping[colIdx] ?? ''}
                              options={fieldOptions}
                              onChange={(v) => handleMappingChange(s.name, colIdx, v)}
                            />
                          </div>
                        )
                      })}
                    </div>
                    {sampleRows.length > 0 && (
                      <Table
                        size="small"
                        rowKey="key"
                        dataSource={sampleRows.map((r: string[], ri: number) => ({
                          key: String(ri),
                          cells: r,
                        }))}
                        pagination={false}
                        scroll={{ x: 'max-content' }}
                        columns={headerCols.map((colIdx: string, i: number) => ({
                          title: mapping[colIdx]
                            ? fieldCatalog.find((f) => f.key === mapping[colIdx])?.label || mapping[colIdx]
                            : headers[Number(colIdx)] || `列${Number(colIdx) + 1}`,
                          key: colIdx,
                          width: 140,
                          ellipsis: true,
                          render: (_: unknown, record: { key: string; cells: string[] }) => (
                            <span className="text-[12px]">{record.cells[i] ?? ''}</span>
                          ),
                        }))}
                      />
                    )}
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}
