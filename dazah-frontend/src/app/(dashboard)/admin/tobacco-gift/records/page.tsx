import { TobaccoGiftApplyButton } from '@/components/administration'
import { MappedDatasetPage } from '@/components/feishu-data'
import { TOBACCO_GIFT_RECORDS_PAGE_KEY } from '@/lib/administration-pages'

export default function TobaccoGiftRecordsPage() {
  return (
    <>
      <div className="mx-auto flex max-w-[1600px] justify-end px-6 pt-7">
        <TobaccoGiftApplyButton />
      </div>
      <MappedDatasetPage
        moduleCode="administration"
        pageKey={TOBACCO_GIFT_RECORDS_PAGE_KEY}
        title="领用记录"
        enableAdvancedQuery={false}
      />
    </>
  )
}
