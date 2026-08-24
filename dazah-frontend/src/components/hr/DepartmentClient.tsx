'use client'

import { useState, useCallback, useMemo, useEffect } from 'react'
import { App } from 'antd'
import type { Department, OrgTreeNode } from '@/types/hr'
import { deleteDepartment, fetchDepartmentsAction, fetchDepartmentTreeAction, fetchOrgTreeAction, syncDepartmentsFromFeishuAction, getDepartmentSyncStatus } from '@/actions/hr'
import { useSyncPolling } from './useSyncPolling'
import DepartmentTable from './DepartmentTable'
import DepartmentDetailDrawer from './DepartmentDetailDrawer'
import DepartmentForm from './DepartmentForm'
import DepartmentToolbar from './DepartmentToolbar'
import DepartmentTreeView from './DepartmentTreeView'

interface DepartmentClientProps {
  initialDepartments: Department[]
  initialTotal: number
  initialTreeDepartments?: Department[]
  initialAllDepartments?: Department[]
  initialOrgTreeData?: OrgTreeNode[]
}

export default function DepartmentClient({
  initialDepartments = [],
  initialTotal = 0,
  initialTreeDepartments = [],
  initialAllDepartments = [],
  initialOrgTreeData = [],
}: DepartmentClientProps) {
  const { message } = App.useApp()

  // 视图状态
  const [activeView, setActiveView] = useState<'table' | 'tree'>('table')
  const [loading, setLoading] = useState(false)

  // 数据状态
  const [departments, setDepartments] = useState<Department[]>(initialDepartments)
  const [total, setTotal] = useState(initialTotal)
  const [treeDepartments, setTreeDepartments] = useState<Department[]>(initialTreeDepartments)
  const [allDepartments, setAllDepartments] = useState<Department[]>(initialAllDepartments)
  const [orgTreeData, setOrgTreeData] = useState<OrgTreeNode[]>(initialOrgTreeData)

  // 筛选和分页
  const [filters, setFilters] = useState({ keyword: '', parentId: null as string | null, leaderName: '' })
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20 })

  // 表单和详情
  const [formOpen, setFormOpen] = useState(false)
  const [editingDept, setEditingDept] = useState<Department | null>(null)
  const [addParentId, setAddParentId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [selectedDept, setSelectedDept] = useState<Department | null>(null)
  const [selectedDeptId, setSelectedDeptId] = useState<string | null>(null)

  // 权限（Phase 1 暂用 true，后续接入 usePermission）
  const canEdit = true

  // 加载表格数据
  const loadTableData = useCallback(async (page?: number, pageSize?: number) => {
    setLoading(true)
    try {
      const p = page ?? pagination.current
      const ps = pageSize ?? pagination.pageSize
      const res = await fetchDepartmentsAction({
        keyword: filters.keyword || undefined,
        parent_id: filters.parentId || undefined,
        leader_name: filters.leaderName || undefined,
        page: p,
        page_size: ps,
      })
      setDepartments(res.data || [])
      setTotal(res.meta?.total || 0)
      setPagination({ current: p, pageSize: ps })
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [filters, pagination, message])

  // 加载树数据 + 组织架构树(含人员)
  const loadTreeData = useCallback(async () => {
    setLoading(true)
    try {
      const [treeRes, allRes] = await Promise.all([
        fetchDepartmentTreeAction(),
        fetchDepartmentsAction({ page: 1, page_size: 100 }),
      ])
      setTreeDepartments(treeRes.data || [])
      setAllDepartments(allRes.data || [])
      // org-tree 单独加载，容错处理
      try {
        const orgRes = await fetchOrgTreeAction()
        setOrgTreeData(orgRes.data || [])
      } catch {
        // 飞书API超时，使用空数组，表格回退到 treeDepartments
        setOrgTreeData([])
      }
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  // 筛选变化
  const handleFilterChange = useCallback((newFilters: typeof filters) => {
    setFilters(newFilters)
    setPagination(prev => ({ ...prev, current: 1 }))
  }, [])

  // 分页变化
  const handlePaginationChange = useCallback((page: number, pageSize: number) => {
    setPagination({ current: page, pageSize })
    loadTableData(page, pageSize)
  }, [loadTableData])

  // 行点击 -> 打开详情（从树数据中递归查找，含children）
  const handleRowClick = useCallback((id: string) => {
    const findDept = (list: Department[]): Department | undefined => {
      for (const d of list) {
        if (d.id === id) return d
        if (d.children) {
          const found = findDept(d.children)
          if (found) return found
        }
      }
      return undefined
    }
    const dept = findDept(treeDepartments)
    if (dept) {
      setSelectedDept(dept)
      setSelectedDeptId(id)
      setDrawerOpen(true)
    }
  }, [treeDepartments])

  // 树节点点击 → 打开详情
  const handleTreeNodeClick = useCallback((id: string) => {
    // 在树数据中查找
    const findDept = (list: Department[]): Department | undefined => {
      for (const d of list) {
        if (d.id === id) return d
        if (d.children) {
          const found = findDept(d.children)
          if (found) return found
        }
      }
      return undefined
    }
    const dept = findDept(treeDepartments)
    if (dept) {
      setSelectedDept(dept)
      setSelectedDeptId(id)
      setDrawerOpen(true)
    }
  }, [treeDepartments])

  // 新增部门
  const handleAdd = useCallback((parentId?: string) => {
    setEditingDept(null)
    setAddParentId(parentId ?? null)
    setFormOpen(true)
  }, [])

  // 编辑部门
  const handleEdit = useCallback((dept: Department) => {
    setEditingDept(dept)
    setAddParentId(null)
    setFormOpen(true)
  }, [])

  // 删除部门
  const handleDelete = useCallback(async (id: string) => {
    try {
      await deleteDepartment(id)
      message.success('部门已删除')
      loadTableData()
      loadTreeData()
      if (drawerOpen && selectedDept?.id === id) {
        setDrawerOpen(false)
        setSelectedDept(null)
      }
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '删除失败')
    }
  }, [message, loadTableData, loadTreeData, drawerOpen, selectedDept])

  // 表单成功回调
  const handleFormSuccess = useCallback(() => {
    loadTableData()
    loadTreeData()
  }, [loadTableData, loadTreeData])

  // 飞书同步（使用共享轮询 hook）
  const { isSyncing, startSync: handleSync } = useSyncPolling({
    syncAction: syncDepartmentsFromFeishuAction,
    pollAction: getDepartmentSyncStatus,
    maxPolls: 90,
    interval: 2000,
    onSuccess: (msg, result) => {
      if (result?.created !== undefined) {
        message.success(
          `同步完成：新增 ${result.created} 条，更新 ${result.updated} 条，跳过 ${result.skipped} 条，失败 ${result.failed} 条`,
        )
      } else {
        message.success(msg || '同步完成')
      }
      loadTableData()
      loadTreeData()
    },
    onError: (msg) => {
      message.error(msg)
    },
  })

  // 挂载后静默自动同步飞书：确保打开页面看到最新数据（后台执行，不阻塞页面）
  useEffect(() => {
    let cancelled = false
    const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))
    const autoSync = async () => {
      try {
        await syncDepartmentsFromFeishuAction()
        // 最多轮询 3 分钟，超时静默放弃
        for (let i = 0; i < 90; i++) {
          if (cancelled) return
          await wait(2000)
          const statusRes = await getDepartmentSyncStatus()
          const state = statusRes.data?.state
          if (state === 'completed' || state === 'failed') {
            if (!cancelled) {
              loadTableData()
              loadTreeData()
            }
            return
          }
        }
      } catch {
        // 静默失败，不打扰用户
      }
    }
    autoSync()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 表格视图：一级部门展开规则
  // 质量管理部/安全部/201车间/生产管理部 不显示本身，展开显示其二级部门
  const EXPANDABLE_DEPARTMENTS = ['质量管理部', '安全部', '201车间', '生产管理部']

  const filteredDepartments = useMemo(() => {
    // 从树数据中获取一级部门（含children）
    const rootDepts = treeDepartments.filter(d => !d.parent_id)
    const result: Department[] = []
    for (const dept of rootDepts) {
      if (EXPANDABLE_DEPARTMENTS.includes(dept.name) && dept.children && dept.children.length > 0) {
        // 展开为二级部门
        result.push(...dept.children)
      } else {
        result.push(dept)
      }
    }
    return result
  }, [treeDepartments])

  const tablePagination = useMemo(() => ({
    current: pagination.current,
    pageSize: pagination.pageSize,
    total: filteredDepartments.length,
    onChange: handlePaginationChange,
  }), [pagination, filteredDepartments.length, handlePaginationChange])

  return (
    <div className="space-y-4">
      <DepartmentToolbar
        activeView={activeView}
        onViewChange={setActiveView}
        canEdit={canEdit}
        onAdd={() => handleAdd()}
        onSync={handleSync}
        syncing={isSyncing}
      />

      {activeView === 'table' ? (
        <DepartmentTable
          departments={filteredDepartments}
          orgTreeData={orgTreeData.length > 0 ? orgTreeData : (treeDepartments as unknown as OrgTreeNode[])}
          loading={loading}
          filters={filters}
          onFilterChange={handleFilterChange}
          onRowClick={handleRowClick}
          onEdit={handleEdit}
          onDelete={handleDelete}
          canEdit={canEdit}
          allDepartments={allDepartments}
        />
      ) : (
        <DepartmentTreeView
          departments={treeDepartments}
          selectedDepartmentId={selectedDeptId}
          canEdit={canEdit}
          onSelect={setSelectedDeptId}
          onAdd={handleAdd}
          onEdit={handleEdit}
          onDelete={handleDelete}
          onRefresh={loadTreeData}
          onNodeClick={handleTreeNodeClick}
        />
      )}

      <DepartmentDetailDrawer
        open={drawerOpen}
        department={selectedDept}
        canEdit={canEdit}
        onClose={() => { setDrawerOpen(false); setSelectedDept(null) }}
        onEdit={(dept) => { setDrawerOpen(false); handleEdit(dept) }}
        onDelete={(id) => handleDelete(id)}
        onChildClick={handleRowClick}
        allDepartments={allDepartments}
      />

      <DepartmentForm
        open={formOpen}
        department={editingDept}
        parentId={addParentId}
        onClose={() => { setFormOpen(false); setEditingDept(null) }}
        onSuccess={handleFormSuccess}
        departments={[...departments, ...treeDepartments]}
      />
    </div>
  )
}
