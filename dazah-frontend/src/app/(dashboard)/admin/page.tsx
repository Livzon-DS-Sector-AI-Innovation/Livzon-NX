import { redirect } from 'next/navigation'

/** 行政管理模块首页：目前唯一功能为烟酒礼品管理，直达其仪表台。 */
export default function AdminPage() {
  redirect('/admin/tobacco-gift')
}
