import { notFound, redirect } from 'next/navigation'

import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'

// 旧车间子路径（/equipment/assets/<车间代码>）收敛为查询参数：
// 重定向到 /equipment/assets?workshop=<车间代码>，保持历史链接可用。
export default async function AssetsWorkshopRedirect({
  params,
}: {
  params: Promise<{ workshop: string }>
}) {
  const { workshop } = await params
  if (!EQUIPMENT_WORKSHOPS.some((item) => item.code === workshop)) notFound()
  redirect(`/equipment/assets?workshop=${encodeURIComponent(workshop)}`)
}
