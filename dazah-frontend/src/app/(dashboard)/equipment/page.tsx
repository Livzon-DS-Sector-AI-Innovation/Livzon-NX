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
  const meta = EQUIPMENT_WORKSHOPS.find((item) => item.code === workshop)
    ?? EQUIPMENT_WORKSHOPS.find((item) => item.code === '201-1')!
  const activeModule = isEquipmentModule(module) ? module : undefined

  // 车间块按当前模块的授权车间过滤；模块未定时按台账（首个 Tab）过滤
  const pageKey = activeModule
    ? EQUIPMENT_MODULE_TABS.find((tab) => tab.module === activeModule)?.key
    : EQUIPMENT_PAGE_KEYS.assets

  return (
    // 与生产概览页同一节奏容器：页边距 p-4、模块间距 gap-3（12px），
    // 车间块/模块 Tab/内容区不再各自携带 marginBottom
    <div className="p-4 flex flex-col gap-3">
      <WorkshopNavBlocks pageKey={pageKey ?? EQUIPMENT_PAGE_KEYS.assets} />
      <ModuleTabs workshop={meta.code} activeModule={activeModule} />
      {activeModule === 'assets' && <AssetsView workshopCode={meta.code} />}
      {activeModule === 'maintenance' && <MaintenanceView workshopCode={meta.code} />}
      {activeModule === 'inspection' && (
        <InspectionView workshopCode={meta.code} workshopLabel={meta.label} />
      )}
      {activeModule === 'spare-parts' && <SparePartsView workshopCode={meta.code} />}
      {activeModule === 'personnel' && <PersonnelView workshopCode={meta.code} />}
    </div>
  )
}
