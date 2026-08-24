import { AuthorizationLetterClient } from '@/components/registration'
import {
  fetchAuthorizationFdaServer,
  fetchAuthorizationLedgerServer,
} from '@/lib/api/server/registration'

export const dynamic = 'force-dynamic'

export default async function AuthorizationLetterPage() {
  const [groupedLedgerResult, fdaResult] = await Promise.all([
    fetchAuthorizationLedgerServer(),
    fetchAuthorizationFdaServer().catch(() => []),
  ])

  return (
    <AuthorizationLetterClient
      initialRecords={groupedLedgerResult.records}
      initialFdaRecords={fdaResult}
    />
  )
}
