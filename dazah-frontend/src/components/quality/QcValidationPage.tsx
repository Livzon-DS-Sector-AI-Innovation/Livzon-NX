'use client'

import { useEffect, useMemo, useState } from 'react'
import { App, Alert, Button, Input, Select, Space, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, EyeOutlined } from '@ant-design/icons'
import {
  fetchQcValidationFields,
  fetchQcValidationRecords,
  fetchQcValidationYears,
} from '@/lib/api/client/quality'
import type {
  QcValidationFieldMeta,
  QcValidationRecord,
} from '@/types/quality'
import {
  createQcValidationRecord,
  deleteQcValidationRecord,
  updateQcValidationRecord,
} from '@/actions/quality-validation-qc'
import { QcValidationDetailDrawer, QC_LIST_FIELD_ORDER } from './QcValidationDetailDrawer'
import { QcValidationFormModal } from './QcValidationFormModal'
import {
  renderFeishuValue,
  type FeishuAttachmentUrlBuilder,
} from './inspection/renderFeishuValue'
import { TableEmptyState } from './TableEmptyState'

const QC_YEARS = Array.from({ length: 5 }, (_, i) => 2024 + i)

function qcAttachmentUrlBuilder(year: number): FeishuAttachmentUrlBuilder {
  return (_entityCode, recordId, fileToken) =>
    `/api/v1/quality/validation-qc/records/${encodeURIComponent(recordId)}/attachments/${encodeURIComponent(fileToken)}/content?year=${year}`
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

/** QC验证（验证与确认-QC验证）：按年读取飞书多维表格，列表展示方案名称→人员，详情看全量。 */
export function QcValidationPage() {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const currentYear = useMemo(() => new Date().getFullYear(), [])
  const defaultYear = QC_YEARS.includes(currentYear) ? currentYear : 2026
  const [year, setYear] = useState<number>(defaultYear)
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [detailRecord, setDetailRecord] = useState<QcValidationRecord | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<QcValidationRecord | null>(null)
  const [saving, setSaving] = useState(false)

  const { data: years } = useQuery({
    queryKey: ['qc-validation', 'years'],
    queryFn: fetchQcValidationYears,
  })
  const { data: fieldsResult } = useQuery({
    queryKey: ['qc-validation', 'fields', year],
    queryFn: () => fetchQcValidationFields(year),
  })
  const listQuery = useQuery({
    queryKey: ['qc-validation', 'list', year, keyword, page, pageSize],
    queryFn: () => fetchQcValidationRecords(year, { keyword: keyword || undefined, page, page_size: pageSize }),
  })

  const records = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0
  const fieldMetas: QcValidationFieldMeta[] = fieldsResult?.fields ?? []
  const yearStatus = years?.find((item) => item.year === year)

  useEffect(() => {
    if (listQuery.error) {
      message.error(getErrorMessage(listQuery.error, `加载${year}年QC验证记录失败`))
    }
  }, [listQuery.error, message, year])

  const openDetail = (record: QcValidationRecord) => {
    setDetailRecord(record)
    setDetailOpen(true)
  }

  const handleDelete = (record: QcValidationRecord) => {
    const name = String(record['方案名称'] ?? record.record_id)
    modal.confirm({
      title: '确认删除',
      content: `确定要删除记录 "${name}" 吗？删除会同步到飞书多维表格。`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteQcValidationRecord(year, record.record_id)
          message.success('删除成功')
          queryClient.invalidateQueries({ queryKey: ['qc-validation', 'list', year] })
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '删除失败'))
        }
      },
    })
  }

  const handleSubmit = async (fields: Record<string, unknown>) => {
    try {
      setSaving(true)
      if (editingRecord) {
        await updateQcValidationRecord(year, editingRecord.record_id, fields)
        message.success('QC验证记录已更新')
      } else {
        await createQcValidationRecord(year, fields)
        message.success('QC验证记录已创建')
      }
      setEditorOpen(false)
      setEditingRecord(null)
      queryClient.invalidateQueries({ queryKey: ['qc-validation', 'list', year] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存QC验证记录失败'))
    } finally {
      setSaving(false)
    }
  }

  const columns: ColumnsType<QcValidationRecord> = QC_LIST_FIELD_ORDER.map(
    (fieldName) => {
      const meta = fieldMetas.find((item) => item.field_name === fieldName)
      return {
        title: fieldName,
        key: fieldName,
        width: fieldName === '方案名称' ? 260 : 130,
        fixed: fieldName === '方案名称' ? ('left' as const) : undefined,
        render: (_: unknown, record: QcValidationRecord) =>
          fieldName === '方案名称' ? (
            <a onClick={() => openDetail(record)} style={{ whiteSpace: 'normal', wordBreak: 'break-all' }}>
              {renderFeishuValue(record[fieldName], record, undefined, message, {
                uiType: meta?.ui_type,
                attachmentUrlBuilder: qcAttachmentUrlBuilder(year),
              })}
            </a>
          ) : (
            <div style={{ whiteSpace: 'normal', wordBreak: 'break-all' }}>
              {renderFeishuValue(record[fieldName], record, undefined, message, {
                uiType: meta?.ui_type,
                attachmentUrlBuilder: qcAttachmentUrlBuilder(year),
              })}
            </div>
          ),
      }
    },
  )

  columns.push({
    title: '操作',
    key: 'action',
    fixed: 'right',
    width: 150,
    render: (_: unknown, record: QcValidationRecord) => (
      <Space size="small">
        <Button type="text" icon={<EyeOutlined />} onClick={() => openDetail(record)} />
        <Button
          type="text"
          icon={<EditOutlined />}
          onClick={() => {
            setEditingRecord(record)
            setEditorOpen(true)
          }}
        />
        <Button type="text" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)} />
      </Space>
    ),
  })

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 验证与确认 / QC验证</p>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>QC验证（{year}年）</h1>
        <p style={{ marginTop: 8, color: 'var(--color-steel)' }}>
          读取飞书 QC验证年度表；列表展示方案名称至人员，点击行查看全部内容与附件，支持新增、编辑、删除。
        </p>
      </div>

      {yearStatus && !yearStatus.table_configured && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={`${year} 年 QC验证飞书表未配置`}
          description={`请到 质量管理 → 飞书同步设置 中为「QC验证-${year}年」绑定 App Token 与表 ID 后刷新本页。`}
        />
      )}

      <Space wrap style={{ marginBottom: 12 }}>
        <Select
          style={{ width: 130 }}
          value={year}
          onChange={(value) => {
            setYear(value)
            setPage(1)
          }}
          options={QC_YEARS.map((item) => ({
            label:
              years?.find((status) => status.year === item)?.table_configured
                ? `${item}年`
                : `${item}年（未配置）`,
            value: item,
          }))}
        />
        <Input
          placeholder="方案名称/编码等关键词"
          style={{ width: 240 }}
          value={keyword}
          allowClear
          onChange={(event) => {
            setKeyword(event.target.value)
            setPage(1)
          }}
        />
        <Button
          icon={<PlusOutlined />}
          type="primary"
          onClick={() => {
            setEditingRecord(null)
            setEditorOpen(true)
          }}
        >
          新增
        </Button>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => queryClient.invalidateQueries({ queryKey: ['qc-validation'] })}
        >
          刷新
        </Button>
      </Space>

      <Table<QcValidationRecord>
        rowKey="record_id"
        loading={listQuery.isLoading}
        dataSource={records}
        columns={columns}
        scroll={{ x: 1900 }}
        locale={{
          emptyText: (
            <TableEmptyState hasFilters={Boolean(keyword) || page > 1} />
          ),
        }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (count) => `共 ${count} 条`,
          onChange: (nextPage, nextPageSize) => {
            setPage(nextPage)
            setPageSize(nextPageSize)
          },
        }}
      />

      <QcValidationDetailDrawer
        open={detailOpen}
        record={detailRecord}
        fieldMetas={fieldMetas}
        attachmentUrlBuilder={qcAttachmentUrlBuilder(year)}
        onClose={() => {
          setDetailOpen(false)
          setDetailRecord(null)
        }}
      />

      <QcValidationFormModal
        open={editorOpen}
        saving={saving}
        year={year}
        fieldMetas={fieldMetas}
        initialRecord={editingRecord}
        onCancel={() => {
          setEditorOpen(false)
          setEditingRecord(null)
        }}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
