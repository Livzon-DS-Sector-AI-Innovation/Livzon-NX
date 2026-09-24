"use client"

import Link from "next/link"
import { usePathname, useSearchParams } from "next/navigation"
import { Dropdown } from "antd"
import type { ModuleMenu } from "@/lib/menu-config"
import { getSafeListReturnHref } from "@/lib/list-url-state"
import { getNavigationHierarchy } from "./navigationHierarchy"

export function PageNavigation({ modules }: { modules: ModuleMenu[] }) {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const currentModule = modules.find((entry) => pathname === entry.path || pathname.startsWith(`${entry.path}/`))
  if (!currentModule) return null
  const { levels: menuLevels, modulePath } = getNavigationHierarchy(currentModule, pathname)
  const returnTo = getSafeListReturnHref(searchParams.get("returnTo"), pathname)
  const returnPath = returnTo?.split("?")[0]
  const levels = returnTo && !menuLevels.some((level) => level.path?.split("?")[0] === returnPath)
    ? [...menuLevels.slice(0, -1), { label: "列表", path: returnTo }, ...menuLevels.slice(-1)]
    : menuLevels
  if (pathname === modulePath && levels.length === 1) return null

  return (
    <nav aria-label="页面层级" className="mb-4 flex min-h-8 flex-wrap items-center text-[13px] text-[var(--color-steel)]">
      <ol className="flex min-w-0 flex-wrap items-center gap-1" aria-label="当前位置">
        {levels.map((level, index) => <li key={`${index}-${level.label}`} className="inline-flex items-center gap-1">
          {index > 0 && <span aria-hidden="true" className="px-1 text-[var(--color-stone)]">/</span>}
          {level.path && index < levels.length - 1
            ? <Link href={returnTo && level.path.split("?")[0] === returnPath ? returnTo : level.path} className="rounded-[var(--rounded-sm)] hover:text-[var(--color-primary)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]">{level.label}</Link>
            : level.options?.length && index < levels.length - 1
              ? <Dropdown trigger={["click"]} overlayClassName="page-breadcrumb-menu" menu={{ items: level.options.map((option, optionIndex) => ({ key: `${option.path}:${optionIndex}`, label: <Link href={option.path}>{option.label}</Link> })) }}>
                  <button type="button" aria-label={`展开${level.label}菜单`} className="rounded-[var(--rounded-sm)] hover:text-[var(--color-primary)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]">{level.label}</button>
                </Dropdown>
            : <span aria-current={index === levels.length - 1 ? "page" : undefined} className={index === levels.length - 1 ? "font-medium text-[var(--color-charcoal)]" : undefined}>{level.label}</span>}
        </li>)}
      </ol>
    </nav>
  )
}
