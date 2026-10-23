import { redirect } from 'next/navigation'

// 旧功能页路径收敛到统一工作台：/equipment/inspection[?workshop=] → /equipment[?workshop=&module=inspection]
export default async function InspectionRedirect({
  searchParams,
}: {
  searchParams: Promise<{ workshop?: string }>
}) {
  const { workshop } = await searchParams
  const query = workshop
    ? `workshop=${encodeURIComponent(workshop)}&module=inspection`
    : 'module=inspection'
  redirect(`/equipment?${query}`)
}
