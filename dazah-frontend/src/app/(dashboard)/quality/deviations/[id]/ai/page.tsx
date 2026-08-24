import { DeviationAiWorkbenchPage, QualityQueryProvider } from '@/components/quality'

export default function DeviationAiWorkbenchRoute() {
  return (
    <QualityQueryProvider>
      <DeviationAiWorkbenchPage />
    </QualityQueryProvider>
  )
}
