'use client'

import ProductDataView from '@/components/production/ProductDataView'
import { PRODUCTION_PAGE_KEYS } from '@/components/production/useProductionPermissions'

export default function LovastatinPage() {
  return <ProductDataView productName="洛伐他汀" pageKey={PRODUCTION_PAGE_KEYS.overview} />
}
