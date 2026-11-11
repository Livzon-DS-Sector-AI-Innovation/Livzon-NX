import { MappedDatasetPage } from '@/components/feishu-data'
import { TOBACCO_GIFT_ITEMS_PAGE_KEY } from '@/lib/administration-pages'

export default function TobaccoGiftItemsPage() {
  return (
    <MappedDatasetPage
      moduleCode="administration"
      pageKey={TOBACCO_GIFT_ITEMS_PAGE_KEY}
      title="物品清单"
      description="烟酒礼品库存物品，来自飞书多维表格「物品清单」的本地镜像（每 15 分钟同步）。"
      enableAdvancedQuery={false}
    />
  )
}
