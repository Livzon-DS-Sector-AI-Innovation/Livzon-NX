import { notFound } from 'next/navigation'

import { PersonnelPage, PersonnelQueryProvider } from '@/components/equipment'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'

// 人员配置按车间隔离：/equipment/personnel/<车间代码>
export default async function Page({
  params,
}: {
  params: Promise<{ workshop: string }>
}) {
  const { workshop } = await params
  const meta = EQUIPMENT_WORKSHOPS.find((item) => item.code === workshop)
  if (!meta) notFound()

  return (
    <PersonnelQueryProvider>
      <PersonnelPage workshopCode={meta.code} workshopLabel={meta.label} />
    </PersonnelQueryProvider>
  )
}
