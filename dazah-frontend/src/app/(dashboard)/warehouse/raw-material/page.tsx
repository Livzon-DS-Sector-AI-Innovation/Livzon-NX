import { RawMaterialTable } from '@/components/warehouse/RawMaterialTable'
import { fetchRawMaterials } from '@/lib/api/server/warehouse'
import type { RawMaterial } from '@/types/warehouse'

export const dynamic = 'force-dynamic'

export default async function RawMaterialPage() {
  let initialItems: RawMaterial[] = []

  try {
    initialItems = await fetchRawMaterials()
  } catch (error) {
    console.warn('原辅料库存页面初始数据加载失败，使用空数据降级:', error)
  }

  return (
    <div>
      <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
        原辅料库存
      </h1>
      <p className="text-[14px] text-[var(--color-steel)] mb-6">
        原辅料库存实时数据
      </p>
      <RawMaterialTable initialItems={initialItems} />
    </div>
  )
}
