'use client'
import WorkshopDataView from '@/components/production/WorkshopDataView'
import { PRODUCTION_PAGE_KEYS } from '@/components/production/useProductionPermissions'
export default function Page() {
  return <WorkshopDataView workshopName="103车间" pageKey={PRODUCTION_PAGE_KEYS.overview} />
}
