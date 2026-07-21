import { DepartmentContactPage } from '@/components/quality'
import { fetchFeishuDepartmentContactsAction } from '@/actions/quality'
import type { DepartmentContactListResponse } from '@/types/quality'

export const dynamic = 'force-dynamic'

type SearchParamsValue = string | string[] | undefined

interface DepartmentContactsPageProps {
  searchParams: Promise<Record<string, SearchParamsValue>>
}

function pickFirst(value: SearchParamsValue): string | undefined {
  if (Array.isArray(value)) {
    return value[0]
  }
  return value
}

function parsePositiveInteger(value: string | undefined, fallback: number): number {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

export default async function DepartmentContactsPage({ searchParams }: DepartmentContactsPageProps) {
  let initialData: DepartmentContactListResponse = {
    items: [],
    total: 0,
    page: 1,
    page_size: 1000,
  }

  try {
    initialData = await fetchFeishuDepartmentContactsAction(1, 1000)
  } catch (error) {
    console.warn('部门联系人飞书首屏加载失败:', error)
  }

  const params = await searchParams
  const activeDepartment = pickFirst(params.department) || '全部'
  const page = parsePositiveInteger(pickFirst(params.page), 1)
  const pageSize = parsePositiveInteger(pickFirst(params.page_size), 20)

  const departmentOptions = Array.from(
    new Set(
      initialData.items
        .map((item) => item.department?.trim())
        .filter((item): item is string => Boolean(item))
    )
  ).sort((a, b) => a.localeCompare(b, 'zh-CN'))

  const filteredItems =
    activeDepartment === '全部'
      ? initialData.items
      : initialData.items.filter((item) => item.department === activeDepartment)

  const total = filteredItems.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(page, totalPages)
  const start = (safePage - 1) * pageSize
  const pagedItems = filteredItems.slice(start, start + pageSize)

  return (
    <DepartmentContactPage
      items={pagedItems}
      total={total}
      page={safePage}
      pageSize={pageSize}
      activeDepartment={activeDepartment}
      departmentOptions={['全部', ...departmentOptions]}
    />
  )
}
