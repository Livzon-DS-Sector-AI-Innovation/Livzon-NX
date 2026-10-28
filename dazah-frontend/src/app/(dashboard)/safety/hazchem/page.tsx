import {
  getChemicalInventories,
  getHazardousChemicals,
} from '@/actions/safety'
import { HazchemPanel } from '@/components/safety'

export const dynamic = 'force-dynamic'

const PAGE_KEY = 'safety:site-mgmt:hazchem-msds'

export default async function HazchemPage() {
  const [chemicalsRes, inventoriesRes] = await Promise.all([
    getHazardousChemicals({ page_size: 200 }).catch(() => null),
    getChemicalInventories({ page_size: 200 }).catch(() => null),
  ])

  const initialChemicals =
    chemicalsRes && chemicalsRes.code === 200 && chemicalsRes.data
      ? chemicalsRes.data.items
      : []
  const initialInventories =
    inventoriesRes && inventoriesRes.code === 200 && inventoriesRes.data
      ? inventoriesRes.data.items
      : []
  const initialError =
    chemicalsRes && chemicalsRes.code !== 200
      ? chemicalsRes.message || '加载危化品档案失败'
      : null

  return (
    <HazchemPanel
      pageKey={PAGE_KEY}
      initialChemicals={initialChemicals}
      initialInventories={initialInventories}
      initialError={initialError}
    />
  )
}
