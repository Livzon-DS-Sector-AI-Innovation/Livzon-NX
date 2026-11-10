import { TobaccoGiftRequisitionCard } from '@/components/administration'
import { MappedDatasetPage } from '@/components/feishu-data'
import { TOBACCO_GIFT_RECORDS_PAGE_KEY } from '@/lib/administration-pages'

export default function TobaccoGiftRecordsPage() {
  return (
    <>
      <div className="mx-auto max-w-[1600px] px-6 pt-7">
        <TobaccoGiftRequisitionCard />
      </div>
      <MappedDatasetPage
        moduleCode="administration"
        pageKey={TOBACCO_GIFT_RECORDS_PAGE_KEY}
        title="领用记录"
        description="烟酒礼品领用单，来自飞书多维表格「领用记录」的本地镜像（每 15 分钟同步）。"
        enableAdvancedQuery={false}
      />
    </>
  )
}
