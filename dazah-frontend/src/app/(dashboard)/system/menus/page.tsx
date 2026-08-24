import { serverFetchMenus } from "@/lib/api/server/admin"
import { MenuManager } from "@/components/system/MenuManager"

export const dynamic = "force-dynamic"

export default async function MenusPage() {
  const menus = await serverFetchMenus()

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-charcoal)]">菜单管理</h1>
        <p className="text-sm text-[var(--color-stone)] mt-1">
          后台配置全局菜单树（目录 → 菜单 → 按钮），角色经「角色-菜单」绑定获得菜单与按钮权限。
        </p>
      </div>
      <MenuManager initialMenus={menus} />
    </div>
  )
}