import { MappedDatasetPage } from '@/components/feishu-data'
import { TOBACCO_GIFT_ITEMS_PAGE_KEY } from '@/lib/administration-pages'

export default function TobaccoGiftItemsPage() {
  return (
    <MappedDatasetPage
      moduleCode="administration"
      pageKey={TOBACCO_GIFT_ITEMS_PAGE_KEY}
      title="物品清单"
      enableAdvancedQuery={false}
    />
  )
}
