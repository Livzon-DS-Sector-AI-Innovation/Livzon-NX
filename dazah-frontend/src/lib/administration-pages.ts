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
export const ADMIN_DORMITORY_PAGE_KEY = 'admin:dormitory'
/** 公告通知为平台原生台账页（非飞书镜像），无数据表绑定。 */
export const ADMIN_NOTICE_PAGE_KEY = 'admin:notice'

/** 领用申请走飞书表单，提交后由 15 分钟定时镜像同步进平台。 */
export const TOBACCO_GIFT_REQUISITION_FORM_URL =
  'https://j0eukrlohu.feishu.cn/share/base/form/shrcnA8obAulQqr4eBxZITZrZKh'

/** 废旧物资放置申请新增表单（页面「放置申请」页签的新增按钮入口）。 */
export const SCRAP_PLACEMENT_FORM_URL =
  'https://j0eukrlohu.feishu.cn/share/base/form/shrcne3A9lKKh5oorYWjQx9pOvh'

/** 废旧物资领用申请新增表单（页面「领用申请」页签的新增按钮入口）。 */
export const SCRAP_REQUISITION_FORM_URL =
  'https://j0eukrlohu.feishu.cn/share/base/form/shrcn0Cr0wTk4Z1AY2c89MlexXb'

/** 新增印章（用章）申请表单（印章管理页「印章台账」页签的新增按钮入口）。 */
export const SEAL_REQUISITION_FORM_URL =
  'https://j0eukrlohu.feishu.cn/share/base/form/shrcnWAFOyeRKftcfnNZ5aAs7s4'
