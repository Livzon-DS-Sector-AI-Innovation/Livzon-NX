'use client'

import Link from 'next/link'

export const SYSTEM_PERMISSION_PAGES = [
  {
    href: '/system/roles',
    title: '角色管理',
    description: '配置模块读写权限、菜单权限和角色数据范围。',
  },
  {
    href: '/system/user-roles',
    title: '用户角色',
    description: '为用户分配角色和可见部门，查看生效授权。',
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
    description: '模拟账号访问，核对模块权限和数据范围结果。',
  },
] as const

export default function SystemPermissionsPanel() {
  return (
    <section aria-labelledby="system-permissions-title" data-testid="system-permissions-panel">
      <div className="mb-4">
        <h2 id="system-permissions-title" className="m-0 text-lg font-semibold text-[var(--color-charcoal)]">
          权限与数据范围
        </h2>
        <p className="m-0 mt-1 text-sm text-[var(--color-steel)]">
          系统权限页面统一从这里进入；后端仍会对每次读写操作执行最终鉴权。
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {SYSTEM_PERMISSION_PAGES.map((page) => (
          <Link
            key={page.href}
            href={page.href}
            className="rounded-[var(--rounded-md)] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4 transition-colors hover:border-[var(--color-primary)] hover:bg-[var(--color-surface)]"
          >
            <span className="block text-sm font-medium text-[var(--color-charcoal)]">{page.title}</span>
            <span className="mt-1 block text-xs leading-5 text-[var(--color-steel)]">{page.description}</span>
          </Link>
        ))}
      </div>
    </section>
  )
}
