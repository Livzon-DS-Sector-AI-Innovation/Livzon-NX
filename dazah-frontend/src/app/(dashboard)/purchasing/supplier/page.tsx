import { SupplierManagementClient } from '@/components/purchasing'
import { fetchSuppliers } from '@/lib/api/purchasing'
import { getAuthHeaders } from '@/lib/auth'

export const dynamic = 'force-dynamic'

const DEFAULT_PAGE_SIZE = 20

function getColumnsFromMeta(meta: Record<string, unknown> | null | undefined) {
  const columns = meta?.columns
  if (!Array.isArray(columns)) return []
  return columns.filter((column): column is string => typeof column === 'string')
}

export default async function SupplierManagementPage() {
  let initialLoadFailed = false
  const response = await fetchSuppliers({
    page: 1,
    page_size: DEFAULT_PAGE_SIZE,
  }, await getAuthHeaders()).catch(() => {
    initialLoadFailed = true
    return {
      code: 200,
      message: 'success',
      data: [],
      meta: {
        page: 1,
        page_size: DEFAULT_PAGE_SIZE,
        total: 0,
        columns: [],
      },
    }
  })

  const initialTotal = Number(response.meta?.total ?? response.data.length)

  return (
    <SupplierManagementClient
      initialRecords={response.data}
      initialTotal={Number.isFinite(initialTotal) ? initialTotal : response.data.length}
      initialColumns={getColumnsFromMeta(response.meta)}
      initialLoadFailed={initialLoadFailed}
    />
  )
}
