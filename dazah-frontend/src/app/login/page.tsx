import { redirect } from 'next/navigation'
import { getCurrentUser } from '@/actions/auth'
import { LoginPanel } from '@/components/auth/LoginPanel'
import { getLocalLoginMode } from '@/lib/local-auth'

export const dynamic = 'force-dynamic'

function sanitizeNextPath(value: string | string[] | undefined): string {
  const raw = Array.isArray(value) ? value[0] : value
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) {
    return '/production'
  }
  if (raw.startsWith('/api/') || raw.startsWith('/auth/')) {
    return '/production'
  }
  return raw
}

interface LoginPageProps {
  searchParams: Promise<{
    error?: string | string[]
    next?: string | string[]
  }>
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams
  const nextPath = sanitizeNextPath(params.next)
  const error = Array.isArray(params.error) ? params.error[0] : params.error
  const user = await getCurrentUser()

  if (user) {
    redirect(nextPath)
  }

  return (
    <LoginPanel
      error={error}
      nextPath={nextPath}
      localLoginMode={getLocalLoginMode()}
    />
  )
}
