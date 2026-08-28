import { DeviationReportRecordPage, QualityQueryProvider } from '@/components/quality'

export default function DeviationRecordsPage() {
  return (
    <QualityQueryProvider>
      <DeviationReportRecordPage />
    </QualityQueryProvider>
  )
}
