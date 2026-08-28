'use client'

import { useState, useCallback, useEffect } from 'react'
import { App, Button, Select, Input } from 'antd'
import { PlusOutlined, SearchOutlined, SyncOutlined } from '@ant-design/icons'
import { Employee } from '@/types/hr'
import { fetchEmployeesAction, syncFromFeishuAction } from '@/actions/hr'
import { fetchTrainingDepartments } from '@/lib/api/client/hr'
import { useHrStore } from '@/stores/hr'
import { usePermission } from '@/hooks/usePermission'
import EmployeeTable from './EmployeeTable'
import EmployeeForm from './EmployeeForm'
import EmployeeDetailDrawer from './EmployeeDetailDrawer'
import HrChatbot from './HrChatbot'
import ContractAlertBanner from './ContractAlertBanner'

interface EmployeeProfileClientProps {
  initialEmployees: Employee[]
  initialTotal: number
  fetchAction?: typeof fetchEmployeesAction
}

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debouncedValue
}

export default function EmployeeProfileClient({
  initialEmployees,
  initialTotal,
  fetchAction }: EmployeeProfileClientProps) {
  const { message } = App.useApp()
  const [syncing, setSyncing] = useState(false)
  const [employees, setEmployees] = useState<Employee[]>(initialEmployees)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [formOpen, setFormOpen] = useState(false)
  const [editingEmployee, setEditingEmployee] = useState<Employee | null>(null)
  const [viewingEmployee, setViewingEmployee] = useState<Employee | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [departments, setDepartments] = useState<string[]>([])
  const [filterDepartment, setFilterDepartment] = useState('')
  const [filterSubDepartment, setFilterSubDepartment] = useState('')
  const [filterGender, setFilterGender] = useState('')
  const [filterLevel, setFilterLevel] = useState('')
  const [filterPosition, setFilterPosition] = useState('')

  const { searchKeyword, setSearchKeyword, filterStatus, setFilterStatus } = useHrStore()
  const debouncedSearchKeyword = useDebounce(searchKeyword, 300)
  const debouncedPosition = useDebounce(filterPosition, 300)

  const doFetch = fetchAction || fetchEmployeesAction

  const loadData = useCallback(async () => {
    try {
      const res = await doFetch({
        keyword: debouncedSearchKeyword || undefined,
        department: filterDepartment || undefined,
        sub_department: filterSubDepartment || undefined,
        status: filterStatus || undefined,
        gender: filterGender || undefined,
        level: filterLevel || undefined,
        position: debouncedPosition || undefined,
        page,
        page_size: pageSize })
      setEmployees(res.data)
      setTotal(res.meta?.total || 0)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '加载数据失败')
    }
  }, [debouncedSearchKeyword, filterDepartment, filterSubDepartment, filterStatus, filterGender, filterLevel, debouncedPosition, page, pageSize, doFetch, message])

  const loadDepartments = useCallback(async () => {
    try {
      // 部门选项使用"培训部门列表"接口：后端按当前用户可见范围过滤，
      // 非管理员只看到自己可见的部门，避免筛选越权部门触发 403
      const depts = await fetchTrainingDepartments()
      setDepartments(depts || [])
    } catch {
      setDepartments([])
    }
  }, [])

  const handlePageChange = (newPage: number, newPageSize: number) => {
    setPage(newPage)
    setPageSize(newPageSize)
  }

  const handleRefresh = () => {
    loadData()
    loadDepartments()
  }

  const handleSync = async (silent = false) => {
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
    setEditingEmployee(employee)
    setFormOpen(true)
  }

  const handleView = (employee: Employee) => {
    setViewingEmployee(employee)
    setDetailOpen(true)
  }

  // 编辑权限：仅人力资源部（hr:write）可新增/同步/编辑/删除员工
  const { has } = usePermission()
  const canEditHr = has('hr:write')

  const handleAdd = () => {
    setEditingEmployee(null)
    setFormOpen(true)
  }

  const handleFormSuccess = () => {
    loadData()
  }

  // Sync is manual-only — no auto-sync on mount

  useEffect(() => {
    queueMicrotask(loadData)
  }, [debouncedSearchKeyword, filterDepartment, filterSubDepartment, filterStatus, filterGender, filterLevel, debouncedPosition, page, pageSize, loadData])

  useEffect(() => {
    queueMicrotask(loadDepartments)
  }, [loadDepartments])

  const departmentOptions = departments.map((d) => ({ value: d, label: d }))

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
          员工档案
        </h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          新增员工
        </Button>
        {canEditHr ? (
          <Button icon={<SyncOutlined spin={syncing} />} loading={syncing} onClick={() => handleSync(false)}>
            同步飞书
          </Button>
        ) : null}
      </div>

      <ContractAlertBanner />

      {/* 筛选区 - 所有条件同一行 */}
      <div className="flex flex-nowrap gap-2 items-center">
        <Input
          placeholder="姓名/工号"
          value={searchKeyword}
          onChange={(e) => setSearchKeyword(e.target.value)}
          prefix={<SearchOutlined />}
          style={{ width: 130 }}
          allowClear
        />
        <Input
          placeholder="岗位"
          value={filterPosition}
          onChange={(e) => setFilterPosition(e.target.value)}
          style={{ width: 100 }}
          allowClear
        />
        <Select
          placeholder="部门"
          value={filterDepartment || undefined}
          onChange={(value) => setFilterDepartment(value || '')}
          allowClear
          style={{ width: 110 }}
          options={departmentOptions}
          showSearch
          filterOption={(input, option) =>
            (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
          }
        />
        <Select
          placeholder="二级部门"
          value={filterSubDepartment || undefined}
          onChange={(value) => setFilterSubDepartment(value || '')}
          allowClear
          style={{ width: 110 }}
          showSearch
        />
        <Select
          placeholder="性别"
          value={filterGender || undefined}
          onChange={(value) => setFilterGender(value || '')}
          allowClear
          style={{ width: 70 }}
          options={[
            { value: '男', label: '男' },
            { value: '女', label: '女' },
          ]}
        />
        <Select
          placeholder="职级"
          value={filterLevel || undefined}
          onChange={(value) => setFilterLevel(value || '')}
          allowClear
          style={{ width: 70 }}
          options={[
            { value: '高级', label: '高级' },
            { value: '中级', label: '中级' },
            { value: '初级', label: '初级' },
            { value: '员级', label: '员级' },
          ]}
        />
        <Select
          placeholder="状态"
          value={filterStatus || undefined}
          onChange={(value) => setFilterStatus(value || '')}
          allowClear
          style={{ width: 90 }}
          options={[
            { value: '在职', label: '在职' },
            { value: '试用期', label: '试用期' },
            { value: '离职', label: '离职' },
            { value: '待审批', label: '待审批' },
          ]}
        />
      </div>

      <EmployeeTable
        employees={employees}
        total={total}
        page={page}
        pageSize={pageSize}
        onPageChange={handlePageChange}
        onRefresh={handleRefresh}
        onEdit={handleEdit}
        onView={handleView}
      />

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

      <HrChatbot />
    </div>
  )
}
