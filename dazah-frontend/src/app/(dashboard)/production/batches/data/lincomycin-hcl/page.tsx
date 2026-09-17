'use client'

import ProductDataView from '@/components/production/ProductDataView'
import { PRODUCTION_PAGE_KEYS } from '@/components/production/useProductionPermissions'

export default function LincomycinHclPage() {
  return <ProductDataView productName="盐酸林可霉素" pageKey={PRODUCTION_PAGE_KEYS.overview} />
}
