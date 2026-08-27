import { fetchFeeEntriesServer } from '@/lib/api/server/registration'
import { FeeLedgerPage } from '@/components/registration'

export const dynamic = 'force-dynamic'

interface Props {
  searchParams: Promise<{ year_from?: string }>
}

export default async function FeeLedgerRoutePage({ searchParams }: Props) {
  const params = await searchParams
  const envDefault = Number(process.env.REGISTRATION_FEE_DEFAULT_YEAR_FROM) || 2023
  const defaultYearFrom = Number(params.year_from) || envDefault
  const entries = await fetchFeeEntriesServer(defaultYearFrom)

  return <FeeLedgerPage entries={entries} defaultYearFrom={defaultYearFrom} />
}
