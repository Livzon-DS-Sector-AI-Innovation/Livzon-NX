/**
 * 行政管理 · 镜像页面的页面常量与飞书表单入口。
 *
 * 页面 key 必须与后端 page_policy / page_permission_lifecycle 登记一致。
 */

export const TOBACCO_GIFT_DASHBOARD_PAGE_KEY = 'admin:tobacco-gift:dashboard'
export const TOBACCO_GIFT_ITEMS_PAGE_KEY = 'admin:tobacco-gift:items'
export const TOBACCO_GIFT_RECORDS_PAGE_KEY = 'admin:tobacco-gift:records'

export const ADMIN_SEALS_PAGE_KEY = 'admin:seals'
export const ADMIN_SCRAP_MATERIALS_PAGE_KEY = 'admin:scrap-materials'

/** 领用申请走飞书表单，提交后由 15 分钟定时镜像同步进平台。 */
export const TOBACCO_GIFT_REQUISITION_FORM_URL =
  'https://j0eukrlohu.feishu.cn/share/base/form/shrcnA8obAulQqr4eBxZITZrZKh'
