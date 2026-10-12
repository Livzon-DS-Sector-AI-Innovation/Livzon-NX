import { redirect } from 'next/navigation'

// 人员配置已按车间拆分路由（/equipment/personnel/<车间代码>）；
// 旧入口保留重定向，当前唯一已配置车间为 201一车间。
export default function PersonnelPageRedirect() {
  redirect('/equipment/personnel/201-1')
}
