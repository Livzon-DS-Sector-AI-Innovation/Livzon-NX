import { RegulationTrackerPage, RegistrationQueryProvider } from '@/components/registration'
import {
  fetchRegulatoryTrackerDocumentsServer,
  fetchRegulatoryTrackerNotificationRecipientsServer,
  fetchRegulatoryTrackerNotificationSettingsServer,
} from '@/lib/api/server/regulatoryTracker'

export const dynamic = 'force-dynamic'

export default async function Page() {
  const today = new Date()
  const publishDateTo = today.toISOString().slice(0, 10)
  const publishDateFromDate = new Date(today)
  publishDateFromDate.setDate(today.getDate() - 6)
  const publishDateFrom = publishDateFromDate.toISOString().slice(0, 10)

  const [initialResult, notificationSettings, notificationRecipients] = await Promise.all([
    // 主数据不降级：失败时抛出异常由错误边界展示，避免静默吞错
    fetchRegulatoryTrackerDocumentsServer({
      page: 1,
      pageSize: 20,
      publishDateFrom,
      publishDateTo,
    }),
    // 辅助配置允许降级，但必须记录错误便于排查
    fetchRegulatoryTrackerNotificationSettingsServer().catch((error) => {
      console.error('获取法规跟踪通知设置失败，使用默认值降级:', error)
      return {
        is_enabled: false,
        recent_days: 7,
        recipient_open_id: null,
        recipient_name: null,
        recipient_department: null,
        // schedule_time 语义为"每日推送时刻"（后端固定 10:00），非抓取时刻
        // schedule_time 语义为"每日推送时刻"（后端固定 10:00），非抓取时刻
        schedule_time: '10:00',
        pending_count: 0,
      }
    }),
    fetchRegulatoryTrackerNotificationRecipientsServer().catch((error) => {
      console.error('获取法规跟踪通知接收人失败，使用空列表降级:', error)
      return []
    }),
  ])

  return (
    <RegistrationQueryProvider>
      <RegulationTrackerPage
        initialResult={initialResult}
        initialNotificationSettings={notificationSettings}
        notificationRecipients={notificationRecipients}
      />
    </RegistrationQueryProvider>
  )
}
