import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { getCurrentUser } from '@/actions/auth'
import { AntdProvider } from '@/components/AntdProvider'
import { ImpersonationBanner } from '@/components/auth/ImpersonationBanner'
import { IMPERSONATION_COOKIE, IMPERSONATION_SETTINGS_RECOVERY_REASON } from '@/lib/impersonation'

export default async function ImpersonationRecoveryPage({ searchParams }: {
  searchParams: Promise<{ reason?: string | string[] }>
}) {
  if (!(await cookies()).get(IMPERSONATION_COOKIE)) redirect('/')

  const fromSettings = (await searchParams).reason === IMPERSONATION_SETTINGS_RECOVERY_REASON
  const user = fromSettings ? await getCurrentUser() : null
  const activeSimulation = user?.impersonation

  return <AntdProvider>
    <main className="mx-auto max-w-[35.5rem] py-8">
      <h1 className="mx-3 mb-2 text-xl font-semibold">模拟登录恢复</h1>
      {activeSimulation && <p className="mx-3 mb-2 text-sm text-slate">当前模拟用户无法访问系统设置。</p>}
      <ImpersonationBanner
        name={activeSimulation ? user.name : undefined}
        expiresAt={activeSimulation?.expires_at}
        showContinue={Boolean(activeSimulation)}
      />
    </main>
  </AntdProvider>
}
