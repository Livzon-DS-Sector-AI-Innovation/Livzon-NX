import { redirect } from 'next/navigation'

// 旧功能页路径收敛到统一工作台：/equipment/maintenance[?workshop=] → /equipment[?workshop=&module=maintenance]
export default async function MaintenanceRedirect({
  searchParams,
}: {
  searchParams: Promise<{ workshop?: string }>
}) {
  const { workshop } = await searchParams
  const query = workshop
    ? `workshop=${encodeURIComponent(workshop)}&module=maintenance`
    : 'module=maintenance'
  redirect(`/equipment?${query}`)
}
