import { getSafetyFeishuSettings, getSafetyFeishuWsStatus } from '@/actions/safety'
import { FeishuSettingsPage } from '@/components/safety'

export const dynamic = 'force-dynamic'

export default async function SafetyFeishuSettingsRoutePage() {
  const [settingsRes, wsRes] = await Promise.all([
    getSafetyFeishuSettings(),
    getSafetyFeishuWsStatus(),
  ])

  return (
    <div style={{ padding: '0 0 24px' }}>
      <h2 style={{ marginBottom: 16 }}>飞书设置</h2>
      <FeishuSettingsPage
        initialSettings={settingsRes.data ?? null}
        initialWsStatus={wsRes.data ?? null}
      />
    </div>
  )
}
