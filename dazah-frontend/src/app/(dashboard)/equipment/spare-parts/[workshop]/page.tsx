import { notFound, redirect } from 'next/navigation'

import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'

// 旧车间子路径（/equipment/spare-parts/<车间代码>）收敛到统一工作台：
// 重定向到 /equipment?workshop=<车间代码>&module=spare-parts，保持历史链接可用。
export default async function SparePartsWorkshopRedirect({
  params,
}: {
  params: Promise<{ workshop: string }>
}) {
  const { workshop } = await params
  if (!EQUIPMENT_WORKSHOPS.some((item) => item.code === workshop)) notFound()
  redirect(`/equipment?workshop=${encodeURIComponent(workshop)}&module=spare-parts`)
}
