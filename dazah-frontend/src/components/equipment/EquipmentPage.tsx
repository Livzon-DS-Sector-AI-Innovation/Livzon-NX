'use client'

import { useState } from 'react'
import { App, Tabs, Button } from 'antd'
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import {
  EquipmentCategory,
  Location,
  Equipment,
  EquipmentStatistics,
  DepartmentOption,
} from '@/types/equipment'
import { useEquipmentStore } from '@/stores/equipment'
import {
  EquipmentQueryProvider,
  useCategoriesQuery,
  useDepartmentsQuery,
  useEquipmentStatisticsQuery,
  useEquipmentsQuery,
  useInvalidateEquipment,
  useLocationsQuery,
} from './queries'
import { StatsCards } from './StatsCards'
import { EquipmentTable } from './EquipmentTable'
import { CategoryTree } from './CategoryTree'
import { LocationTree } from './LocationTree'
import { EquipmentDrawer } from './EquipmentDrawer'
import { CategoryDrawer } from './CategoryDrawer'
import { LocationDrawer } from './LocationDrawer'
import { RepairDrawer } from './RepairDrawer'

interface EquipmentPageProps {
  workshopCode: string
  initialCategories: EquipmentCategory[]
  initialLocations: Location[]
  initialEquipments: Equipment[]
  initialTotal: number
  initialStatistics: EquipmentStatistics
  initialDepartments: DepartmentOption[]
}

const SIDEBAR_WIDTH = 280

function EquipmentPageInner({
  workshopCode,
  initialCategories,
  initialLocations,
  initialEquipments,
  initialTotal,
  initialStatistics,
  initialDepartments,
}: EquipmentPageProps) {
  const failureCodes = useEquipmentStore((s) => s.failureCodes)
  const selectedCategory = useEquipmentStore((s) => s.selectedCategory)
  const selectedLocation = useEquipmentStore((s) => s.selectedLocation)
  const statusFilter = useEquipmentStore((s) => s.statusFilter)
  const departmentFilter = useEquipmentStore((s) => s.departmentFilter)
  const keyword = useEquipmentStore((s) => s.keyword)
  const setSelectedCategory = useEquipmentStore((s) => s.setSelectedCategory)
  const setSelectedLocation = useEquipmentStore((s) => s.setSelectedLocation)

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const invalidate = useInvalidateEquipment()

  // 筛选变化时回到第一页（渲染期调整，避免级联 effect）
  const filterKey = JSON.stringify([
    selectedCategory,
    selectedLocation,
    departmentFilter,
    statusFilter,
    keyword,
  ])
  const [lastFilterKey, setLastFilterKey] = useState(filterKey)
  if (filterKey !== lastFilterKey) {
    setLastFilterKey(filterKey)
    setPage(1)
  }

  const filters = {
    workshop: workshopCode,
    category_id: selectedCategory ?? undefined,
    location_id: selectedLocation ?? undefined,
    department_id: departmentFilter ?? undefined,
    status: statusFilter || undefined,
    keyword: keyword || undefined,
    page,
    page_size: pageSize,
  }
  const equipmentsQuery = useEquipmentsQuery(filters, {
    items: initialEquipments,
    total: initialTotal,
    page,
    page_size: pageSize,
  })
  const statisticsQuery = useEquipmentStatisticsQuery(
    workshopCode,
    initialStatistics,
  )
  const categoriesQuery = useCategoriesQuery(initialCategories)
  const locationsQuery = useLocationsQuery(initialLocations)
  const departmentsQuery = useDepartmentsQuery(initialDepartments)

  const equipments = equipmentsQuery.data?.items ?? []
  const statistics = statisticsQuery.data ?? initialStatistics
  const categories = categoriesQuery.data ?? []
  const locations = locationsQuery.data ?? []
  const departments = departmentsQuery.data ?? []

  const refreshEquipments = () => {
    invalidate('equipments')
    invalidate('statistics')
  }
  const refreshCategoriesAndLocations = () => {
    invalidate('categories')
    invalidate('locations')
  }

  const tabItems = [
    {
      key: 'category',
      label: '分类',
      children: (
        <CategoryTree
          categories={categories}
          onRefresh={refreshCategoriesAndLocations}
        />
      ),
    },
    {
      key: 'location',
      label: '位置',
      children: (
        <LocationTree
          locations={locations}
          onRefresh={refreshCategoriesAndLocations}
        />
      ),
    },
  ]

  const tabBarExtra =
    selectedCategory || selectedLocation ? (
      <Button
        type="text"
        size="small"
        onClick={() => {
          setSelectedCategory(null)
          setSelectedLocation(null)
        }}
        style={{ color: 'var(--color-stone)', marginRight: 4 }}
      >
        重置
      </Button>
    ) : null

  return (
    <>
      <div
        className="flex gap-4"
        style={{ height: 'calc(100vh - 210px)', minHeight: 400 }}
      >
        {/* 左侧：可折叠分类/位置树 */}
        {!sidebarCollapsed && (
          <div
            className="shrink-0"
            style={{
              width: SIDEBAR_WIDTH,
              background: 'var(--color-canvas)',
              padding: 16,
              borderRadius: 12,
              border: '1px solid var(--color-hairline)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
              <Tabs items={tabItems} tabBarExtraContent={tabBarExtra} />
            </div>
          </div>
        )}

        {/* 右侧：设备列表 */}
        <div
          className="flex-1 min-w-0"
          style={{
            background: 'var(--color-canvas)',
            padding: '16px 20px',
            borderRadius: 12,
            border: '1px solid var(--color-hairline)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* 折叠按钮 + 统计 + 标题 */}
          <div className="mb-3 flex items-center gap-3" style={{ flexShrink: 0 }}>
            <Button
              type="text"
              icon={
                sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />
              }
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              style={{ color: 'var(--color-slate)', flexShrink: 0 }}
            />
            <StatsCards statistics={statistics} compact />
          </div>

          {/* 表格区域 */}
          <div style={{ flex: 1, overflow: 'hidden', minHeight: 0 }}>
            <EquipmentTable
              data={equipments}
              total={equipmentsQuery.data?.total ?? 0}
              page={page}
              pageSize={pageSize}
              departments={departments}
              loading={equipmentsQuery.isLoading || equipmentsQuery.isFetching}
              onPageChange={(p, s) => {
                if (s !== pageSize) setPageSize(s)
                setPage(p)
              }}
              workshopCode={workshopCode}
            />
          </div>
        </div>
      </div>

      {/* 抽屉组件 */}
      <EquipmentDrawer
        workshopCode={workshopCode}
        onRefresh={refreshEquipments}
      />
      <CategoryDrawer onRefresh={refreshCategoriesAndLocations} />
      <LocationDrawer onRefresh={refreshCategoriesAndLocations} />
      <RepairDrawer
        equipments={equipments.map((e) => ({
          id: e.id,
          equipment_no: e.equipment_no,
          name: e.name,
          importance: e.importance,
        }))}
        symptoms={failureCodes.symptoms}
        onRefresh={refreshEquipments}
      />
    </>
  )
}

export function EquipmentPage(props: EquipmentPageProps) {
  return (
    <EquipmentQueryProvider>
      <App>
        <EquipmentPageInner {...props} />
      </App>
    </EquipmentQueryProvider>
  )
}
