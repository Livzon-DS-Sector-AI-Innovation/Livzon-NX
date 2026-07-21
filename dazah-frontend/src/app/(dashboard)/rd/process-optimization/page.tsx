import { ProcessOptimizationPage } from '@/components/rd/process-optimization'
import { fetchOptimizations } from '@/lib/api/rd'
import { ProcessOptimization } from '@/types/rd'

export const dynamic = 'force-dynamic'

export default async function ProcessOptimizationPageWrapper() {
  let optimizations: ProcessOptimization[] = []
  let total = 0

  try {
    const result = await fetchOptimizations({ page: 1, page_size: 20 })
    optimizations = result.items
    total = result.total
  } catch {
    // 后端不可用时使用空数据
  }

  return <ProcessOptimizationPage initialOptimizations={optimizations} initialTotal={total} />
}
