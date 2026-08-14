import { notFound, redirect } from 'next/navigation'
import { getCurrentUser } from '@/actions/auth'
import { ProcurementMaterialSourceSettingsClient } from '@/components/purchasing'
import { fetchMaterialSourceConfig } from '@/lib/api/purchasing'
import { getAuthHeaders } from '@/lib/auth'

export const dynamic = 'force-dynamic'

export default async function ProcurementSettingsPage() {
  const user = await getCurrentUser()
  if (!user) redirect('/login')
  if (user.role !== 'admin') notFound()

  const response = await fetchMaterialSourceConfig(await getAuthHeaders()).catch(() => null)
  const initialLoadFailed = response === null

  return (
    <ProcurementMaterialSourceSettingsClient
      initialConfig={response?.data ?? null}
      initialLoadFailed={initialLoadFailed}
    />
  )
}
