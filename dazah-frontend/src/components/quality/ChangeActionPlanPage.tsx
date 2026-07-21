'use client'

import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { App, Button, Space } from 'antd'
import {
  createChangeActionPlan,
  deleteChangeActionPlan,
  syncChangeActionPlanToFeishu,
  syncChangeActionPlansFromFeishu,
  updateChangeActionPlan,
} from '@/actions/quality'
import {
  fetchChangeActionPlans,
} from '@/lib/api/quality'
import type { ChangeActionPlanListItem } from '@/types/quality'
import { ChangeActionPlanTable } from './ChangeActionPlanTable'
import { ChangeActionPlanEditModal } from './change-action-plan-edit-modal'

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

export function ChangeActionPlanPage() {
  const { message, modal } = App.useApp()
  const searchParams = useSearchParams()
  const [items, setItems] = useState<ChangeActionPlanListItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({
    change_code: searchParams.get('change_code') ?? '',
    project_name: '',
    related_work: '',
    owner_name: '',
    status: '',
  })
  const [editorOpen, setEditorOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editingRecord, setEditingRecord] = useState<ChangeActionPlanListItem | null>(null)

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const result = await fetchChangeActionPlans({
        ...filters,
        page,
        page_size: pageSize,
      })
      setItems(result.items)
      setTotal(result.total)
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '加载变更计划失败'))
    } finally {
      setLoading(false)
    }
  }, [filters, message, page, pageSize])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadData()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadData])

  const handleCreate = useCallback(() => {
    setEditingRecord(null)
    setEditorOpen(true)
  }, [])

  const handleSubmit = useCallback(
    async (values: Record<string, unknown>) => {
      try {
        setSaving(true)
        if (editingRecord) {
          const payload = { ...values }
          if (payload.owner_user_id === editingRecord.owner_user_id) {
            delete payload.owner_user_id
          }
          if (payload.owner_name === editingRecord.owner_name) {
            delete payload.owner_name
          }
          if (payload.director_user_id === editingRecord.director_user_id) {
            delete payload.director_user_id
          }
          if (payload.director_name === editingRecord.director_name) {
            delete payload.director_name
          }
          await updateChangeActionPlan(editingRecord.id, payload)
          message.success('变更计划已更新并同步飞书')
        } else {
          await createChangeActionPlan(values)
          message.success('变更计划已创建')
        }
        setEditorOpen(false)
        await loadData()
      } catch (error: unknown) {
        message.error(getErrorMessage(error, '保存变更计划失败'))
      } finally {
        setSaving(false)
      }
    },
    [editingRecord, loadData, message]
  )

  const handlePullFromFeishu = useCallback(async () => {
    try {
      const result = await syncChangeActionPlansFromFeishu()
      message.success(`拉取完成：成功 ${result.synced} 条，失败 ${result.failed} 条。飞书多维表中的负责人/部门负责人已按最新结果回写系统。`)
      await loadData()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '拉取飞书失败'))
    }
  }, [loadData, message])

  const handleSyncSingle = useCallback(
    async (record: ChangeActionPlanListItem) => {
      try {
        await syncChangeActionPlanToFeishu(record.id)
        message.success('已回写飞书')
        await loadData()
      } catch (error: unknown) {
        message.error(getErrorMessage(error, '回写飞书失败'))
      }
    },
    [loadData, message]
  )

  const handleDelete = useCallback(
    (record: ChangeActionPlanListItem) => {
      modal.confirm({
        title: '确认删除',
        content: `确定要删除变更计划 "${record.project_name}" 吗？`,
        okText: '删除',
        okType: 'danger',
        cancelText: '取消',
        onOk: async () => {
          try {
            await deleteChangeActionPlan(record.id)
            message.success('变更计划已删除')
            await loadData()
          } catch (error: unknown) {
            message.error(getErrorMessage(error, '删除变更计划失败'))
          }
        },
      })
    },
    [loadData, message, modal]
  )

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>变更计划台账</h1>
        <Space>
          <Button type="primary" onClick={handleCreate}>
            新增变更计划
          </Button>
        </Space>
      </div>
      <ChangeActionPlanTable
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
        onSyncAll={handlePullFromFeishu}
        onEdit={(record) => {
          setEditingRecord(record)
          setEditorOpen(true)
        }}
        onSyncSingle={handleSyncSingle}
        onDelete={handleDelete}
      />

      <ChangeActionPlanEditModal
        open={editorOpen}
        saving={saving}
        initialValue={editingRecord}
        onCancel={() => setEditorOpen(false)}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
