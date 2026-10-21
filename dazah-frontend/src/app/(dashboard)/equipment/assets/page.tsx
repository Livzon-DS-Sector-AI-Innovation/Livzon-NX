import { redirect } from 'next/navigation'

// 旧功能页路径收敛到统一工作台：/equipment/assets[?workshop=] → /equipment[?workshop=&module=assets]
export default async function AssetsRedirect({
  searchParams,
}: {
  searchParams: Promise<{ workshop?: string }>
}) {
  const { workshop } = await searchParams
  const query = workshop
    ? `workshop=${encodeURIComponent(workshop)}&module=assets`
    : 'module=assets'
  redirect(`/equipment?${query}`)
}
