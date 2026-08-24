import { QualityFeishuSettingsPage, QualityQueryProvider } from '@/components/quality'

export default function QualityFeishuSettingsRoutePage() {
  return (
    <QualityQueryProvider>
      <QualityFeishuSettingsPage />
    </QualityQueryProvider>
  )
}
