import { MappedDatasetPage } from '@/components/feishu-data/MappedDatasetPage'

export default function ProductionFeishuDataPage() {
  return (
    <MappedDatasetPage
      moduleCode="production"
      pageKey="production.data"
      title="生产飞书数据"
      description="展示已映射并完成本地镜像同步的生产数据表。"
      enableAdvancedQuery={false}
    />
  )
}
