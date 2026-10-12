import { redirect } from 'next/navigation'

// 台账已按车间拆分路由（/equipment/assets/<车间代码>）；
// 旧入口保留重定向，当前唯一已配置车间为 201一车间。
export default function AssetsPageRedirect() {
  redirect('/equipment/assets/201-1')
}
