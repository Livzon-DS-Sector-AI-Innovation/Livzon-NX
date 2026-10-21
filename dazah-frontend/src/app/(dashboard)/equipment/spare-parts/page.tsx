import { redirect } from 'next/navigation'

// 旧功能页路径收敛到统一工作台：/equipment/spare-parts[?workshop=] → /equipment[?workshop=&module=spare-parts]
export default async function SparePartsRedirect({
  searchParams,
}: {
  searchParams: Promise<{ workshop?: string }>
}) {
  const { workshop } = await searchParams
  const query = workshop
    ? `workshop=${encodeURIComponent(workshop)}&module=spare-parts`
    : 'module=spare-parts'
  redirect(`/equipment?${query}`)
}
