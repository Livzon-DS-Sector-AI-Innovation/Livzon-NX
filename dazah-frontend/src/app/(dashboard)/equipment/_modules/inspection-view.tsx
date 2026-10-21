import { FeishuInspectionPage } from '@/components/equipment/inspection/FeishuInspectionPage'

// 巡检模块：飞书多维表格镜像只读展示，数据在客户端自取
export default function InspectionView({
  workshopCode,
  workshopLabel,
}: {
  workshopCode: string
  workshopLabel: string
}) {
  return <FeishuInspectionPage workshopCode={workshopCode} workshopLabel={workshopLabel} />
}
