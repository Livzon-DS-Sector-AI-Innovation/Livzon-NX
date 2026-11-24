import { MappedDatasetPage } from '@/components/feishu-data'
import {
  ADMIN_SCRAP_MATERIALS_PAGE_KEY,
  SCRAP_PLACEMENT_FORM_URL,
  SCRAP_REQUISITION_FORM_URL,
} from '@/lib/administration-pages'

/** 废旧物资页：放置申请与领用申请两张表绑定同一页面，按页签切换；
 * 新增按钮按激活页签跳对应飞书表单。 */
export default function ScrapMaterialsPage() {
  return (
    <MappedDatasetPage
      moduleCode="administration"
      pageKey={ADMIN_SCRAP_MATERIALS_PAGE_KEY}
      title="废旧物资"
      enableAdvancedQuery
      enablePersonAvatars
      enableExport
      createForms={[
        {
          tabLabel: '放置申请',
          label: '新增放置申请',
          url: SCRAP_PLACEMENT_FORM_URL,
        },
        {
          tabLabel: '领用申请',
          label: '新增领用申请',
          url: SCRAP_REQUISITION_FORM_URL,
        },
      ]}
    />
  )
}
