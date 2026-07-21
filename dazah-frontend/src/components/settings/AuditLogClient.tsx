'use client'

import { Tabs } from 'antd'
import AgentAuditLogClient from './AgentAuditLogClient'
import GeneralAuditLogClient from './GeneralAuditLogClient'

export default function AuditLogClient() {
  return (
    <Tabs
      defaultActiveKey="livzon-conversations"
      items={[
        {
          key: 'livzon-conversations',
          label: 'Livzon 对话',
          children: <AgentAuditLogClient />,
        },
        {
          key: 'permissions',
          label: '权限与授权',
          children: <GeneralAuditLogClient category="permissions" />,
        },
        {
          key: 'agent-tools',
          label: 'Agent 工具',
          children: <GeneralAuditLogClient category="agent_tools" />,
        },
        {
          key: 'automations',
          label: '自动化',
          children: <GeneralAuditLogClient category="automations" />,
        },
        {
          key: 'feishu',
          label: '飞书交互',
          children: <GeneralAuditLogClient category="feishu" />,
        },
        {
          key: 'business',
          label: '业务操作',
          children: <GeneralAuditLogClient category="business" />,
        },
      ]}
    />
  )
}
