import { redirect } from 'next/navigation'
import { getCurrentUser } from '@/actions/auth'
import { WorkshopNavBlocks } from '@/components/equipment'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
import {
  EQUIPMENT_MODULES,
  EQUIPMENT_PAGE_KEYS,
  firstAccessibleEquipmentModule,
  isEquipmentModule,
} from '@/lib/equipment-page-permissions'
import AssetsView from './_modules/assets-view'
import InspectionView from './_modules/inspection-view'
import RepairView from './_modules/repair-view'

export const dynamic = 'force-dynamic'

// 车间代码格式（与后端 WORKSHOP_QUERY / 车间注册表一致）；车间清单由
// WorkshopNavBlocks 客户端从注册表接口读取，服务端只做格式兜底。
const WORKSHOP_CODE_RE = /^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$/
const DEFAULT_WORKSHOP_CODE = '201-1'

// 设备管理工作台：车间块行 + 左侧菜单选定的功能模块（巡检 / 检修 / 台账）。
// URL 组合 /equipment?workshop=<车间>&module=<模块>；左侧菜单切换模块时
// 沿用当前车间。未带（或带了无效的）模块参数时，落到当前用户首个有权限的模块。
export default async function EquipmentConsolePage({
  searchParams,
}: {
  searchParams: Promise<{ workshop?: string; module?: string }>
}) {
  const { workshop, module } = await searchParams
  const known = EQUIPMENT_WORKSHOPS.find((item) => item.code === workshop)
  const workshopCode = known
    ? known.code
    : workshop && WORKSHOP_CODE_RE.test(workshop)
      ? workshop
      : DEFAULT_WORKSHOP_CODE
  const workshopLabel = known?.label ?? workshopCode

  if (!isEquipmentModule(module)) {
    const user = await getCurrentUser()
    const query = new URLSearchParams({ module: firstAccessibleEquipmentModule(user) })
    if (workshop) query.set('workshop', workshop)
    redirect(`/equipment?${query.toString()}`)
  }
  const pageKey = EQUIPMENT_MODULES.find((item) => item.module === module)?.key

  return (
    <>
      <WorkshopNavBlocks pageKey={pageKey ?? EQUIPMENT_PAGE_KEYS.inspection} />
      {module === 'assets' && <AssetsView workshopCode={workshopCode} />}
      {module === 'inspection' && (
        <InspectionView workshopCode={workshopCode} workshopLabel={workshopLabel} />
      )}
      {module === 'maintenance' && (
        <RepairView workshopCode={workshopCode} workshopLabel={workshopLabel} />
      )}
    </>
  )
}
