import { RepairLedgerPage } from '@/components/equipment/repair/RepairLedgerPage'

// 检修模块：飞书维修记录表镜像只读展示 + 维修频次排行，数据在客户端自取
export default function RepairView({
  workshopCode,
  workshopLabel,
}: {
  workshopCode: string
  workshopLabel: string
}) {
  return <RepairLedgerPage workshopCode={workshopCode} workshopLabel={workshopLabel} />
}
