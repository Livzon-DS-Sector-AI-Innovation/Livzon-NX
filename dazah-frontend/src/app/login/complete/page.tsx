import { AuthCompletion } from '@/components/auth/AuthCompletion'

export const dynamic = 'force-dynamic'

function sanitizeNextPath(value: string | string[] | undefined): string {
  const raw = Array.isArray(value) ? value[0] : value
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) {
    return '/production'
  }
  if (
    raw.startsWith('/api/') ||
    raw.startsWith('/auth/') ||
    raw === '/login' ||
    raw.startsWith('/login/')
  ) {
    return '/production'
  }
  return raw
}

interface AuthCompletionPageProps {
  searchParams: Promise<{
    next?: string | string[]
  }>
}

export default async function AuthCompletionPage({
  searchParams,
}: AuthCompletionPageProps) {
  const params = await searchParams
  return <AuthCompletion nextPath={sanitizeNextPath(params.next)} />
}
