import { SupplierManagementClient } from '@/components/purchasing'
import { fetchSuppliers } from '@/lib/api/purchasing'
import { getAuthHeaders } from '@/lib/auth'
import { firstQueryValue, readListPagination, type ServerQueryRecord } from '@/lib/list-url-state'

export const dynamic = 'force-dynamic'

function getColumnsFromMeta(meta: Record<string, unknown> | null | undefined) {
  const columns = meta?.columns
  if (!Array.isArray(columns)) return []
  return columns.filter((column): column is string => typeof column === 'string')
}

export default async function SupplierManagementPage({ searchParams }: {
  searchParams: Promise<ServerQueryRecord>
}) {
  const query = await searchParams
  const { page, pageSize } = readListPagination(query)
  const { response, initialLoadFailed } = await fetchSuppliers({
    page,
    page_size: pageSize,
    keyword: firstQueryValue(query.keyword) || undefined,
    supplier_name: firstQueryValue(query.supplier_name) || undefined,
    material_name: firstQueryValue(query.material_name) || undefined,
    purchase_category: firstQueryValue(query.purchase_category) || undefined,
  }, await getAuthHeaders()).then((result) => ({ response: result, initialLoadFailed: false }), () => ({
    response: {
      code: 200,
      message: 'success',
      data: [],
      meta: {
        page,
        page_size: pageSize,
        total: 0,
        columns: [],
      },
    },
    initialLoadFailed: true,
  }))

  const initialTotal = Number(response.meta?.total ?? response.data.length)

  return (
    <SupplierManagementClient
      key={JSON.stringify(query)}
      initialRecords={response.data}
      initialTotal={Number.isFinite(initialTotal) ? initialTotal : response.data.length}
      initialColumns={getColumnsFromMeta(response.meta)}
      initialLoadFailed={initialLoadFailed}
    />
  )
}
