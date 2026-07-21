import { MappedDatasetPage } from '@/components/feishu-data'

export const dynamic = 'force-dynamic'

export default function EnergyDataPage() {
  return (
    <MappedDatasetPage
      moduleCode="energy"
      pageKey="energy.data"
      title="能源原始数据"
      description="统一展示已启用映射工作表的最后完整本地快照"
      enableAdvancedQuery={false}
    />
  )
}
