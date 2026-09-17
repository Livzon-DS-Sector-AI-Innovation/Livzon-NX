'use client'

import ProductDataView from '@/components/production/ProductDataView'
import { PRODUCTION_PAGE_KEYS } from '@/components/production/useProductionPermissions'

export default function MycophenolicAcidPage() {
  return <ProductDataView productName="霉酚酸" pageKey={PRODUCTION_PAGE_KEYS.overview} />
}
