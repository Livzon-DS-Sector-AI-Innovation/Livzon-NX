import { redirect } from 'next/navigation'
import { getCurrentUser } from '@/actions/auth'
import { getFirstAuthorizedModulePath, NO_AUTHORIZED_PAGE_PATH } from '@/lib/menu-config'

export default async function NoAccessPage() {
  const user = await getCurrentUser()
  if (!user) redirect('/login')
  const landingPath = getFirstAuthorizedModulePath(user)
  if (landingPath !== NO_AUTHORIZED_PAGE_PATH) redirect(landingPath)

  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--color-surface)] p-6">
      <section className="w-full max-w-xl rounded-[var(--rounded-lg)] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-8 text-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
          账号已登录，暂未分配可访问的业务页面
        </h1>
        <p className="mt-3 text-[14px] leading-6 text-[var(--color-steel)]">
          请联系管理员为你分配模块和页面权限。授权完成后，可重新检查权限进入系统。
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-4">
          <form action="/" method="get">
            <button type="submit" className="rounded-[var(--rounded-sm)] bg-[var(--color-primary)] px-4 py-2 text-[14px] font-medium text-white hover:bg-[var(--color-primary-pressed)]">
              重新检查权限
            </button>
          </form>
          <a href="/auth/logout" className="rounded-[var(--rounded-sm)] border border-[var(--color-hairline)] px-4 py-2 text-[14px] text-[var(--color-charcoal)]">
            退出登录
          </a>
        </div>
      </section>
    </main>
  )
}
