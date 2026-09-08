'use client'

import { useState } from 'react'
import { BellOutlined, CloudOutlined } from '@ant-design/icons'
import { Tabs, Typography } from 'antd'

import { QualityFeishuSettingsPage } from '@/components/quality/QualityFeishuSettingsPage'
import { QualityNotificationSettingsPanel } from '@/components/quality/QualityNotificationSettingsPanel'

const TAB_ITEMS = [
  {
    key: 'feishu',
    label: (
      <span>
        <CloudOutlined />
        飞书设置
      </span>
    ),
    children: <QualityFeishuSettingsPage embedded />,
    forceRender: true,
  },
  {
    key: 'notification',
    label: (
      <span>
        <BellOutlined />
        通知设置
      </span>
    ),
    children: <QualityNotificationSettingsPanel />,
    forceRender: true,
  },
]

export function QualitySettingsPage() {
  const [activeTab, setActiveTab] = useState('feishu')

  return (
    <div>
      <Typography.Title level={4} style={{ marginBottom: 4 }}>
        质量设置
      </Typography.Title>
      <Typography.Text type="secondary">
        维护质量模块的飞书应用/台账同步配置，以及各类通知的开关与频率。
      </Typography.Text>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={TAB_ITEMS}
        size="large"
        style={{ marginTop: 16 }}
      />
    </div>
  )
}

export default QualitySettingsPage
