import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./UserManagementClient', () => ({ default: () => <div>用户列表内容</div> }))
vi.mock('./SystemPermissionsPanel', () => ({ default: () => <div>权限配置内容</div> }))
vi.mock('./AuditLogClient', () => ({ default: () => <div>审计内容</div> }))
vi.mock('./LLMConfigClient', () => ({ default: () => <div>模型内容</div> }))
vi.mock('./FeishuSettingsClient', () => ({ default: () => <div>Agent 内容</div> }))
vi.mock('./AgentSkillManagementClient', () => ({ default: () => <div>Skill 内容</div> }))
vi.mock('./LivzonTaskClient', () => ({ default: () => <div>Task 内容</div> }))

import SettingsAdminClient from './SettingsAdminClient'

describe('SettingsAdminClient navigation', () => {
  it('groups settings entries and marks the direct URL as current', () => {
    const html = renderToStaticMarkup(<SettingsAdminClient
      activeTab="permissions"
      systemPermissions={{ roles: [], departments: [], deptRules: [] }}
    />)

    expect(html).toContain('账号与权限')
    expect(html).toContain('模型与智能助手')
    expect(html).toContain('审计与追踪')
    expect(html).toContain('<aside class="w-full shrink-0')
    expect(html).toContain('xl:w-56')
    expect(html).toContain('<section aria-label="设置内容"')
    expect(html.indexOf('<aside')).toBeLessThan(html.indexOf('<section aria-label="设置内容"'))
    expect(html).toContain('href="/settings?tab=permissions"')
    expect(html).toMatch(/aria-current="page"[^>]*href="\/settings\?tab=permissions"/)
    expect(html).toContain('权限配置内容')
    expect(html).not.toContain('用户列表内容')
    const sideLinks = html.match(/<a[^>]*class="settings-side-link"[^>]*>.*?<\/a>/g) || []
    expect(sideLinks).toHaveLength(7)
    expect(sideLinks.every((link) => link.includes('aria-hidden="true'))).toBe(true)
  })

  it('uses the user list for an unknown tab', () => {
    const html = renderToStaticMarkup(<SettingsAdminClient activeTab="unknown" systemPermissions={null} />)
    expect(html).toMatch(/<h2[^>]*>用户管理<\/h2>/)
    expect(html).toContain('用户列表内容')
    expect(html).not.toContain('权限配置内容')
  })

  it('shows Livzon Agent Skill and Livzon Agent Task without changing their destinations', () => {
    const html = renderToStaticMarkup(<SettingsAdminClient activeTab="agent-skills" systemPermissions={null} />)
    expect(html).toMatch(/href="\/settings\?tab=agent-skills"[^>]*>.*?Livzon Agent Skill<\/span><\/a>/)
    expect(html).toMatch(/href="\/settings\?tab=livzon-task"[^>]*>.*?Livzon Agent Task<\/span><\/a>/)
    expect(html).toMatch(/<h2[^>]*>Livzon Agent Skill<\/h2>/)
    expect(html).not.toContain('Livzon Skill')
    expect(html).not.toContain('Livzon Task')
  })
})
