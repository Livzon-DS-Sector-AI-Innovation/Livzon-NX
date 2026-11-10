import type { EmployeeListQuery } from '@/lib/api/hr'

const filterKeys = ['keyword', 'position', 'department', 'sub_department', 'gender', 'level', 'education', 'status'] as const

type EmployeeProfileFilterKey = (typeof filterKeys)[number]
export type EmployeeProfileFilters = Partial<Record<EmployeeProfileFilterKey, string>>

export function readEmployeeProfileFilters(read: (key: EmployeeProfileFilterKey) => string | null | undefined): EmployeeProfileFilters {
  return Object.fromEntries(filterKeys.map(key => [key, read(key)?.trim() || undefined]))
}

export function employeeProfileQuery(
  { department, ...filters }: EmployeeProfileFilters,
  page: number,
  pageSize: number,
): EmployeeListQuery {
  return { ...filters, first_department: department, page, page_size: pageSize }
}
