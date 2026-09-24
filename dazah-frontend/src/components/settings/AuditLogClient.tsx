'use client'

import { Tabs } from 'antd'
import AgentAuditLogClient from './AgentAuditLogClient'
import AutomationAuditFactsClient from './AutomationAuditFactsClient'
import GeneralAuditLogClient from './GeneralAuditLogClient'

export default function AuditLogClient() {
  return (
    <Tabs
      defaultActiveKey="operations"
      items={[
        {
          key: 'operations',
          label: '用户操作',
          children: <GeneralAuditLogClient category="operations" />,
        },
        {
          key: 'permissions',
          label: '权限与授权',
          children: <GeneralAuditLogClient category="permissions" />,
        },
        {
          key: 'livzon',
          label: 'Livzon助手',
          children: <Tabs defaultActiveKey="conversations" items={[
            { key: 'conversations', label: '对话', children: <AgentAuditLogClient /> },
            { key: 'tools', label: '工具执行', children: <GeneralAuditLogClient category="agent_tools" /> },
            { key: 'automations', label: '自动化版本与运行', children: <AutomationAuditFactsClient /> },
            { key: 'automation-access', label: '自动化访问记录', children: <GeneralAuditLogClient category="automations" /> },
          ]} />,
        },
        {
          key: 'business',
          label: '业务与外部交互',
          children: <Tabs defaultActiveKey="changes" items={[
            { key: 'changes', label: '业务与平台记录', children: <GeneralAuditLogClient category="business" /> },
            { key: 'feishu', label: '飞书交互', children: <GeneralAuditLogClient category="feishu" /> },
          ]} />,
        },
      ]}
    />
  )
}
