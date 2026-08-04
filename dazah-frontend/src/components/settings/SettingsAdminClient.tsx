'use client'

import { Tabs } from 'antd'
import AgentSkillManagementClient from './AgentSkillManagementClient'
import AuditLogClient from './AuditLogClient'
import FeishuSettingsClient from './FeishuSettingsClient'
import LLMConfigClient from './LLMConfigClient'
import LivzonTaskClient from './LivzonTaskClient'
import UserManagementClient from './UserManagementClient'

export default function SettingsAdminClient() {
  return (
    <div className="mx-auto max-w-[1320px] px-6 py-6">
      <div className="mb-5">
        <h1 className="m-0 text-[24px] font-semibold text-[var(--color-charcoal)]">
          系统设置
        </h1>
        <p className="m-0 mt-1 text-[13px] text-[var(--color-steel)]">
          管理平台用户、角色权限、模型配置、Livzon Agent 治理、Task、Skill 与操作审计。
        </p>
      </div>
      <Tabs
        defaultActiveKey="users"
        items={[
          {
            key: 'users',
            label: '用户管理',
            children: <UserManagementClient />,
          },
          {
            key: 'audit',
            label: '审计日志',
            children: <AuditLogClient />,
          },
          {
            key: 'llm',
            label: 'LLM 模型配置',
            children: <LLMConfigClient embedded />,
          },
          {
            key: 'feishu',
            label: 'Livzon Agent管理',
            children: <FeishuSettingsClient />,
          },
          {
            key: 'agent-skills',
            label: 'Livzon Skill',
            children: <AgentSkillManagementClient />,
          },
          {
            key: 'livzon-task',
            label: 'Livzon Task',
            children: <LivzonTaskClient />,
          },
        ]}
      />
    </div>
  )
}
