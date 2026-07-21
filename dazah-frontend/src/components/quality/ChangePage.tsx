'use client'

import { useCallback, useEffect, useState } from 'react'
import { App, Button } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { ChangeTable } from './ChangeTable'
import { useChangeStore } from '@/stores/quality'
import { syncChangesFromFeishu } from '@/actions/quality'
import { fetchChanges } from '@/lib/api/quality'

export function ChangePage() {
  const { message } = App.useApp()
  const [editorOpen, setEditorOpen] = useState(false)
  const {
    setChanges,
    setTotal,
    setLoading,
    loading,
    page,
    pageSize,
    changeCodeFilter,
    applicantDepartmentFilter,
    changeObjectFilter,
    changeLevelFilter,
    applicationDateFrom,
    applicationDateTo,
    plannedApprovalDateFrom,
    plannedApprovalDateTo,
    executionDateFrom,
    executionDateTo,
    closureDateFrom,
    closureDateTo,
    contentKeywordFilter,
  } = useChangeStore()

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const result = await fetchChanges({
        page,
        page_size: pageSize,
        change_code: changeCodeFilter || undefined,
        applicant_department: applicantDepartmentFilter || undefined,
        change_object: changeObjectFilter || undefined,
        change_level: changeLevelFilter || undefined,
        application_date_from: applicationDateFrom || undefined,
        application_date_to: applicationDateTo || undefined,
        planned_approval_date_from: plannedApprovalDateFrom || undefined,
        planned_approval_date_to: plannedApprovalDateTo || undefined,
        execution_date_from: executionDateFrom || undefined,
        execution_date_to: executionDateTo || undefined,
        closure_date_from: closureDateFrom || undefined,
        closure_date_to: closureDateTo || undefined,
        content_keyword: contentKeywordFilter || undefined,
      })
      setChanges(result.items)
      setTotal(result.total)
    } catch (error) {
      console.warn('加载变更数据失败:', error)
    } finally {
      setLoading(false)
    }
  }, [
    page,
    pageSize,
    changeCodeFilter,
    applicantDepartmentFilter,
    changeObjectFilter,
    changeLevelFilter,
    applicationDateFrom,
    applicationDateTo,
    plannedApprovalDateFrom,
    plannedApprovalDateTo,
    executionDateFrom,
    executionDateTo,
    closureDateFrom,
    closureDateTo,
    contentKeywordFilter,
    setChanges,
    setTotal,
    setLoading,
  ])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handlePullFromFeishu = useCallback(async () => {
    try {
      const result = await syncChangesFromFeishu()
      message.success(`拉取完成：成功 ${result.synced} 条，失败 ${result.failed} 条`)
      loadData()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '拉取飞书失败')
    }
  }, [loadData, message])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>变更管理台账</h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditorOpen(true)}>新增变更</Button>
      </div>
      <ChangeTable
        loading={loading}
        onRefresh={loadData}
        editorOpen={editorOpen}
        onCloseEditor={() => setEditorOpen(false)}
        onPullFromFeishu={handlePullFromFeishu}
      />
    </div>
  )
}
