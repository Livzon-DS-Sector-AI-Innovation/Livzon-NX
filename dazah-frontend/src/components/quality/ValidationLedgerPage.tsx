'use client'

import { useCallback, useEffect, useState } from 'react'
import { App, Button, Space } from 'antd'
import { CloudDownloadOutlined, PlusOutlined } from '@ant-design/icons'
import {
  createFeishuValidationAction,
  deleteFeishuValidationAction,
  pullFeishuValidations,
  updateFeishuValidationAction,
} from '@/actions/quality'
import { fetchFeishuValidations } from '@/lib/api/quality'
import type { FeishuValidationItem } from '@/types/quality'
import { ValidationEditModal } from './ValidationEditModal'
import { ValidationTable } from './ValidationTable'

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
  const [items, setItems] = useState<FeishuValidationItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [pulling, setPulling] = useState(false)
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
  const [saving, setSaving] = useState(false)
  const [editingRecord, setEditingRecord] = useState<FeishuValidationItem | null>(null)

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const result = await fetchFeishuValidations({
        validation_type: mode === 'child' ? validationType : filters.validation_type || undefined,
        keyword: filters.keyword || undefined,
        status: filters.status || undefined,
        department: filters.department || undefined,
        record_code: filters.record_code || undefined,
        planned_end_date_from:
          mode === 'master' ? filters.planned_end_date_from || undefined : undefined,
        planned_end_date_to:
          mode === 'master' ? filters.planned_end_date_to || undefined : undefined,
        drafted_at_from:
          mode === 'child' ? filters.drafted_at_from || undefined : undefined,
        drafted_at_to:
          mode === 'child' ? filters.drafted_at_to || undefined : undefined,
        page,
        page_size: pageSize,
      })
      setItems(result.items)
      setTotal(result.total)
    } catch (error: unknown) {
      message.error(getErrorMessage(error, `加载${title}失败`))
    } finally {
      setLoading(false)
    }
  }, [filters, message, mode, page, pageSize, title, validationType])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadData()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadData])

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const pullResult = await pullFeishuValidations(
        mode === 'child' ? validationType : undefined
      )
      message.success(
        `飞书数据拉取完成：同步 ${pullResult.synced} 条，失败 ${pullResult.failed} 条`
      )
      await loadData()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '飞书数据拉取失败'))
    } finally {
      setPulling(false)
    }
  }, [loadData, message, mode, validationType])

  const handleCreate = useCallback(() => {
    setEditingRecord(null)
    setEditorOpen(true)
  }, [])

  const handleEdit = useCallback((record: FeishuValidationItem) => {
    setEditingRecord(record)
    setEditorOpen(true)
  }, [])

  const handleDelete = useCallback(
    (record: FeishuValidationItem) => {
      modal.confirm({
        title: '确认删除',
        content: `确定要删除记录 "${record.title}" 吗？此操作将同步删除飞书 Base 中的记录。`,
        okText: '确认',
        cancelText: '取消',
        okButtonProps: { danger: true },
        onOk: async () => {
          try {
            await deleteFeishuValidationAction(
              record.record_id,
              mode === 'child' ? validationType : undefined
            )
            message.success('删除成功，已同步到飞书')
            await loadData()
          } catch (error: unknown) {
            message.error(getErrorMessage(error, '删除失败'))
          }
        },
      })
    },
    [loadData, message, modal, mode, validationType]
  )

  const handleSubmit = useCallback(
    async (values: Record<string, unknown>) => {
      try {
        setSaving(true)
        if (editingRecord) {
          await updateFeishuValidationAction(
            editingRecord.record_id,
            values,
            mode === 'child' ? validationType : undefined
          )
          message.success(`${title}已更新，已同步到飞书`)
        } else {
          await createFeishuValidationAction(values)
          message.success(`${title}已创建，已同步到飞书`)
        }
        setEditorOpen(false)
        await loadData()
      } catch (error: unknown) {
        message.error(getErrorMessage(error, `保存${title}失败`))
      } finally {
        setSaving(false)
      }
    },
    [editingRecord, loadData, message, mode, title, validationType]
  )

  const handleBatchDelete = useCallback(
    async (ids: string[]) => {
      modal.confirm({
        title: '确认批量删除',
        content: `确定要删除选中的 ${ids.length} 条记录吗？此操作将同步删除飞书 Base 中的记录。`,
        okText: '确认',
        cancelText: '取消',
        okButtonProps: { danger: true },
        onOk: async () => {
          let successCount = 0
          let failCount = 0
          for (const id of ids) {
            try {
              await deleteFeishuValidationAction(
                id,
                mode === 'child' ? validationType : undefined
              )
              successCount++
            } catch {
              failCount++
            }
          }
          message.success(`批量删除完成：成功 ${successCount} 条${failCount > 0 ? `，失败 ${failCount} 条` : ''}`)
          await loadData()
        },
      })
    },
    [loadData, message, modal, mode, validationType]
  )

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">
          质量管理 / 验证与确认 / {title}
        </p>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>
              {mode === 'master' ? title : `${title}执行台账`}
            </h1>
            <p style={{ marginTop: 8, color: 'var(--color-steel)' }}>{description}</p>
          </div>
          <Space>
            <Button
              icon={<CloudDownloadOutlined />}
              loading={pulling}
              onClick={handlePullFromFeishu}
            >
              拉取飞书数据
            </Button>
            {mode === 'master' && (
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                新增主计划
              </Button>
            )}
          </Space>
        </div>
      </div>

      <ValidationTable
        mode={mode}
        validationType={validationType}
        items={items}
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
        onRefresh={loadData}
        onCreate={handleCreate}
        onEdit={handleEdit}
        onDelete={handleDelete}
        onBatchDelete={handleBatchDelete}
      />

      <ValidationEditModal
        open={editorOpen}
        saving={saving}
        mode={mode}
        validationType={validationType}
        validationTypeLabel={title}
        initialValue={editingRecord}
        onCancel={() => setEditorOpen(false)}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
