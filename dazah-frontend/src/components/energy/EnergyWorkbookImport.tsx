'use client'

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Skeleton } from 'antd'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { ledgerRequest, type Meter } from '@/lib/api/energy-ledger'
import { EnergyImportClient } from './EnergyImportClient'

export function EnergyWorkbookImport({ year }: { year: number }) {
  const client = useQueryClient()
  // Imports retain settings authorization even when opened from the ledger.
  const init = { headers: { 'X-Dazah-Page-Path': '/energy/settings' } }
  const meters = useQuery({ queryKey: ['energy-ledger', 'import-meters'], queryFn: () => ledgerRequest<Meter[]>('/input-fields', init) })
  const error = meters.error
  if (error) return <PlatformNotice type="error" title={error.message} action={<Button onClick={() => { void meters.refetch() }}>重试</Button>} />
  if (meters.isPending) return <Skeleton active />
  return <EnergyImportClient initialYear={year} meters={meters.data} onChanged={() => client.invalidateQueries({ queryKey: ['energy-ledger'] })} />
}
