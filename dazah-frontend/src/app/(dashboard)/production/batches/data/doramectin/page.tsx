'use client'

import ProductDataView from '@/components/production/ProductDataView'
import { PRODUCTION_PAGE_KEYS } from '@/components/production/useProductionPermissions'

export default function DoramectinPage() {
  return <ProductDataView productName="多拉菌素" pageKey={PRODUCTION_PAGE_KEYS.overview} />
}
