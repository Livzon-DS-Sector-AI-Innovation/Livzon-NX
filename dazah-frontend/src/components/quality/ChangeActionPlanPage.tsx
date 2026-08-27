'use client'

import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { App, Button, Space } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createChangeActionPlan, deleteChangeActionPlan, syncChangeActionPlanToFeishu, syncChangeActionPlansFromFeishu, updateChangeActionPlan } from '@/actions/quality-change'
import { fetchChangeActionPlans } from '@/lib/api/client/quality'
import { ChangeActionPlanTable } from './ChangeActionPlanTable'

import type { ChangeActionPlanListItem } from '@/types/quality'
import { ChangeActionPlanEditModal } from './ChangeActionPlanEditModal'

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

export function ChangeActionPlanPage() {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const searchParams = useSearchParams()
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

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-change-plan', 'list', { ...filters, page, pageSize }],
    queryFn: () => fetchChangeActionPlans({
      ...filters,
      page,
      page_size: pageSize,
    }),
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载变更计划失败'))
    }
  }, [error, message])

  const items = data?.items ?? []
  const total = data?.total ?? 0

  const handleCreate = useCallback(() => {
    setEditingRecord(null)
    setEditorOpen(true)
  }, [])

  const handleSubmit = useCallback(
    async (values: Record<string, unknown>) => {
      try {
        setSaving(true)
        if (editingRecord) {
          await updateChangeActionPlan(editingRecord.id, values)
          message.success('变更计划已更新，人员字段请在飞书多维表维护后再同步回系统')
        } else {
          await createChangeActionPlan(values)
          message.success('变更计划已创建')
        }
        setEditorOpen(false)
        queryClient.invalidateQueries({ queryKey: ['quality-change-plan'] })
      } catch (error: unknown) {
        message.error(getErrorMessage(error, '保存变更计划失败'))
      } finally {
        setSaving(false)
      }
    },
    [editingRecord, message, queryClient]
  )

  const handleSyncAll = useCallback(async () => {
    try {
      const result = await syncChangeActionPlansFromFeishu()
      message.success(`同步完成：成功 ${result.synced} 条，失败 ${result.failed} 条。飞书多维表中的负责人/部门总监已按最新结果回写系统。`)
      queryClient.invalidateQueries({ queryKey: ['quality-change-plan'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '同步飞书失败'))
    }
  }, [message, queryClient])

  const handleSyncSingle = useCallback(
    async (record: ChangeActionPlanListItem) => {
      try {
        await syncChangeActionPlanToFeishu(record.id)
        message.success('已回写飞书')
        queryClient.invalidateQueries({ queryKey: ['quality-change-plan'] })
      } catch (error: unknown) {
        message.error(getErrorMessage(error, '回写飞书失败'))
      }
    },
    [message, queryClient]
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
            queryClient.invalidateQueries({ queryKey: ['quality-change-plan'] })
          } catch (error: unknown) {
            message.error(getErrorMessage(error, '删除变更计划失败'))
          }
        },
      })
    },
    [message, modal, queryClient]
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
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ['quality-change-plan'] })}
        onSyncAll={handleSyncAll}
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
