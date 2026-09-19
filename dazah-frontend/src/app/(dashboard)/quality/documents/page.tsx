import { DocumentCatalogPage, QualityQueryProvider } from '@/components/quality'
import type { DocumentDepartmentItem } from '@/types/quality'
import { fetchDocumentDepartmentsServer } from '@/lib/api/server/quality'

export const dynamic = 'force-dynamic'

export default async function Page() {
  let initialDepartments: DocumentDepartmentItem[] = []
  try {
    initialDepartments = await fetchDocumentDepartmentsServer()
  } catch {
    // 后端不可用时使用空数据初始化，保证页面可打开
  }
  return (
    <QualityQueryProvider>
      <DocumentCatalogPage initialDepartments={initialDepartments} />
    </QualityQueryProvider>
  )
}
