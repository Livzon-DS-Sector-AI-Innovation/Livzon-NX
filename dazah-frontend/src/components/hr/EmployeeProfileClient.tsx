'use client'

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { App, Button } from 'antd'
import { PlusOutlined, SyncOutlined } from '@ant-design/icons'
import { Employee } from '@/types/hr'
import { syncFromFeishuAction } from '@/actions/hr'
import { fetchEmployeeFilterOptions, fetchEmployees, HrListReadError, type EmployeeFilterOptions } from '@/lib/api/hr'
import { getUserErrorMessage } from '@/lib/user-error'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { useListUrlState } from '@/lib/useListUrlState'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import EmployeeTable from './EmployeeTable'
import EmployeeForm from './EmployeeForm'
import EmployeeDetailDrawer from './EmployeeDetailDrawer'
import ContractAlertBanner from './ContractAlertBanner'
import EmployeeProfileFilterBar from './EmployeeProfileFilterBar'
import { employeeProfileQuery, readEmployeeProfileFilters } from './employeeProfileQuery'

interface EmployeeProfileClientProps {
  initialEmployees: Employee[]
  initialTotal: number
  fetchAction?: typeof fetchEmployees
}

const emptyOptions: EmployeeFilterOptions = { departments: [], levels: [], educations: [] }

export default function EmployeeProfileClient({
  initialEmployees,
  initialTotal,
  fetchAction }: EmployeeProfileClientProps) {
  const { message } = App.useApp()
  const { canOperate: canEditHr, canDelete, canSync } = usePagePermissions(
    'hr:employee-management:profile',
  )
  const [syncing, setSyncing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [employees, setEmployees] = useState<Employee[]>(initialEmployees)
  const [total, setTotal] = useState(initialTotal)
  const [formOpen, setFormOpen] = useState(false)
  const [editingEmployee, setEditingEmployee] = useState<Employee | null>(null)
  const [viewingEmployee, setViewingEmployee] = useState<Employee | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [options, setOptions] = useState(emptyOptions)
  const [loadingOptions, setLoadingOptions] = useState(true)
  const [optionsFailed, setOptionsFailed] = useState(false)
  const [refreshVersion, setRefreshVersion] = useState(0)
  const listRequestId = useRef(0)
  const optionsRequestId = useRef(0)
  const { page, pageSize, params, setListQuery } = useListUrlState()
  const queryString = params.toString()
  const filters = useMemo(() => {
    const query = new URLSearchParams(queryString)
    return readEmployeeProfileFilters(key => query.get(key))
  }, [queryString])

  const doFetch = fetchAction || fetchEmployees

  const loadData = useCallback(async () => {
    const requestId = ++listRequestId.current
    setLoading(true)
    try {
      const res = await doFetch(employeeProfileQuery(filters, page, pageSize))
      if (requestId !== listRequestId.current) return
      setEmployees(res.data)
      setTotal(res.meta?.total || 0)
      setLoadError(null)
    } catch (err) {
      if (requestId !== listRequestId.current) return
      setLoadError(getUserErrorMessage(err, '员工档案加载失败，请稍后重试'))
      if (err instanceof HrListReadError && [401, 403].includes(err.status)) {
        setEmployees([])
        setTotal(0)
      }
    } finally {
      if (requestId === listRequestId.current) setLoading(false)
    }
  }, [filters, page, pageSize, doFetch])

  const loadOptions = useCallback(async () => {
    const requestId = ++optionsRequestId.current
    setLoadingOptions(true)
    try {
      const result = await fetchEmployeeFilterOptions()
      if (requestId !== optionsRequestId.current) return
      setOptions(result)
      setOptionsFailed(false)
    } catch {
      if (requestId !== optionsRequestId.current) return
      setOptions(emptyOptions)
      setOptionsFailed(true)
    } finally {
      if (requestId === optionsRequestId.current) setLoadingOptions(false)
    }
  }, [])

  const handlePageChange = (newPage: number, newPageSize: number) => {
    if (newPageSize === pageSize) {
      setListQuery({ page: newPage })
    } else {
      setListQuery({ page_size: newPageSize }, true)
    }
  }

  const handleRefresh = () => {
    setRefreshVersion(version => version + 1)
  }

  const handleSync = async (silent = false) => {
    if (!canSync) return
    setSyncing(true)
    const hide = silent ? undefined : message.loading('正在从飞书同步数据，请稍候...', 0)
    try {
      const json = await syncFromFeishuAction()
      if (hide) hide()
      if (!silent) {
        message.success(json.message || '同步完成')
      }
      handleRefresh()
    } catch (e: unknown) {
      if (hide) hide()
      if (!silent) {
        message.error(e instanceof Error ? (e instanceof Error ? e.message : '') : '同步失败')
      }
    } finally {
      setSyncing(false)
    }
  }

  const handleEdit = (employee: Employee) => {
    if (!canEditHr) return
    setEditingEmployee(employee)
    setFormOpen(true)
  }

  const handleView = (employee: Employee) => {
    setViewingEmployee(employee)
    setDetailOpen(true)
  }

  const handleAdd = () => {
    if (!canEditHr) return
    setEditingEmployee(null)
    setFormOpen(true)
  }

  const handleFormSuccess = () => {
    handleRefresh()
  }

  // Sync is manual-only — no auto-sync on mount

  useEffect(() => {
    let active = true
    queueMicrotask(() => { if (active) void loadData() })
    return () => {
      active = false
      listRequestId.current += 1
    }
  }, [loadData, refreshVersion])

  useEffect(() => {
    let active = true
    queueMicrotask(() => { if (active) void loadOptions() })
    return () => {
      active = false
      optionsRequestId.current += 1
    }
  }, [loadOptions, refreshVersion])

  const hasFilters = Object.values(filters).some(Boolean)

  return (
    <div className="space-y-4 @container">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
          员工档案
        </h1>
        <Button type="primary" icon={<PlusOutlined />} disabled={!canEditHr} onClick={handleAdd}>
          新增员工
        </Button>
        {canSync ? (
          <Button icon={<SyncOutlined spin={syncing} />} loading={syncing} onClick={() => handleSync(false)}>
            同步飞书
          </Button>
        ) : null}
      </div>

      <ContractAlertBanner />

      <EmployeeProfileFilterBar
        key={JSON.stringify(filters)}
        filters={filters}
        options={options}
        loadingOptions={loadingOptions}
        optionsFailed={optionsFailed}
        onRetryOptions={loadOptions}
        onSubmit={patch => setListQuery(patch, true)}
      />

      {loadError && <PlatformNotice type="error" title={loadError}
        description="员工档案查询未成功。临时故障时保留上次加载的记录；登录失效或权限不足时清空记录，请重新登录或联系管理员。恢复后可重试。"
        action={<Button loading={loading} onClick={loadData}>重试</Button>} />}

      {(!loadError || employees.length > 0) && <EmployeeTable
        employees={employees}
        total={total}
        page={page}
        pageSize={pageSize}
        listLoading={loading}
        filtered={hasFilters}
        onPageChange={handlePageChange}
        onRefresh={handleRefresh}
        onEdit={handleEdit}
        onView={handleView}
        canEdit={canEditHr}
        canDelete={canDelete}
      />}

      <EmployeeForm
        open={formOpen}
        employee={editingEmployee}
        onClose={() => setFormOpen(false)}
        onSuccess={handleFormSuccess}
      />

      <EmployeeDetailDrawer
        open={detailOpen}
        employee={viewingEmployee}
        onClose={() => setDetailOpen(false)}
        onEdit={(emp) => {
          setDetailOpen(false)
          handleEdit(emp)
        }}
      />

    </div>
  )
}
