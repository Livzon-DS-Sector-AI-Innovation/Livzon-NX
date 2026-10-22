'use client'

/**
 * 设备模块 React Query 查询层。
 * SSR 视图传入 initial* props 时经 initialData 接入，客户端筛选/分页/刷新
 * 全部走 query 缓存；写操作后用 invalidateEquipmentQueries 失效对应域。
 */

import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'

import {
  fetchCategoriesClient,
  fetchDepartmentsClient,
  fetchEquipmentStatisticsClient,
  fetchEquipmentsClient,
  fetchLocationsClient,
  fetchSparePartsClient,
  fetchStockWarningsClient,
} from '@/lib/api/equipment-client'
import type { EquipmentFilters } from '@/types/equipment'

export function EquipmentQueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30 * 1000,
            retry: 1,
          },
        },
      }),
  )

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

export const equipmentQueryKeys = {
  equipments: (filters: EquipmentFilters) =>
    ['equipment', 'equipments', filters] as const,
  statistics: (workshop?: string) =>
    ['equipment', 'statistics', workshop ?? ''] as const,
  categories: () => ['equipment', 'categories'] as const,
  locations: () => ['equipment', 'locations'] as const,
  departments: () => ['equipment', 'departments'] as const,
  spareParts: (filters: { workshop?: string; keyword?: string; page: number; page_size: number }) =>
    ['equipment', 'spare-parts', filters] as const,
  stockWarnings: (workshop?: string) =>
    ['equipment', 'stock-warnings', workshop ?? ''] as const,
}

/** 设备台账列表（筛选 + 分页） */
export function useEquipmentsQuery(
  filters: EquipmentFilters & { page: number; page_size: number },
  initialData?: Awaited<ReturnType<typeof fetchEquipmentsClient>>,
) {
  return useQuery({
    queryKey: equipmentQueryKeys.equipments(filters),
    queryFn: () => fetchEquipmentsClient(filters),
    // SSR 数据为空时视为过期，挂载即客户端补偿拉取
    initialData,
    initialDataUpdatedAt: initialData && initialData.items.length > 0 ? Infinity : 0,
  })
}

export function useEquipmentStatisticsQuery(
  workshop: string | undefined,
  initialData?: Awaited<ReturnType<typeof fetchEquipmentStatisticsClient>>,
) {
  return useQuery({
    queryKey: equipmentQueryKeys.statistics(workshop),
    queryFn: () => fetchEquipmentStatisticsClient(workshop),
    initialData,
    initialDataUpdatedAt: initialData && initialData.total > 0 ? Infinity : 0,
  })
}

export function useCategoriesQuery(
  initialData?: Awaited<ReturnType<typeof fetchCategoriesClient>>,
) {
  return useQuery({
    queryKey: equipmentQueryKeys.categories(),
    queryFn: fetchCategoriesClient,
    initialData,
    initialDataUpdatedAt:
      initialData && initialData.length > 0 ? Infinity : 0,
  })
}

export function useLocationsQuery(
  initialData?: Awaited<ReturnType<typeof fetchLocationsClient>>,
) {
  return useQuery({
    queryKey: equipmentQueryKeys.locations(),
    queryFn: fetchLocationsClient,
    initialData,
    initialDataUpdatedAt:
      initialData && initialData.length > 0 ? Infinity : 0,
  })
}

export function useDepartmentsQuery(
  initialData?: Awaited<ReturnType<typeof fetchDepartmentsClient>>,
) {
  return useQuery({
    queryKey: equipmentQueryKeys.departments(),
    queryFn: fetchDepartmentsClient,
    initialData,
    initialDataUpdatedAt:
      initialData && initialData.length > 0 ? Infinity : 0,
  })
}

/** 备件列表（筛选 + 分页） */
export function useSparePartsQuery(
  filters: { workshop?: string; keyword?: string; page: number; page_size: number },
  initialData?: Awaited<ReturnType<typeof fetchSparePartsClient>>,
) {
  return useQuery({
    queryKey: equipmentQueryKeys.spareParts(filters),
    queryFn: () => fetchSparePartsClient(filters),
    initialData,
    initialDataUpdatedAt: initialData && initialData.items.length > 0 ? Infinity : 0,
  })
}

export function useStockWarningsQuery(
  workshop: string | undefined,
  initialData?: Awaited<ReturnType<typeof fetchStockWarningsClient>>,
) {
  return useQuery({
    queryKey: equipmentQueryKeys.stockWarnings(workshop),
    queryFn: () => fetchStockWarningsClient(workshop),
    initialData,
    initialDataUpdatedAt:
      initialData && initialData.length > 0 ? Infinity : 0,
  })
}

/** 写操作后按域失效查询缓存（scope 省略时刷新设备模块全部查询） */
export function useInvalidateEquipment() {
  const queryClient = useQueryClient()
  return (scope?: 'equipments' | 'statistics' | 'categories' | 'locations' | 'departments' | 'spareParts' | 'stockWarnings') => {
    if (!scope) {
      void queryClient.invalidateQueries({ queryKey: ['equipment'] })
      return
    }
    void queryClient.invalidateQueries({
      queryKey: ['equipment', scope === 'spareParts' ? 'spare-parts' : scope],
    })
  }
}
