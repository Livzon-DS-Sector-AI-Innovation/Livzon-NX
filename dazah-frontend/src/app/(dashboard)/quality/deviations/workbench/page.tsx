import { DeviationWorkbenchPage, QualityQueryProvider } from '@/components/quality'

export default async function DeviationWorkbenchPageShell({
  searchParams,
}: {
  searchParams: Promise<{ record_id?: string }>
}) {
  const { record_id } = await searchParams
  return (
    <QualityQueryProvider>
      <DeviationWorkbenchPage initialRecordId={record_id || null} />
    </QualityQueryProvider>
  )
}
