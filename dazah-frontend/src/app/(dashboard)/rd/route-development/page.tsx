import { RouteDevelopmentPage } from '@/components/rd/route-development'
import { fetchRoutes } from '@/actions/rd'
import { RouteDevelopment } from '@/types/rd'

export const dynamic = 'force-dynamic'

export default async function RouteDevelopmentPageWrapper() {
  let routes: RouteDevelopment[] = []
  let total = 0

  try {
    const result = await fetchRoutes({ page: 1, page_size: 20 })
    routes = result.items
    total = result.total
  } catch {
    // 后端不可用时使用空数据，不输出错误日志
  }

  return <RouteDevelopmentPage initialRoutes={routes} initialTotal={total} />
}
