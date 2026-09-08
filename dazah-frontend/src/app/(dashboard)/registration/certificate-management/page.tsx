import { Alert, Space } from 'antd'

import { CertificateDashboardPage } from '@/components/registration'
import {
  fetchCertificateReminderRecipientsServer,
  fetchCertificateReminderSettingsServer,
  fetchCertificateWorkbookOverviewServer,
} from '@/lib/api/server/registration'
import type {
  CertificateReminderRecipientOption,
  CertificateReminderSetting,
  CertificateWorkbookOverview,
} from '@/types/registration'

export const dynamic = 'force-dynamic'

export default async function RegistrationCertificateManagementPage() {
  let overview: CertificateWorkbookOverview
  let reminderSettings: CertificateReminderSetting
  let reminderRecipients: CertificateReminderRecipientOption[]

  try {
    ;[overview, reminderSettings, reminderRecipients] = await Promise.all([
      fetchCertificateWorkbookOverviewServer(),
      fetchCertificateReminderSettingsServer(),
      fetchCertificateReminderRecipientsServer(),
    ])
  } catch (error) {
    return (
      <Alert
        type="error"
        showIcon
        title="药政证书台账加载失败"
        description={error instanceof Error ? error.message : '药政证书台账加载失败'}
      />
    )
  }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      {overview.total_records === 0 ? (
        <Alert
          type="info"
          showIcon
          title="暂无药政证书台账数据"
          description="尚未配置药政证书台账，请点击页面右上角「导入药政证书台账」上传 Excel 完成初始化。"
        />
      ) : null}
      <CertificateDashboardPage
        overview={overview}
        reminderSettings={reminderSettings}
        reminderRecipients={reminderRecipients}
      />
    </Space>
  )
}
