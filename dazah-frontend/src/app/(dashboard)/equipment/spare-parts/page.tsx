import { redirect } from 'next/navigation'

// 备件已按车间拆分路由（/equipment/spare-parts/<车间代码>）；
// 旧入口保留重定向，当前唯一已配置车间为 201一车间。
export default function SparePartsPageRedirect() {
  redirect('/equipment/spare-parts/201-1')
}
