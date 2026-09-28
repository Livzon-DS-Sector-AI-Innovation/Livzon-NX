'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'
import {
  AppstoreOutlined,
  ClockCircleOutlined,
  CodeSandboxOutlined,
  FileTextOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons'
import AgentSkillManagementClient from './AgentSkillManagementClient'
import AuditLogClient from './AuditLogClient'
import FeishuSettingsClient from './FeishuSettingsClient'
import LLMConfigClient from './LLMConfigClient'
import LivzonTaskClient from './LivzonTaskClient'
import SystemPermissionsPanel from './SystemPermissionsPanel'
import type { SystemPermissionsData } from './SystemPermissionsPanel'
import UserManagementClient from './UserManagementClient'

const settingsGroups = [
  {
    label: '账号与权限',
    items: [
      { key: 'users', label: '用户管理', icon: UserOutlined },
      { key: 'permissions', label: '权限管理', icon: SafetyCertificateOutlined },
    ],
  },
  {
    label: '模型与智能助手',
    items: [
      { key: 'llm', label: 'LLM 模型配置', icon: CodeSandboxOutlined },
      { key: 'feishu', label: 'Livzon Agent管理', icon: RobotOutlined },
      { key: 'agent-skills', label: 'Livzon Agent Skill', icon: AppstoreOutlined },
      { key: 'livzon-task', label: 'Livzon Agent Task', icon: FileTextOutlined },
    ],
  },
  {
    label: '审计与追踪',
    items: [{ key: 'audit', label: '审计日志', icon: ClockCircleOutlined }],
  },
] as const

interface SettingsAdminClientProps {
  activeTab: string
  systemPermissions: SystemPermissionsData | null
}

function SettingsSimplePage({ title, description, icon, children }: { title: string; description: string; icon: ReactNode; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="mb-4 flex items-center gap-3">
        <span aria-hidden="true" className="flex size-12 shrink-0 items-center justify-center rounded-[var(--rounded-lg)] border border-[var(--color-hairline-soft)] bg-[var(--color-canvas)] text-xl text-[var(--color-primary)]">{icon}</span>
        <div className="min-w-0">
          <h2 className="m-0 text-xl font-semibold text-[var(--color-ink-deep)]">{title}</h2>
          <p className="m-0 text-sm text-[var(--color-slate)]">{description}</p>
        </div>
      </div>
      <div className="min-w-0 rounded-[var(--rounded-xl)] border border-[var(--color-hairline-soft)] bg-[var(--color-canvas)] p-4 shadow-sm sm:p-5">
        {children}
      </div>
    </div>
  )
}

export default function SettingsAdminClient({ activeTab, systemPermissions }: SettingsAdminClientProps) {
  const selectedTab = settingsGroups.some((group) => group.items.some((item) => item.key === activeTab))
    ? activeTab
    : 'users'

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[1480px] flex-col overflow-hidden rounded-[var(--rounded-md)] border border-[var(--color-hairline)] bg-[var(--color-canvas)] xl:flex-row">
      <aside className="w-full shrink-0 border-b border-[var(--color-hairline)] bg-[var(--color-canvas)] xl:w-56 xl:border-b-0 xl:border-r">
        <div className="mx-3 flex h-14 items-center border-b border-[var(--color-hairline-soft)]">
          <h1 className="m-0 inline-flex items-center gap-2 px-1.5 text-[18px] font-semibold text-[var(--color-ink-deep)]">
            <span aria-hidden="true" className="h-5 w-[3px] rounded-full bg-[var(--color-primary)]" />
            系统设置
          </h1>
        </div>
        <nav aria-label="系统设置导航" className="flex gap-1 overflow-x-auto p-2 xl:block xl:overflow-x-visible">
          {settingsGroups.map((group, groupIndex) => (
            <div key={group.label} className={`flex shrink-0 gap-1 xl:block ${groupIndex > 0 ? 'xl:mt-4 xl:border-t xl:border-[var(--color-hairline-soft)] xl:pt-3' : ''}`}>
              <p className="m-0 hidden px-3 pb-1 text-[11px] font-medium text-[var(--color-steel)] xl:block">{group.label}</p>
              {group.items.map((item) => {
                const Icon = item.icon
                return <Link
                  key={item.key}
                  href={`/settings?tab=${item.key}`}
                  prefetch={false}
                  scroll={false}
                  aria-current={selectedTab === item.key ? 'page' : undefined}
                  className="settings-side-link"
                >
                  <Icon aria-hidden="true" className="shrink-0 text-base" />
                  <span>{item.label}</span>
                </Link>
              })}
            </div>
          ))}
        </nav>
      </aside>
      <section aria-label="设置内容" className="min-w-0 flex-1 bg-[var(--color-surface-soft)] p-4 sm:p-5">
        {selectedTab === 'users' && <SettingsSimplePage title="用户管理" description="管理本地账号与飞书用户的平台角色。" icon={<UserOutlined />}><UserManagementClient /></SettingsSimplePage>}
        {selectedTab === 'permissions' && (systemPermissions
          ? <SystemPermissionsPanel {...systemPermissions} />
          : <p role="status" className="text-sm text-[var(--color-steel)]">正在加载权限设置…</p>)}
        {selectedTab === 'audit' && <AuditLogClient />}
        {selectedTab === 'llm' && <SettingsSimplePage title="LLM 模型配置" description="维护业务模块使用的模型连接与激活状态。" icon={<CodeSandboxOutlined />}><LLMConfigClient embedded /></SettingsSimplePage>}
        {selectedTab === 'feishu' && <FeishuSettingsClient />}
        {selectedTab === 'agent-skills' && <SettingsSimplePage title="Livzon Agent Skill" description="管理助手可使用的 Skill 与触发配置。" icon={<AppstoreOutlined />}><AgentSkillManagementClient /></SettingsSimplePage>}
        {selectedTab === 'livzon-task' && <LivzonTaskClient />}
      </section>
    </div>
  )
}
