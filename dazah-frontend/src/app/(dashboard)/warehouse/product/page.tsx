import { MappedDatasetPage } from '@/components/feishu-data'

export const dynamic = 'force-dynamic'

export default function ProductPage() {
  return (
    <MappedDatasetPage
      pageKey="warehouse.product"
      title="五金"
      description="展示映射到五金页面的飞书数据表完整本地镜像"
    />
  )
}
