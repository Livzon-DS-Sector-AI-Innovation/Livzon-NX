import { Button, Space, Table } from 'antd'
import { DepartmentContact } from '@/types/quality'

interface DepartmentContactPageProps {
  items: DepartmentContact[]
  total: number
  page: number
  pageSize: number
  activeDepartment: string
  departmentOptions: string[]
}

interface DepartmentContactTableRow extends DepartmentContact {
  name_display: string
  department_display: string
  enterprise_email_display: string
  department_head_name_display: string
}

function buildDepartmentContactsHref(params: {
  department?: string
  page?: number
  pageSize?: number
}): string {
  const searchParams = new URLSearchParams()

  if (params.department && params.department !== '全部') {
    searchParams.set('department', params.department)
  }
  if (params.page && params.page > 1) {
    searchParams.set('page', String(params.page))
  }
  if (params.pageSize && params.pageSize !== 20) {
    searchParams.set('page_size', String(params.pageSize))
  }

  const query = searchParams.toString()
  return `/quality/department-contacts${query ? `?${query}` : ''}`
}

function getVisiblePages(page: number, totalPages: number): number[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1)
  }

  const candidates = new Set([1, totalPages, page - 1, page, page + 1])
  return Array.from(candidates)
    .filter((value) => value >= 1 && value <= totalPages)
    .sort((a, b) => a - b)
}

export function DepartmentContactPage({
  items,
  total,
  page,
  pageSize,
  activeDepartment,
  departmentOptions,
}: DepartmentContactPageProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const visiblePages = getVisiblePages(page, totalPages)
  const tableData: DepartmentContactTableRow[] = items.map((item) => ({
    ...item,
    name_display: item.name || '-',
    department_display: item.department || '-',
    enterprise_email_display: item.enterprise_email || '-',
    department_head_name_display: item.department_head_name || '-',
  }))

  const columns = [
    {
      title: '姓名',
      dataIndex: 'name_display',
      key: 'name',
      width: 220,
    },
    {
      title: '部门',
      dataIndex: 'department_display',
      key: 'department',
      width: 260,
    },
    {
      title: '企业邮箱',
      dataIndex: 'enterprise_email_display',
      key: 'enterprise_email',
      width: 360,
    },
    {
      title: '上级负责人姓名',
      dataIndex: 'department_head_name_display',
      key: 'department_head_name',
      width: 240,
    },
  ]

  return (
    <div style={{ padding: '4px 8px 20px' }}>
      <div style={{ maxWidth: 1680, margin: '0 auto' }}>
        <div style={{ marginBottom: 12 }}>
          <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>部门联系人台账</h1>
        </div>
        <div
          style={{
            marginBottom: 14,
            padding: '8px 12px',
            background: '#fff',
            border: '1px solid #f0f0f0',
            borderRadius: 10,
          }}
        >
          <Space wrap size={[6, 6]}>
            {departmentOptions.map((department) => {
              const active = activeDepartment === department
              return (
                <Button
                  key={department}
                  href={buildDepartmentContactsHref({ department, page: 1, pageSize })}
                  type="text"
                  size="small"
                  style={{
                    height: 28,
                    padding: '0 12px',
                    borderRadius: 999,
                    border: active ? '1px solid #6f5ef9' : '1px solid #d9d9d9',
                    background: active ? '#6f5ef9' : '#fff',
                    color: active ? '#fff' : '#262626',
                    fontSize: 12,
                    fontWeight: active ? 600 : 400,
                    boxShadow: active ? '0 3px 8px rgba(111, 94, 249, 0.16)' : 'none',
                  }}
                >
                  {department}
                </Button>
              )
            })}
          </Space>
        </div>
        <div
          style={{
            background: '#fff',
            borderRadius: 14,
            padding: 10,
            boxShadow: '0 6px 18px rgba(15, 23, 42, 0.05)',
          }}
        >
          <Table
            columns={columns}
            dataSource={tableData}
            rowKey="id"
            size="middle"
            scroll={{ x: 1200 }}
            pagination={false}
          />
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
              marginTop: 12,
              flexWrap: 'wrap',
            }}
          >
            <div style={{ color: '#595959', fontSize: 13 }}>共 {total} 条</div>
            <Space wrap size={[6, 6]}>
              {[20, 50, 100].map((size) => {
                const active = pageSize === size
                return (
                  <Button
                    key={size}
                    href={buildDepartmentContactsHref({ department: activeDepartment, page: 1, pageSize: size })}
                    size="small"
                    type="text"
                    style={{
                      height: 28,
                      padding: '0 10px',
                      borderRadius: 999,
                      border: active ? '1px solid #6f5ef9' : '1px solid #d9d9d9',
                      background: active ? '#f3f0ff' : '#fff',
                      color: active ? '#6f5ef9' : '#595959',
                      fontSize: 12,
                    }}
                  >
                    {size}条/页
                  </Button>
                )
              })}
            </Space>
            <Space wrap size={[6, 6]}>
              <Button
                href={buildDepartmentContactsHref({
                  department: activeDepartment,
                  page: Math.max(1, page - 1),
                  pageSize,
                })}
                disabled={page <= 1}
                size="small"
              >
                上一页
              </Button>
              {visiblePages.map((pageNumber) => {
                const active = pageNumber === page
                return (
                  <Button
                    key={pageNumber}
                    href={buildDepartmentContactsHref({
                      department: activeDepartment,
                      page: pageNumber,
                      pageSize,
                    })}
                    size="small"
                    type={active ? 'primary' : 'default'}
                    style={active ? { background: '#6f5ef9', borderColor: '#6f5ef9' } : undefined}
                  >
                    {pageNumber}
                  </Button>
                )
              })}
              <Button
                href={buildDepartmentContactsHref({
                  department: activeDepartment,
                  page: Math.min(totalPages, page + 1),
                  pageSize,
                })}
                disabled={page >= totalPages}
                size="small"
              >
                下一页
              </Button>
            </Space>
          </div>
        </div>
      </div>
    </div>
  )
}
