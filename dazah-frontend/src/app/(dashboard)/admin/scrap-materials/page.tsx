import { MappedDatasetPage } from '@/components/feishu-data'
import { ADMIN_SCRAP_MATERIALS_PAGE_KEY } from '@/lib/administration-pages'

/** 废旧物资页：放置申请与领用申请两张表绑定同一页面，按页签切换。 */
export default function ScrapMaterialsPage() {
  return (
    <MappedDatasetPage
      moduleCode="administration"
      pageKey={ADMIN_SCRAP_MATERIALS_PAGE_KEY}
      title="废旧物资"
      enableAdvancedQuery={false}
      enablePersonAvatars
    />
  )
}
