import { ChangeDetail, QualityQueryProvider } from '@/components/quality'

export default function QualityChangeDetailPage() {
  return (
    <QualityQueryProvider>
      <ChangeDetail />
    </QualityQueryProvider>
  )
}
