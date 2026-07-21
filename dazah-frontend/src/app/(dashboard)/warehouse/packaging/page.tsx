import { MappedDatasetPage } from '@/components/feishu-data'

export const dynamic = 'force-dynamic'

export default function PackagingPage() {
  return (
    <MappedDatasetPage
      pageKey="warehouse.packaging"
      title="原辅料及包材"
      description="展示映射到原辅料及包材页面的飞书数据表完整本地镜像"
    />
  )
}
