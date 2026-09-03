import { QualityQueryProvider } from '@/components/quality'
import { ValidationAiReviewPanel } from '@/components/quality/validation/ValidationAiReviewPanel'

export default function QualityValidationAiReviewPage() {
  return (
    <QualityQueryProvider>
      <ValidationAiReviewPanel />
    </QualityQueryProvider>
  )
}
