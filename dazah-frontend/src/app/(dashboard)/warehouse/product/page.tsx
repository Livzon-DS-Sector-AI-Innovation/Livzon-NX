import { ProductTable } from '@/components/warehouse/ProductTable'
import { fetchProducts } from '@/lib/api/server/warehouse'
import type { ProductInventory } from '@/types/warehouse'

export const dynamic = 'force-dynamic'

export default async function ProductPage() {
  let initialItems: ProductInventory[] = []

  try {
    initialItems = await fetchProducts()
  } catch (error) {
    console.warn('成品库存页面初始数据加载失败，使用空数据降级:', error)
  }

  return (
    <div>
      <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
        成品库存
      </h1>
      <p className="text-[14px] text-[var(--color-steel)] mb-6">
        成品库存实时数据
      </p>
      <ProductTable initialItems={initialItems} />
    </div>
  )
}
