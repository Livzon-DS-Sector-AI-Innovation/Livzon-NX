import { redirect } from 'next/navigation'

// 维护保养已按车间拆分路由（/equipment/maintenance/<车间代码>）；
// 旧入口保留重定向，当前唯一已配置车间为 201一车间。
export default function MaintenancePageRedirect() {
  redirect('/equipment/maintenance/201-1')
}
