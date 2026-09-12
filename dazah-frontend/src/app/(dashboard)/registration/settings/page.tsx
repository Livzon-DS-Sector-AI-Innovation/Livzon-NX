import { Alert } from 'antd'

import { RegistrationSettingsPage, RegistrationQueryProvider } from '@/components/registration'
import {
  fetchCertificateReminderRecipientsServer,
  fetchCertificateReminderSettingsServer,
} from '@/lib/api/server/registration'
import {
  fetchRegulatoryTrackerNotificationRecipientsServer,
  fetchRegulatoryTrackerNotificationSettingsServer,
} from '@/lib/api/server/regulatoryTracker'
import type {
  CertificateReminderRecipientOption,
  CertificateReminderSetting,
} from '@/types/registration'
import type {
  RegulatoryTrackerNotificationRecipientOption,
  RegulatoryTrackerNotificationSetting,
} from '@/lib/api/client/regulatoryTracker'

export const dynamic = 'force-dynamic'

export default async function RegistrationSettingsPageRoute() {
  let reminderSettings: CertificateReminderSetting
  let reminderRecipients: CertificateReminderRecipientOption[]

  try {
    ;[reminderSettings, reminderRecipients] = await Promise.all([
      fetchCertificateReminderSettingsServer(),
      fetchCertificateReminderRecipientsServer(),
    ])
  } catch (error) {
    return (
      <Alert
        type="error"
        showIcon
        title="注册设置加载失败"
        description={error instanceof Error ? error.message : '注册设置加载失败'}
      />
    )
  }

  // 法规推送配置允许降级，但必须记录错误便于排查（与法规跟踪页策略一致）
  const notificationSettings = await fetchRegulatoryTrackerNotificationSettingsServer().catch(
    (error) => {
      console.error('获取法规跟踪通知设置失败，使用默认值降级:', error)
      return {
        is_enabled: false,
        recent_days: 7,
        recipient_open_id: null,
        recipient_name: null,
        recipient_department: null,
        // schedule_time 语义为"每日推送时刻"（后端固定 10:00），非抓取时刻
        schedule_time: '10:00',
        pending_count: 0,
        header_template: null,
        footer_template: null,
      } satisfies RegulatoryTrackerNotificationSetting
    }
  )
  const notificationRecipients = await fetchRegulatoryTrackerNotificationRecipientsServer().catch(
    (error) => {
      console.error('获取法规跟踪通知接收人失败，使用空列表降级:', error)
      return [] satisfies RegulatoryTrackerNotificationRecipientOption[]
    }
  )

  return (
    <RegistrationQueryProvider>
      <RegistrationSettingsPage
        reminderSettings={reminderSettings}
        reminderRecipients={reminderRecipients}
        notificationSettings={notificationSettings}
        notificationRecipients={notificationRecipients}
      />
    </RegistrationQueryProvider>
  )
}
