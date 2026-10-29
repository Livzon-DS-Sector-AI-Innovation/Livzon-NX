import { WorkshopNavBlocks, ModuleTabs } from '@/components/equipment'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
import {
  EQUIPMENT_MODULE_TABS,
  EQUIPMENT_PAGE_KEYS,
  isEquipmentModule,
} from '@/lib/equipment-page-permissions'
import AssetsView from './_modules/assets-view'
import MaintenanceView from './_modules/maintenance-view'
import InspectionView from './_modules/inspection-view'
import SparePartsView from './_modules/spare-parts-view'
import PersonnelView from './_modules/personnel-view'

export const dynamic = 'force-dynamic'

// 车间代码格式（与后端 WORKSHOP_QUERY / 车间注册表一致）；车间清单由
// WorkshopNavBlocks 客户端从注册表接口读取，服务端只做格式兜底。
const WORKSHOP_CODE_RE = /^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$/
const DEFAULT_WORKSHOP_CODE = '201-1'

// 设备统一工作台：车间块行 + 功能模块 Tab + 选中模块内容。
// URL 组合 /equipment?workshop=<车间>&module=<模块>（均可分享/刷新保位）；
// ?workshop= 缺省回落 201一车间，?module= 缺省由 ModuleTabs 客户端落到
// 首个有权限的模块；旧 /equipment/<功能> 路径由各自 redirect 存根跳转至此。
export default async function EquipmentConsolePage({
  searchParams,
}: {
  searchParams: Promise<{ workshop?: string; module?: string }>
}) {
  const { workshop, module } = await searchParams
  // 新车间由注册表动态提供，服务端无法枚举：按格式校验放行，
  // 已知车间回填常量显示名（InspectionView 内会再按注册表纠正）
  const known = EQUIPMENT_WORKSHOPS.find((item) => item.code === workshop)
  const workshopCode = known
    ? known.code
    : (workshop && WORKSHOP_CODE_RE.test(workshop)
      ? workshop
      : DEFAULT_WORKSHOP_CODE)
  const workshopLabel = known?.label ?? workshopCode
  const activeModule = isEquipmentModule(module) ? module : undefined

  // 车间块按当前模块的授权车间过滤；模块未定时按台账（首个 Tab）过滤
  const pageKey = activeModule
    ? EQUIPMENT_MODULE_TABS.find((tab) => tab.module === activeModule)?.key
    : EQUIPMENT_PAGE_KEYS.assets

  return (
    <>
      <WorkshopNavBlocks pageKey={pageKey ?? EQUIPMENT_PAGE_KEYS.assets} />
      <ModuleTabs workshop={workshopCode} activeModule={activeModule} />
      {activeModule === 'assets' && <AssetsView workshopCode={workshopCode} />}
      {activeModule === 'maintenance' && <MaintenanceView workshopCode={workshopCode} />}
      {activeModule === 'inspection' && (
        <InspectionView workshopCode={workshopCode} workshopLabel={workshopLabel} />
      )}
      {activeModule === 'spare-parts' && <SparePartsView workshopCode={workshopCode} />}
      {activeModule === 'personnel' && <PersonnelView workshopCode={workshopCode} />}
    </>
  )
}
