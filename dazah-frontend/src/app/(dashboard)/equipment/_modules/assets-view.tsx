import { EquipmentPage } from '@/components/equipment'
import {
  fetchCategoryTree,
  fetchLocationTree,
  fetchEquipments,
  fetchEquipmentStatistics,
  fetchDepartments,
} from '@/actions/equipment'
import type {
  DepartmentOption,
  EquipmentCategory,
  Location,
  Equipment,
  EquipmentStatistics,
} from '@/types/equipment'

// 台账模块：各 API 独立 try/catch，避免一个失败拖垮全部数据
const defaultStatistics: EquipmentStatistics = {
  total: 0,
  by_status: {
    '在用': 0,
    '备用': 0,
    '维修中': 0,
    '停用': 0,
    '报废': 0,
  },
  by_category: {},
  by_location: {},
}

export default async function AssetsView({
  workshopCode,
}: {
  workshopCode: string
}) {
  let categories: EquipmentCategory[] = []
  let locations: Location[] = []
  let equipments: Equipment[] = []
  let total = 0
  let statistics = defaultStatistics
  let departments: DepartmentOption[] = []

  try {
    categories = await fetchCategoryTree()
  } catch (error) {
    console.warn('加载分类树失败:', error)
  }
  try {
    locations = await fetchLocationTree()
  } catch (error) {
    console.warn('加载位置树失败:', error)
  }
  try {
    const result = await fetchEquipments({ workshop: workshopCode, page: 1, page_size: 20 })
    equipments = result.items
    total = result.total
  } catch (error) {
    console.warn('加载设备列表失败:', error)
  }
  try {
    statistics = await fetchEquipmentStatistics(workshopCode)
  } catch (error) {
    console.warn('加载设备统计失败:', error)
  }
  try {
    departments = await fetchDepartments()
  } catch (error) {
    console.warn('加载部门列表失败:', error)
  }

  return (
    <EquipmentPage
      workshopCode={workshopCode}
      initialCategories={categories}
      initialLocations={locations}
      initialEquipments={equipments}
      initialTotal={total}
      initialStatistics={statistics}
      initialDepartments={departments}
    />
  )
}
