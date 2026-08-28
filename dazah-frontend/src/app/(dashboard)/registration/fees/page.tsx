import { fetchFeeDashboardServer } from '@/lib/api/server/registration'
import { FeeDashboardPage, RegistrationQueryProvider } from '@/components/registration'

export const dynamic = 'force-dynamic'

export default async function FeesDashboardPage() {
  const defaultYearFrom = Number(process.env.REGISTRATION_FEE_DEFAULT_YEAR_FROM) || 2023
  const dashboard = await fetchFeeDashboardServer(defaultYearFrom)

  return (
    <RegistrationQueryProvider>
      <FeeDashboardPage dashboard={dashboard} defaultYearFrom={defaultYearFrom} />
    </RegistrationQueryProvider>
  )
}
