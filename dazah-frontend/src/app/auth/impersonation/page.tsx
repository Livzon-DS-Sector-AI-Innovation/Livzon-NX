import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { AntdProvider } from '@/components/AntdProvider'
import { ImpersonationBanner } from '@/components/auth/ImpersonationBanner'
import { IMPERSONATION_COOKIE } from '@/lib/impersonation'

export default async function ImpersonationRecoveryPage() {
  if (!(await cookies()).get(IMPERSONATION_COOKIE)) redirect('/')
  return <AntdProvider>
    <main className="mx-auto max-w-3xl py-8">
      <h1 className="mx-6 mb-4 text-xl font-semibold">模拟登录</h1>
      <ImpersonationBanner />
    </main>
  </AntdProvider>
}
