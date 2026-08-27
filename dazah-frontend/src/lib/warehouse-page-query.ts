import type { WarehouseAdvancedFilter, WarehouseMaterialPageQueryParams } from '@/types/warehouse'

type SearchParamsValue = string | string[] | undefined

export interface WarehousePageProps {
  searchParams: Promise<Record<string, SearchParamsValue>>
}

function pickFirst(value: SearchParamsValue): string | undefined {
  if (Array.isArray(value)) {
    return value[0]
  }
  return value
}

function parseAdvancedFilters(value: string | undefined): WarehouseAdvancedFilter[] | undefined {
  if (!value) {
    return undefined
  }
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : undefined
  } catch {
    return undefined
  }
}

export async function resolveWarehousePageQueryParams(
  searchParams: Promise<Record<string, SearchParamsValue>>
): Promise<WarehouseMaterialPageQueryParams> {
  const params = await searchParams

  return {
    page: Number(pickFirst(params.page) || 1),
    page_size: Number(pickFirst(params.page_size) || 200),
    keyword: pickFirst(params.keyword),
    start_date: pickFirst(params.start_date),
    end_date: pickFirst(params.end_date),
    date_field: pickFirst(params.date_field),
    product: pickFirst(params.product),
    area: pickFirst(params.area),
    quality_status: pickFirst(params.quality_status),
    warning_status: pickFirst(params.warning_status),
    material_category: pickFirst(params.material_category),
    filters: parseAdvancedFilters(pickFirst(params.filters)),
  }
}
