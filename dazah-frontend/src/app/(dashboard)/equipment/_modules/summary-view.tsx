import { RepairSummaryPage } from '@/components/equipment/repair/RepairSummaryPage'

// 检修汇总：跨车间只读聚合，领导视角一屏看全厂（可下钻单车间）。
// 复用「设备检修」授权，不新增权限项；数据在客户端自取。
export default function SummaryView() {
  return <RepairSummaryPage />
}
