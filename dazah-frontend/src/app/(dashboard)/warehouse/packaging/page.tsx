import { PackagingTable } from '@/components/warehouse/PackagingTable'
import { fetchPackagingMaterials } from '@/lib/api/server/warehouse'
import type { PackagingMaterial } from '@/types/warehouse'

export const dynamic = 'force-dynamic'

export default async function PackagingPage() {
  let initialItems: PackagingMaterial[] = []

  try {
    initialItems = await fetchPackagingMaterials()
  } catch (error) {
    console.warn('包材库存页面初始数据加载失败，使用空数据降级:', error)
  }

  return (
    <div>
      <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
        包材库存
      </h1>
      <p className="text-[14px] text-[var(--color-steel)] mb-6">
        包材库存实时数据
      </p>
      <PackagingTable initialItems={initialItems} />
    </div>
  )
}
