'use client'

import { useState } from 'react'
import { useEquipmentStore } from '@/stores/equipment'
import { SparePart, StockWarning } from '@/types/equipment'
import {
  EquipmentQueryProvider,
  useInvalidateEquipment,
  useSparePartsQuery,
  useStockWarningsQuery,
} from './queries'
import { SparePartTable } from './SparePartTable'
import { SparePartDrawer } from './SparePartDrawer'
import { StockInboundDrawer } from './StockInboundDrawer'
import { StockWarningTable } from './StockWarningTable'

interface SparePartsPageProps {
  workshopCode: string
  initialSpareParts: SparePart[]
  initialSparePartTotal: number
  initialStockWarnings: StockWarning[]
}

function SparePartsPageInner({
  workshopCode,
  initialSpareParts,
  initialSparePartTotal,
  initialStockWarnings,
}: SparePartsPageProps) {
  const sparePartKeyword = useEquipmentStore((s) => s.sparePartKeyword)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const invalidate = useInvalidateEquipment()

  const filters = {
    workshop: workshopCode,
    keyword: sparePartKeyword || undefined,
    page,
    page_size: pageSize,
  }
  const sparePartsQuery = useSparePartsQuery(filters, {
    items: initialSpareParts,
    total: initialSparePartTotal,
    page,
    page_size: pageSize,
  })
  const warningsQuery = useStockWarningsQuery(workshopCode, initialStockWarnings)
  const stockWarnings = warningsQuery.data ?? []

  const refresh = () => {
    invalidate('spareParts')
    invalidate('stockWarnings')
  }

  return (
    <>
      {/* 库存预警：仅存在低于安全库存的备件时展示 */}
      {stockWarnings.length > 0 && (
        <div
          style={{
            background: 'var(--color-canvas)',
            padding: 20,
            borderRadius: 12,
            border: '1px solid var(--color-hairline)',
            marginBottom: 16,
          }}
        >
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--color-ink)', marginBottom: 12 }}>
            库存预警
          </div>
          <StockWarningTable warnings={stockWarnings} loading={warningsQuery.isLoading} />
        </div>
      )}
      <div
        style={{
          background: 'var(--color-canvas)',
          padding: 20,
          borderRadius: 12,
          border: '1px solid var(--color-hairline)',
        }}
      >
        <SparePartTable
          data={sparePartsQuery.data?.items ?? []}
          total={sparePartsQuery.data?.total ?? 0}
          page={page}
          pageSize={pageSize}
          loading={sparePartsQuery.isLoading || sparePartsQuery.isFetching}
          onPageChange={(p, s) => {
            if (s !== pageSize) setPageSize(s)
            setPage(p)
          }}
          onRefresh={refresh}
        />
      </div>

      <SparePartDrawer onRefresh={refresh} workshopCode={workshopCode} />
      <StockInboundDrawer onRefresh={refresh} />
    </>
  )
}

export function SparePartsPage(props: SparePartsPageProps) {
  return (
    <EquipmentQueryProvider>
      <SparePartsPageInner {...props} />
    </EquipmentQueryProvider>
  )
}
