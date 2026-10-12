import { redirect } from 'next/navigation'

// 巡检已按车间拆分路由（/equipment/inspection/<车间代码>）；
// 旧入口保留重定向，当前唯一已配置车间为 201一车间。
export default function InspectionPageRedirect() {
  redirect('/equipment/inspection/201-1')
}
