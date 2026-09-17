'use client'

import ProductDataView from '@/components/production/ProductDataView'
import { PRODUCTION_PAGE_KEYS } from '@/components/production/useProductionPermissions'

export default function LPhenylalaninePage() {
  return <ProductDataView productName="L-苯丙氨酸" pageKey={PRODUCTION_PAGE_KEYS.overview} />
}
