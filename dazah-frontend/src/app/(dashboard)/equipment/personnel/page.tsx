import { redirect } from 'next/navigation'

// 旧功能页路径收敛到统一工作台：/equipment/personnel[?workshop=] → /equipment[?workshop=&module=personnel]
export default async function PersonnelRedirect({
  searchParams,
}: {
  searchParams: Promise<{ workshop?: string }>
}) {
  const { workshop } = await searchParams
  const query = workshop
    ? `workshop=${encodeURIComponent(workshop)}&module=personnel`
    : 'module=personnel'
  redirect(`/equipment?${query}`)
}
