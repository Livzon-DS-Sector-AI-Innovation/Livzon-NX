'use client'

import { useEffect, useState } from 'react'
import { App } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { batchDeleteFeishuValidationsAction, createFeishuValidationAction, deleteFeishuValidationAction, updateFeishuValidationAction } from '@/actions/quality'
import { fetchValidations, fetchValidationExecutions } from '@/lib/api/client/quality'
import type { ValidationListItem, ValidationExecutionItem } from '@/types/quality'
import { ValidationEditModal } from './ValidationEditModal'
import { ValidationTable } from './ValidationTable'

/** 台账行：主列表为本地验证记录（无 record_id），子表为飞书执行记录（含 record_id） */
type ValidationRow = (ValidationListItem | ValidationExecutionItem) & { record_id?: string | null; id?: string }

/** 飞书操作优先用 record_id；本地记录回退主键 id */
function getRowRecordId(row: ValidationRow): string {
  return row.record_id || row.id || ''
}

interface ValidationLedgerPageProps {
  mode: 'master' | 'child'
  title: string
  description: string
  validationType?: string
}

interface ValidationTableFilters {
  record_code: string
  keyword: string
  status: string
  department: string
  validation_type: string
  planned_end_date_from: string
  planned_end_date_to: string
  drafted_at_from: string
  drafted_at_to: string
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

export function ValidationLedgerPage({
  mode,
  validationType,
  title,
  description,
}: ValidationLedgerPageProps) {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState<ValidationTableFilters>({
    record_code: '',
    keyword: '',
    status: '',
    department: '',
    validation_type: '',
    planned_end_date_from: '',
    planned_end_date_to: '',
    drafted_at_from: '',
    drafted_at_to: '',
  })
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<ValidationRow | null>(null)

  const { data, isLoading: loading, error } = useQuery<{ items: ValidationRow[]; total: number }>({
    queryKey: ['quality-validation', 'list', {
      mode,
      validationType: validationType ?? '',
      record_code: filters.record_code,
      keyword: filters.keyword,
      status: filters.status,
      department: filters.department,
      validation_type: filters.validation_type,
      planned_end_date_from: filters.planned_end_date_from,
      planned_end_date_to: filters.planned_end_date_to,
      drafted_at_from: filters.drafted_at_from,
      drafted_at_to: filters.drafted_at_to,
      page,
      pageSize,
    }],
    queryFn: () =>
      mode === 'master'
        ? fetchValidations({
            validation_type: filters.validation_type || undefined,
            record_code: filters.record_code || undefined,
            keyword: filters.keyword || undefined,
            status: filters.status || undefined,
            department: filters.department || undefined,
            planned_end_date_from: filters.planned_end_date_from || undefined,
            planned_end_date_to: filters.planned_end_date_to || undefined,
            page,
            page_size: pageSize,
          })
        : fetchValidationExecutions(validationType ?? '', {
            keyword: filters.keyword || undefined,
            status: filters.status || undefined,
            department: filters.department || undefined,
            drafted_at_from: filters.drafted_at_from || undefined,
            drafted_at_to: filters.drafted_at_to || undefined,
            page,
            page_size: pageSize,
          }),
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, `加载${title}失败`))
    }
  }, [error, message, title])

  const items = data?.items ?? []
  const total = data?.total ?? 0

  const handleCreate = () => {
    setEditingRecord(null)
    setEditorOpen(true)
  }

  const handleEdit = (record: ValidationListItem) => {
    setEditingRecord(record)
    setEditorOpen(true)
  }

  const handleDelete = (record: ValidationListItem) => {
    modal.confirm({
      title: '确认删除',
      content: `确定要删除记录 "${record.title}" 吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteFeishuValidationAction(getRowRecordId(record), record.validation_type)
          message.success('删除成功')
          queryClient.invalidateQueries({ queryKey: ['quality-validation', 'list'] })
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '删除失败'))
        }
      },
    })
  }

  const handleSubmit = async (values: Record<string, unknown>) => {
    try {
      setSaving(true)
      if (editingRecord) {
        await updateFeishuValidationAction(
          getRowRecordId(editingRecord),
          values,
          editingRecord.validation_type ?? undefined
        )
        message.success(`${title}已更新`)
      } else {
        await createFeishuValidationAction(values)
        message.success(`${title}已创建`)
      }
      setEditorOpen(false)
      queryClient.invalidateQueries({ queryKey: ['quality-validation', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, `保存${title}失败`))
    } finally {
      setSaving(false)
    }
  }

  const handleBatchDelete = async (recordIds: string[]) => {
    try {
      await batchDeleteFeishuValidationsAction(recordIds, validationType)
      message.success(`成功删除 ${recordIds.length} 条记录`)
      queryClient.invalidateQueries({ queryKey: ['quality-validation', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '批量删除失败'))
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 验证与确认 / {title}</p>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>
          {mode === 'master' ? title : `${title}执行台账`}
        </h1>
        <p style={{ marginTop: 8, color: 'var(--color-steel)' }}>{description}</p>
      </div>

      <ValidationTable
        mode={mode}
        validationType={validationType}
        items={items as ValidationListItem[]}
        total={total}
        loading={loading}
        page={page}
        pageSize={pageSize}
        filters={filters}
        onFilterChange={(patch) => {
          setPage(1)
          setFilters((prev) => ({ ...prev, ...patch }))
        }}
        onPageChange={(nextPage, nextPageSize) => {
          setPage(nextPage)
          setPageSize(nextPageSize)
        }}
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ['quality-validation', 'list'] })}
        onCreate={handleCreate}
        onEdit={handleEdit}
        onDelete={handleDelete}
        onBatchDelete={handleBatchDelete}
      />

      <ValidationEditModal
        open={editorOpen}
        saving={saving}
        validationType={validationType}
        validationTypeLabel={title}
        initialValue={editingRecord as ValidationListItem | null}
        onCancel={() => setEditorOpen(false)}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
