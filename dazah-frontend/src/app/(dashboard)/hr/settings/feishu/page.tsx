import { HrFeishuSettingsPage, HrQueryProvider } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default function HrFeishuSettingsRoutePage() {
  return (
    <HrQueryProvider>
      <HrFeishuSettingsPage />
    </HrQueryProvider>
  )
}
