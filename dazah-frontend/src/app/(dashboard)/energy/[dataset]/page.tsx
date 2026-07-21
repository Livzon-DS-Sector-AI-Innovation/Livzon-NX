import { notFound } from 'next/navigation'

import { MappedDatasetPage } from '@/components/feishu-data'
import { getEnergyDataPage } from '@/lib/energy-data-pages'

export const dynamic = 'force-dynamic'

interface EnergyDatasetPageProps {
  params: Promise<{ dataset: string }>
}

export default async function EnergyDatasetPage({ params }: EnergyDatasetPageProps) {
  const { dataset } = await params
  const page = getEnergyDataPage(dataset)
  if (!page) notFound()

  return (
    <MappedDatasetPage
      moduleCode="energy"
      pageKey={page.pageKey}
      title={page.label}
      description="展示发布到当前菜单页面的飞书数据表最后完整本地镜像"
      enableAdvancedQuery={false}
    />
  )
}
