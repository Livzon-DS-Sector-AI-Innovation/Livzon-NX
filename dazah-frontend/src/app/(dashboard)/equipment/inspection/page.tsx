import { redirect } from 'next/navigation'

// 旧路径收敛：/equipment/inspection[?workshop=] → /equipment?workshop=&module=inspection
// （工作台的功能模块由 ?module= 指定）
export default async function InspectionRedirect({
  searchParams,
}: {
  searchParams: Promise<{ workshop?: string }>
}) {
  const { workshop } = await searchParams
  const query = new URLSearchParams({ module: 'inspection' })
  if (workshop) query.set('workshop', workshop)
  redirect(`/equipment?${query.toString()}`)
}
