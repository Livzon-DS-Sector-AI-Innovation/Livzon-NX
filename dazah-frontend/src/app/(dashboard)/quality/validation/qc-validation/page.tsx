import { QcValidationPage, QualityQueryProvider } from '@/components/quality'

export default function QualityQcValidationSubPage() {
  return (
    <QualityQueryProvider>
      <QcValidationPage />
    </QualityQueryProvider>
  )
}