import { notFound, redirect } from 'next/navigation'

// 车间代码格式与注册表一致；新车间由注册表动态提供，按格式放行重定向
const WORKSHOP_CODE_RE = /^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$/

// 旧车间子路径（/equipment/personnel/<车间代码>）收敛到统一工作台：
// 重定向到 /equipment?workshop=<车间代码>&module=personnel，保持历史链接可用。
export default async function PersonnelWorkshopRedirect({
  params,
}: {
  params: Promise<{ workshop: string }>
}) {
  const { workshop } = await params
  if (!WORKSHOP_CODE_RE.test(workshop)) notFound()
  redirect(`/equipment?workshop=${encodeURIComponent(workshop)}&module=personnel`)
}
