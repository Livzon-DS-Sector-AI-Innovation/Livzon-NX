import { MaterialLibraryClient } from '@/components/purchasing'
import { fetchMaterialCatalog } from '@/lib/api/purchasing'
import { getAuthHeaders } from '@/lib/auth'

export const dynamic = 'force-dynamic'

const DEFAULT_PAGE_SIZE = 20

export default async function MaterialLibraryPage() {
  const response = await fetchMaterialCatalog(
    { page: 1, page_size: DEFAULT_PAGE_SIZE },
    await getAuthHeaders(),
  ).then(
    (data) => ({ data, failed: false }),
    () => ({
      data: {
        code: 200,
        message: 'success',
        data: [],
        meta: {
          page: 1,
          page_size: DEFAULT_PAGE_SIZE,
          total: 0,
          sync_status: 'not_synced',
          sync_error: null,
          sync_phase: 'idle',
          sync_persisted_count: 0,
          last_synced_at: null,
          last_sync_record_count: 0,
        },
      },
      failed: true,
    }),
  )

  return (
    <MaterialLibraryClient
      initialRecords={response.data.data}
      initialMeta={response.data.meta}
      initialLoadFailed={response.failed}
    />
  )
}
