'use client'

import { Tabs } from 'antd'
import type {
  AdminUserItem,
  DepartmentItem,
  DeptRuleItem,
  RoleItem,
} from '@/lib/api/server/admin'
import type { MenuFlatItem } from '@/lib/menu-tree'
import {
  DeptRoleMapper,
  PermissionVerification,
  RoleManager,
  UserRoleManager,
} from '@/components/system'
import { MenuManager } from '@/components/system/MenuManager'

export const SYSTEM_PERMISSION_PAGES = [
  {
    href: '/system/roles',
    title: '角色管理',
    description: '配置菜单页面的访问、查询、操作及独立高风险动作。',
  },
  {
    href: '/system/user-roles',
    title: '用户角色',
    description: '为用户分配角色，并设置可进入的一级业务模块。',
  },
  {
    href: '/system/dept-roles',
    title: '部门角色映射',
    description: '维护部门到角色的自动映射规则。',
  },
  {
    href: '/system/menus',
    title: '菜单管理',
    description: '配置目录、菜单和按钮的可见权限。',
  },
  {
    href: '/system/permission-verification',
    title: '权限验证台',
    description: '按用户、页面和业务动作验证授权结果。',
  },
] as const

export interface SystemPermissionsData {
  roles: RoleItem[]
  departments: DepartmentItem[]
  deptRules: DeptRuleItem[]
  menus: MenuFlatItem[]
  users: AdminUserItem[]
}

interface PermissionTabContentProps {
  description: string
  children: React.ReactNode
}

function PermissionTabContent({ description, children }: PermissionTabContentProps) {
  return (
    <div className="pt-1">
      <p className="m-0 mb-4 text-sm text-[var(--color-steel)]">{description}</p>
      {children}
    </div>
  )
}

export default function SystemPermissionsPanel({
  roles,
  departments,
  deptRules,
  menus,
  users,
}: SystemPermissionsData) {
  return (
    <section aria-labelledby="system-permissions-title" data-testid="system-permissions-panel">
      <div className="mb-4">
        <h2 id="system-permissions-title" className="m-0 text-lg font-semibold text-[var(--color-charcoal)]">
          权限管理
        </h2>
        <p className="m-0 mt-1 text-sm text-[var(--color-steel)]">
          系统权限页面统一从这里进入；后端仍会对每次读写操作执行最终鉴权。
        </p>
      </div>
      <Tabs
        defaultActiveKey="/system/roles"
        items={[
          {
            key: '/system/roles',
            label: '角色管理',
            children: (
              <PermissionTabContent description={SYSTEM_PERMISSION_PAGES[0].description}>
                <RoleManager initialRoles={roles} initialDepartments={departments} />
              </PermissionTabContent>
            ),
          },
          {
            key: '/system/user-roles',
            label: '用户角色',
            children: (
              <PermissionTabContent description={SYSTEM_PERMISSION_PAGES[1].description}>
                <UserRoleManager initialRoles={roles} initialDepartments={departments} />
              </PermissionTabContent>
            ),
          },
          {
            key: '/system/dept-roles',
            label: '部门角色映射',
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
            key: '/system/menus',
            label: '菜单管理',
            children: (
              <PermissionTabContent description={SYSTEM_PERMISSION_PAGES[3].description}>
                <MenuManager initialMenus={menus} />
              </PermissionTabContent>
            ),
          },
          {
            key: '/system/permission-verification',
            label: '权限验证台',
            children: (
              <PermissionTabContent description={SYSTEM_PERMISSION_PAGES[4].description}>
                <PermissionVerification users={users} />
              </PermissionTabContent>
            ),
          },
        ]}
      />
    </section>
  )
}
