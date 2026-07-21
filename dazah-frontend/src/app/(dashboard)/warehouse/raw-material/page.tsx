import { MappedDatasetPage } from '@/components/feishu-data'

export const dynamic = 'force-dynamic'

export default function RawMaterialPage() {
  return (
    <MappedDatasetPage
      pageKey="warehouse.raw_material"
      title="成品"
      description="展示映射到成品页面的飞书数据表完整本地镜像"
    />
  )
}
