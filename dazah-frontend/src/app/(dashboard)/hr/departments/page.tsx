import { fetchDepartments, fetchDepartmentTreeAction, fetchOrgTreeAction } from '@/actions/hr'
import { DepartmentClient } from '@/components/hr'
import type { OrgTreeNode } from '@/types/hr'

export const dynamic = 'force-dynamic'

export default async function DepartmentsPage() {
  // 每个请求独立容错，避免单个 API 失败导致整个页面崩溃
  let tableRes: Awaited<ReturnType<typeof fetchDepartments>> = { data: [], meta: { total: 0, page: 1, page_size: 20 } } as any
  let treeRes: Awaited<ReturnType<typeof fetchDepartmentTreeAction>> = { code: 0, message: '', data: [] }
  let allRes: Awaited<ReturnType<typeof fetchDepartments>> = { data: [], meta: { total: 0, page: 1, page_size: 100 } } as any

  try {
    tableRes = await fetchDepartments({ page: 1, page_size: 20 })
  } catch (error) {
    console.warn('加载部门列表失败:', error)
  }
  try {
    treeRes = await fetchDepartmentTreeAction()
  } catch (error) {
    console.warn('加载部门树失败:', error)
  }
  try {
    allRes = await fetchDepartments({ page: 1, page_size: 100 })
  } catch (error) {
    console.warn('加载全量部门列表失败:', error)
  }

  // org-tree 单独加载，容错处理（飞书API可能超时）
  let orgTreeData: OrgTreeNode[] = []
  try {
    const orgRes = await fetchOrgTreeAction()
    orgTreeData = orgRes.data || []
  } catch {
    // 超时则使用空数组，前端回退到 treeDepartments
  }

  return (
    <DepartmentClient
      initialDepartments={tableRes.data}
      initialTotal={tableRes.meta?.total || 0}
      initialTreeDepartments={treeRes.data || []}
      initialAllDepartments={allRes.data || []}
      initialOrgTreeData={orgTreeData}
    />
  )
}
