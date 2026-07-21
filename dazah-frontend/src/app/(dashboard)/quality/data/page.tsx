import { MappedDatasetPage } from '@/components/feishu-data/MappedDatasetPage'

export default function QualityFeishuDataPage() {
  return (
    <MappedDatasetPage
      moduleCode="quality"
      pageKey="quality.data"
      title="质量飞书数据"
      description="展示已映射并完成本地镜像同步的质量数据表。"
      enableAdvancedQuery={false}
    />
  )
}
