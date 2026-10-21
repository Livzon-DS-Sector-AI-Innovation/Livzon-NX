import { PersonnelPage, PersonnelQueryProvider } from '@/components/equipment'

// 人员配置模块：数据在客户端自取
export default function PersonnelView({
  workshopCode,
}: {
  workshopCode: string
}) {
  return (
    <PersonnelQueryProvider>
      <PersonnelPage workshopCode={workshopCode} />
    </PersonnelQueryProvider>
  )
}
