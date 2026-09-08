import { QualityQueryProvider, QualitySettingsPage } from '@/components/quality'

export default function QualitySettingsRoutePage() {
  return (
    <QualityQueryProvider>
      <QualitySettingsPage />
    </QualityQueryProvider>
  )
}
