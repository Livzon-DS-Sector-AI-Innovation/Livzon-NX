'use client'

import { useState } from 'react'
import {
  ApartmentOutlined,
  SafetyCertificateOutlined,
  SwapOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type {
  DepartmentItem,
  DeptRuleItem,
  RoleItem,
} from '@/lib/api/server/admin'
import {
  DeptRoleMapper,
  PermissionVerification,
  RoleManager,
  UserRoleManager,
} from '@/components/system'
import SettingsSubnav from './SettingsSubnav'
import SettingsSegmentedNav from './SettingsSegmentedNav'
import ImpersonationPanel from './ImpersonationPanel'
import { IMPERSONATION_SETTINGS_PATH } from '@/lib/impersonation'

export const SYSTEM_PERMISSION_PAGES = [
  {
    href: '/system/roles',
    title: '角色管理',
    description: '配置菜单页面的访问、查询、操作及独立高风险动作。',
  },
  {
    href: '/system/user-roles',
    title: '用户角色',
  },
  {
    href: '/system/dept-roles',
    title: '角色映射',
    description: '搜索用户或按部门查询，为所选用户批量分配角色。',
  },
  {
    href: '/system/permission-verification',
    title: '权限接入检查',
    description: '检查各模块的页面、接口和 Livzon 工具是否完整接入权限体系。',
  },
  {
    href: IMPERSONATION_SETTINGS_PATH,
    title: '模拟登录',
    description: '切换到指定用户，验收页面和操作权限。',
  },
] as const

const permissionSections = [
  { key: 'roles', label: '角色与授权', views: ['/system/roles', '/system/user-roles', '/system/dept-roles'] },
  { key: 'checks', label: '权限检查', views: [IMPERSONATION_SETTINGS_PATH, '/system/permission-verification'] },
] as const

export interface SystemPermissionsData {
  roles: RoleItem[]
  departments: DepartmentItem[]
  deptRules: DeptRuleItem[]
}

interface PermissionTabContentProps {
  description?: string
  children: React.ReactNode
}

function PermissionTabContent({ description, children }: PermissionTabContentProps) {
  return (
    <div className="pt-1">
      {description && <p className="m-0 mb-4 text-sm text-[var(--color-steel)]">{description}</p>}
      {children}
    </div>
  )
}

export default function SystemPermissionsPanel({
  roles,
  departments,
  deptRules,
  initialView,
}: SystemPermissionsData & { initialView?: string }) {
  const [activeKey, setActiveKey] = useState<string>(initialView === 'impersonation'
    ? IMPERSONATION_SETTINGS_PATH : '/system/roles')
  const activeSection = permissionSections.find((item) => item.views.some((key) => key === activeKey)) ?? permissionSections[0]

  return (
    <section aria-labelledby="system-permissions-title" data-testid="system-permissions-panel">
      <div className="mb-5">
        <SettingsSegmentedNav
          ariaLabel="权限管理分类"
          items={permissionSections}
          activeKey={activeSection.key}
          onChange={(key) => setActiveKey(permissionSections.find((item) => item.key === key)?.views[0] ?? permissionSections[0].views[0])}
          panelId="permissions-section-panel"
        />
      </div>
      <div className="mb-4 flex items-center gap-3">
        <span aria-hidden="true" className="flex size-12 shrink-0 items-center justify-center rounded-[var(--rounded-lg)] border border-[var(--color-hairline-soft)] bg-[var(--color-canvas)] text-xl text-[var(--color-primary)]"><SafetyCertificateOutlined /></span>
        <div>
          <h2 id="system-permissions-title" className="m-0 text-xl font-semibold text-[var(--color-ink-deep)]">权限管理</h2>
          <p className="m-0 text-sm text-[var(--color-slate)]">配置角色与授权，并检查权限接入情况。</p>
        </div>
      </div>
      <div id="permissions-section-panel" role="tabpanel" aria-labelledby={`permissions-section-panel-tab-${activeSection.key}`}>
      <SettingsSubnav
        ariaLabel="权限管理子导航"
        activeKey={activeKey}
        onChange={setActiveKey}
        showNav={activeSection.views.length > 1}
        items={[
          {
            key: '/system/roles',
            label: '角色管理',
            icon: <SafetyCertificateOutlined />,
            children: (
              <PermissionTabContent description={SYSTEM_PERMISSION_PAGES[0].description}>
                <RoleManager initialRoles={roles} origin="settings" />
              </PermissionTabContent>
            ),
          },
          {
            key: '/system/user-roles',
            label: '用户角色',
            icon: <UserOutlined />,
            children: (
              <PermissionTabContent>
                <UserRoleManager initialRoles={roles} initialDepartments={departments} />
              </PermissionTabContent>
            ),
          },
          {
            key: '/system/dept-roles',
            label: SYSTEM_PERMISSION_PAGES[2].title,
            icon: <TeamOutlined />,
            children: (
              <PermissionTabContent description={SYSTEM_PERMISSION_PAGES[2].description}>
                <DeptRoleMapper
                  initialRules={deptRules}
                  initialRoles={roles}
                  initialDepartments={departments}
                />
              </PermissionTabContent>
            ),
          },
          {
            key: IMPERSONATION_SETTINGS_PATH,
            label: '模拟登录',
            icon: <SwapOutlined />,
            children: <PermissionTabContent description={SYSTEM_PERMISSION_PAGES[4].description}>
              <ImpersonationPanel roles={roles} />
            </PermissionTabContent>,
          },
          {
            key: '/system/permission-verification',
            label: '权限接入检查',
            icon: <ApartmentOutlined />,
            children: (
              <PermissionTabContent description={SYSTEM_PERMISSION_PAGES[3].description}>
                <PermissionVerification />
              </PermissionTabContent>
            ),
          },
        ].filter((item) => activeSection.views.some((key) => key === item.key))}
      />
      </div>
    </section>
  )
}
