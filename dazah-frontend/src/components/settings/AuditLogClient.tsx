'use client'

import { useState } from 'react'
import {
  AuditOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  MessageOutlined,
  SafetyCertificateOutlined,
  ToolOutlined,
  UserOutlined,
} from '@ant-design/icons'
import AgentAuditLogClient from './AgentAuditLogClient'
import AutomationAuditFactsClient from './AutomationAuditFactsClient'
import GeneralAuditLogClient from './GeneralAuditLogClient'
import SettingsSegmentedNav from './SettingsSegmentedNav'
import SettingsSubnav from './SettingsSubnav'

const auditGroups = [
  {
    key: 'operations', label: '用户操作', description: '查看平台用户的操作记录与处理结果。', icon: UserOutlined,
    views: [{ key: 'operations', label: '用户操作', icon: UserOutlined }],
  },
  {
    key: 'permissions', label: '权限与授权', description: '追踪权限变更及授权操作。', icon: SafetyCertificateOutlined,
    views: [{ key: 'permissions', label: '权限与授权', icon: SafetyCertificateOutlined }],
  },
  {
    key: 'livzon', label: 'Livzon助手', description: '查看助手对话、工具调用与自动化运行记录。', icon: MessageOutlined,
    views: [
      { key: 'conversations', label: '对话', icon: MessageOutlined },
      { key: 'tools', label: '工具执行', icon: ToolOutlined },
      { key: 'automations', label: '自动化版本与运行', icon: ClockCircleOutlined },
      { key: 'automation-access', label: '自动化访问记录', icon: FileTextOutlined },
    ],
  },
  {
    key: 'business', label: '业务与外部交互', description: '核查业务操作和外部平台交互记录。', icon: AuditOutlined,
    views: [
      { key: 'changes', label: '业务与平台记录', icon: FileTextOutlined },
      { key: 'feishu', label: '飞书交互', icon: MessageOutlined },
    ],
  },
] as const

type AuditGroupKey = (typeof auditGroups)[number]['key']
type AuditViewKey = (typeof auditGroups)[number]['views'][number]['key']

function auditView(key: AuditViewKey) {
  switch (key) {
    case 'operations': return <GeneralAuditLogClient category="operations" />
    case 'permissions': return <GeneralAuditLogClient category="permissions" />
    case 'conversations': return <AgentAuditLogClient />
    case 'tools': return <GeneralAuditLogClient category="agent_tools" />
    case 'automations': return <AutomationAuditFactsClient />
    case 'automation-access': return <GeneralAuditLogClient category="automations" />
    case 'changes': return <GeneralAuditLogClient category="business" />
    case 'feishu': return <GeneralAuditLogClient category="feishu" />
  }
}

export default function AuditLogClient() {
  const [activeGroup, setActiveGroup] = useState<AuditGroupKey>('operations')
  const [activeView, setActiveView] = useState<AuditViewKey>('operations')
  const group = auditGroups.find((item) => item.key === activeGroup) ?? auditGroups[0]
  const selectedView = group.views.find((item) => item.key === activeView) ?? group.views[0]
  const GroupIcon = group.icon

  const selectGroup = (key: AuditGroupKey) => {
    const nextGroup = auditGroups.find((item) => item.key === key) ?? auditGroups[0]
    setActiveGroup(key)
    setActiveView(nextGroup.views[0].key)
  }

  return (
    <div className="min-w-0 space-y-5">
      <SettingsSegmentedNav ariaLabel="审计分类" items={auditGroups} activeKey={activeGroup} onChange={(key) => selectGroup(auditGroups.find((item) => item.key === key)?.key ?? auditGroups[0].key)} panelId="audit-group-panel" />

      <div id="audit-group-panel" role="tabpanel" aria-labelledby={`audit-group-panel-tab-${activeGroup}`} className="min-w-0 space-y-4">
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className="flex size-12 shrink-0 items-center justify-center rounded-[var(--rounded-lg)] border border-[var(--color-hairline-soft)] bg-[var(--color-surface-soft)] text-xl text-[var(--color-primary)]">
            <GroupIcon />
          </span>
          <div className="min-w-0">
            <h2 className="m-0 text-xl font-semibold text-[var(--color-ink-deep)]">{group.label}</h2>
            <p className="m-0 text-sm text-[var(--color-slate)]">{group.description}</p>
          </div>
        </div>

        <SettingsSubnav
          ariaLabel={`${group.label}子导航`}
          activeKey={selectedView.key}
          onChange={(key) => setActiveView(group.views.find((item) => item.key === key)?.key ?? group.views[0].key)}
          showNav={group.views.length > 1}
          items={group.views.map((item) => {
            const ViewIcon = item.icon
            return { key: item.key, label: item.label, icon: <ViewIcon />, children: auditView(item.key) }
          })}
        />
      </div>
    </div>
  )
}
