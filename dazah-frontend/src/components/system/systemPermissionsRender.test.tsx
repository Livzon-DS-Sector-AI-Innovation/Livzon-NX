/* @vitest-environment happy-dom */

import React from 'react'
import { App as AntdApp } from 'antd'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/actions/admin', () => ({
  createDeptRule: vi.fn(),
  createMenu: vi.fn(),
  createRole: vi.fn(),
  deleteDataScope: vi.fn(),
  deleteDeptRule: vi.fn(),
  deleteMenu: vi.fn(),
  deleteRole: vi.fn(),
  exportPermissions: vi.fn(),
  previewUserPermission: vi.fn(),
  removeUserRole: vi.fn(),
  saveRoleDataScope: vi.fn(),
  saveUserDataScope: vi.fn(),
  setRoleMenus: vi.fn(),
  setRolePermissions: vi.fn(),
  simulatePermission: vi.fn(),
  updateMenu: vi.fn(),
  updateRole: vi.fn(),
}))

vi.mock('@/lib/api/client/admin', () => ({
  fetchAdminUsers: vi.fn(async () => ({ items: [] })),
  fetchDataScopes: vi.fn(async () => []),
  fetchRoleMenus: vi.fn(async () => []),
}))

import { DataScopeConfig } from './DataScopeConfig'
import { DeptRoleMapper } from './DeptRoleMapper'
import { MenuManager } from './MenuManager'
import { PermissionVerification } from './PermissionVerification'
import { RoleManager } from './RoleManager'
import { UserRoleManager } from './UserRoleManager'
import SystemPermissionsPanel from '@/components/settings/SystemPermissionsPanel'

const departments = [
  {
    id: 'dept-1',
    feishu_department_id: 'feishu-1',
    name: '质量部',
    parent_feishu_department_id: null,
  },
  {
    id: 'dept-2',
    feishu_department_id: 'feishu-2',
    name: '质量实验室',
    parent_feishu_department_id: 'feishu-1',
  },
]

const roles = [
  {
    id: 'role-1',
    name: '质量管理员',
    code: 'quality-admin',
    description: '质量模块管理员',
    is_system: false,
    permissions: ['quality.read'],
  },
]

const menus = [
  {
    id: 'menu-1',
    key: 'quality',
    parent_id: null,
    name: '质量管理',
    type: 'directory',
    permission_code: null,
    route_path: '/quality',
    component_path: null,
    icon: null,
    sort_order: 1,
    status: 'active',
  },
  {
    id: 'menu-2',
    key: 'quality-capa',
    parent_id: 'menu-1',
    name: 'CAPA',
    type: 'menu',
    permission_code: 'quality.read',
    route_path: '/quality/capas',
    component_path: null,
    icon: null,
    sort_order: 1,
    status: 'active',
  },
]

function renderInApp(element: React.ReactElement): string {
  return renderToStaticMarkup(React.createElement(AntdApp, null, element))
}

describe('system permissions settings pages', () => {
  it('renders the settings entry and all permission management pages with empty and populated data', () => {
    const settingsHtml = renderInApp(React.createElement(SystemPermissionsPanel, {
      roles,
      departments,
      deptRules: [{
        id: 'rule-1',
        role_id: 'role-1',
        role_name: '质量管理员',
        role_code: 'quality-admin',
        feishu_department_id: 'feishu-1',
        department_name: '质量部',
      }],
      menus,
      users: [{
        id: 'user-1',
        name: '测试用户',
        department: '质量部',
        roles,
      }],
    }))
    expect(settingsHtml).toContain('权限管理')
    expect(settingsHtml).not.toContain('数据范围')
    expect(settingsHtml).toContain('角色管理')
    expect(settingsHtml).toContain('用户角色')
    expect(settingsHtml).toContain('部门角色映射')
    expect(settingsHtml).toContain('菜单管理')
    expect(settingsHtml).toContain('权限验证台')
    expect(settingsHtml).toContain('质量管理员')

    const scopeHtml = renderInApp(React.createElement(DataScopeConfig, {
      departments,
      value: { scopeType: 'departments', departmentNames: ['质量部'] },
      onChange: vi.fn(),
    }))
    expect(scopeHtml).not.toContain('指定部门')
    expect(scopeHtml).not.toContain('全部部门')

    const roleHtml = renderInApp(React.createElement(RoleManager, {
      initialRoles: roles,
      initialPermissions: [{ id: 'perm-1', code: 'quality.read', module: 'quality', action: 'read', name: '读取' }],
      initialMenus: menus,
      initialDepartments: departments,
    }))
    expect(roleHtml).toContain('质量管理员')
    expect(roleHtml).toContain('ant-table-scroll-horizontal')
    expect(roleHtml).toContain('ant-table-cell-fix-end')
    expect(roleHtml).toContain('页面权限')
    expect(roleHtml).toContain('编辑信息')
    expect(roleHtml).toContain('ant-btn-dangerous')

    const userRoleHtml = renderInApp(React.createElement(UserRoleManager, {
      initialRoles: roles,
      initialDepartments: departments,
    }))
    expect(userRoleHtml).toContain('按姓名 / 部门搜索')

    const deptRoleHtml = renderInApp(React.createElement(DeptRoleMapper, {
      initialRules: [{
        id: 'rule-1',
        role_id: 'role-1',
        role_name: '质量管理员',
        role_code: 'quality-admin',
        feishu_department_id: 'feishu-1',
        department_name: '质量部',
      }],
      initialRoles: roles,
      initialDepartments: departments,
    }))
    expect(deptRoleHtml).toContain('新增规则')
    expect(deptRoleHtml).toContain('质量部')

    const menuHtml = renderInApp(React.createElement(MenuManager, { initialMenus: menus }))
    expect(menuHtml).toContain('新建菜单')
    expect(menuHtml).toContain('CAPA')

    const verificationHtml = renderInApp(React.createElement(PermissionVerification, {
      users: [{
        id: 'user-1',
        name: '测试用户',
        department: '质量部',
        roles,
      }],
    }))
    expect(verificationHtml).toContain('按页面验证生效权限')
    expect(verificationHtml).toContain('菜单页面')
    expect(verificationHtml).not.toContain('接口路径')
  })
})
