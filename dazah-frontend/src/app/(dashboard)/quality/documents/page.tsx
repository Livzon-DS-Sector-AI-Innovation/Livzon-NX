import { DocumentCatalogPage, QualityQueryProvider } from '@/components/quality'
import type { DocumentDepartmentItem } from '@/types/quality'
import { fetchDocumentDepartmentsServer } from '@/lib/api/server/quality'

export const dynamic = 'force-dynamic'

export default async function Page() {
  const initialDepartments: DocumentDepartmentItem[] = await fetchDocumentDepartmentsServer()
  return (
    <QualityQueryProvider>
      <DocumentCatalogPage initialDepartments={initialDepartments} />
    </QualityQueryProvider>
  )
}
