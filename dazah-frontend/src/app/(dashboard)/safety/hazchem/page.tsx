import { getHazardousChemicals } from '@/actions/safety'
import { HazchemPanel } from '@/components/safety'

export const dynamic = 'force-dynamic'

const PAGE_KEY = 'safety:site-mgmt:hazchem-msds'

export default async function HazchemPage() {
  const chemicalsRes = await getHazardousChemicals({ page_size: 200 }).catch(
    () => null
  )

  const initialChemicals =
    chemicalsRes && chemicalsRes.code === 200 && chemicalsRes.data
      ? chemicalsRes.data.items
      : []
  const initialError =
    chemicalsRes && chemicalsRes.code !== 200
      ? chemicalsRes.message || '加载危化品档案失败'
      : null

  return (
    <HazchemPanel
      pageKey={PAGE_KEY}
      initialChemicals={initialChemicals}
      initialError={initialError}
    />
  )
}
