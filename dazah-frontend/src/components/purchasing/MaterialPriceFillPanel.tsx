'use client'

import { useState } from 'react'
import { App, Button, Select, Space, Table, Tag, Upload } from 'antd'
import type { TableProps, UploadProps } from 'antd'
import {
  DownloadOutlined,
  InboxOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import {
  generateMaterialPriceFill,
  previewMaterialPriceFill,
} from '@/actions/purchasing'
import type {
  MaterialPriceFillMapping,
  MaterialPriceFillPreview,
  MaterialPriceFillRow,
} from '@/types/purchasing'

const { Dragger } = Upload
const ACCEPTED = '.xlsx,.xlsm'
const MAX_SIZE_MB = 20

const sourceLabels: Record<string, { label: string; color: string }> = {
  live: { label: '实时入库', color: 'success' },
  history: { label: '历史价', color: 'processing' },
  name_fuzzy: { label: '名称匹配', color: 'warning' },
  unmatched: { label: '未匹配', color: 'default' },
}

function downloadBase64(base64: string, filename: string) {
  const binary = window.atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  const blob = new Blob([bytes], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function MaterialPriceFillPanel() {
  const { message } = App.useApp()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<MaterialPriceFillPreview | null>(null)
  const [mapping, setMapping] = useState<MaterialPriceFillMapping | null>(null)
  const [parsing, setParsing] = useState(false)
  const [generating, setGenerating] = useState(false)

  const runPreview = async (
    nextFile: File,
    overrideMapping?: MaterialPriceFillMapping | null,
  ) => {
    setParsing(true)
    try {
      const formData = new FormData()
      formData.append('file', nextFile)
      const effective = overrideMapping ?? mapping
      if (effective) formData.append('mapping', JSON.stringify(effective))
      const response = await previewMaterialPriceFill(formData)
      if (response.code !== 200 || !response.data) {
        message.error(response.message || '表格解析失败')
        setPreview(null)
        return
      }
      setPreview(response.data)
      setMapping(response.data.mapping)
    } catch {
      message.error('表格解析失败，请稍后重试')
    } finally {
      setParsing(false)
    }
  }

  const beforeUpload: UploadProps['beforeUpload'] = (nextFile) => {
    const name = nextFile.name.toLowerCase()
    if (!name.endsWith('.xlsx') && !name.endsWith('.xlsm')) {
      message.error('.xls 请先另存为 xlsx 再上传')
      return Upload.LIST_IGNORE
    }
    if (nextFile.size > MAX_SIZE_MB * 1024 * 1024) {
      message.error(`表格不能超过 ${MAX_SIZE_MB}MB`)
      return Upload.LIST_IGNORE
    }
    setFile(nextFile)
    setPreview(null)
    setMapping(null)
    void runPreview(nextFile, null)
    return Upload.LIST_IGNORE
  }

  const columnOptions = (preview?.headers ?? []).map((title, index) => ({
    label: title ? `${index + 1}. ${title}` : `${index + 1} 列`,
    value: index + 1,
  }))

  const updateMapping = (patch: Partial<MaterialPriceFillMapping>) => {
    if (!mapping || !file) return
    const next = { ...mapping, ...patch }
    setMapping(next)
    void runPreview(file, next)
  }

  const handleDownload = async () => {
    if (!file || !mapping) return
    setGenerating(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('mapping', JSON.stringify(mapping))
      formData.append('only_blank', 'true')
      const result = await generateMaterialPriceFill(formData)
      if (!result.ok) {
        message.error(result.message)
        return
      }
      downloadBase64(result.base64, result.filename)
      message.success(`已填入 ${result.filledCount} 个单元格`)
    } catch {
      message.error('表格补价失败，请稍后重试')
    } finally {
      setGenerating(false)
    }
  }

  const columns: TableProps<MaterialPriceFillRow>['columns'] = [
    { title: '行号', dataIndex: 'row_number', key: 'row_number', width: 70 },
    {
      title: '原物料编码',
      dataIndex: 'material_code',
      key: 'material_code',
      width: 130,
    },
    {
      title: '原物料名称',
      dataIndex: 'material_name',
      key: 'material_name',
      ellipsis: true,
    },
    {
      title: '匹配编码',
      dataIndex: 'matched_code',
      key: 'matched_code',
      width: 120,
    },
    {
      title: '单价',
      dataIndex: 'unit_price',
      key: 'unit_price',
      width: 100,
      align: 'right',
      render: (value: string | null) => (value ? Number(value).toFixed(2) : '-'),
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 110,
      render: (value: string) => {
        const meta = sourceLabels[value] ?? { label: value, color: 'default' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
  ]

  return (
    <div className="space-y-4">
      <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4">
        <Dragger
          accept={ACCEPTED}
          beforeUpload={beforeUpload}
          showUploadList={false}
          disabled={parsing || generating}
          maxCount={1}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">
            {file ? `${file.name}（点击可重新选择）` : '点击或拖拽表格到此处'}
          </p>
        </Dragger>
      </section>

      {preview && (
        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div className="grid flex-1 gap-3 sm:grid-cols-3">
              <label className="text-[13px]">
                <span className="mb-1 block text-[var(--color-steel)]">
                  物料编码列
                </span>
                <Select
                  className="w-full"
                  allowClear
                  value={mapping?.code_column ?? undefined}
                  options={columnOptions}
                  onChange={(value) =>
                    updateMapping({ code_column: value ?? null })
                  }
                />
              </label>
              <label className="text-[13px]">
                <span className="mb-1 block text-[var(--color-steel)]">
                  物料名称列
                </span>
                <Select
                  className="w-full"
                  allowClear
                  value={mapping?.name_column ?? undefined}
                  options={columnOptions}
                  onChange={(value) =>
                    updateMapping({ name_column: value ?? null })
                  }
                />
              </label>
              <label className="text-[13px]">
                <span className="mb-1 block text-[var(--color-steel)]">
                  单价列
                </span>
                <Select
                  className="w-full"
                  allowClear
                  value={mapping?.price_column ?? undefined}
                  options={columnOptions}
                  onChange={(value) =>
                    updateMapping({ price_column: value ?? null })
                  }
                />
              </label>
            </div>
            <Space>
              <Button
                icon={<ReloadOutlined />}
                loading={parsing}
                onClick={() => file && void runPreview(file, mapping)}
              >
                重新匹配
              </Button>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                loading={generating}
                disabled={!mapping?.price_column}
                onClick={handleDownload}
              >
                生成并下载
              </Button>
            </Space>
          </div>

          <div className="grid gap-3 border-t border-[var(--color-hairline-soft)] pt-3 sm:grid-cols-4">
            <div>
              <p className="text-[12px] text-[var(--color-stone)]">工作表</p>
              <p className="text-[15px] font-medium">
                {preview.mapping.sheet_name || '-'}
              </p>
            </div>
            <div>
              <p className="text-[12px] text-[var(--color-stone)]">数据行</p>
              <p className="text-[15px] font-medium">{preview.total_rows}</p>
            </div>
            <div>
              <p className="text-[12px] text-[var(--color-stone)]">已匹配</p>
              <p className="text-[15px] font-medium text-[var(--color-success)]">
                {preview.matched_rows}
              </p>
            </div>
            <div>
              <p className="text-[12px] text-[var(--color-stone)]">未匹配</p>
              <p className="text-[15px] font-medium">
                {preview.unmatched_rows}
              </p>
            </div>
          </div>

          <Table<MaterialPriceFillRow>
            className="mt-4"
            columns={columns}
            dataSource={preview.rows ?? []}
            rowKey="row_number"
            size="small"
            bordered
            pagination={{ pageSize: 20, hideOnSinglePage: true }}
            scroll={{ x: 900 }}
          />
        </section>
      )}
    </div>
  )
}