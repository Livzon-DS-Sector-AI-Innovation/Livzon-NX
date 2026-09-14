'use client'

import { useState } from 'react'
import { BellOutlined } from '@ant-design/icons'
import { Space, Tabs, Typography } from 'antd'

import CertificateReminderSettingsCard from '@/components/registration/CertificateReminderSettingsCard'
import RegulationNotificationSettingsCard from '@/components/registration/RegulationNotificationSettingsCard'
import type { CertificateReminderRecipientOption, CertificateReminderSetting } from '@/types/registration'
import type {
  RegulatoryTrackerNotificationRecipientOption,
  RegulatoryTrackerNotificationSetting,
} from '@/lib/api/client/regulatoryTracker'

interface RegistrationSettingsPageProps {
  reminderSettings: CertificateReminderSetting
  reminderRecipients: CertificateReminderRecipientOption[]
  notificationSettings: RegulatoryTrackerNotificationSetting
  notificationRecipients: RegulatoryTrackerNotificationRecipientOption[]
}

export function RegistrationSettingsPage({
  reminderSettings,
  reminderRecipients,
  notificationSettings,
  notificationRecipients,
}: RegistrationSettingsPageProps) {
  const [activeTab, setActiveTab] = useState('notification')

  const tabItems = [
    {
      key: 'notification',
      label: (
        <span>
          <BellOutlined />
          通知设置
        </span>
      ),
      children: (
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          <CertificateReminderSettingsCard
            reminderSettings={reminderSettings}
            reminderRecipients={reminderRecipients}
          />
          <RegulationNotificationSettingsCard
            initialNotificationSettings={notificationSettings}
            notificationRecipients={notificationRecipients}
          />
        </Space>
      ),
      forceRender: true,
    },
  ]

  return (
    <div>
      <Typography.Title level={4} style={{ marginBottom: 4 }}>
        注册设置
      </Typography.Title>
      <Typography.Text type="secondary">
        维护注册管理模块各类通知的开关、接收人与消息模板。
      </Typography.Text>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        size="large"
        style={{ marginTop: 16 }}
      />
    </div>
  )
}

export default RegistrationSettingsPage
