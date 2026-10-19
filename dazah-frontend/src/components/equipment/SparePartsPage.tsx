'use client'

import { useEffect, useCallback } from 'react'
import { App, ConfigProvider, Button, Spin } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { PlusOutlined } from '@ant-design/icons'
import { SparePart, StockWarning } from '@/types/equipment'
import { useEquipmentStore } from '@/stores/equipment'
import { fetchSparePartsClient, fetchStockWarningsClient } from '@/lib/api/equipment-client'
import { SparePartTable } from './SparePartTable'
import { SparePartDrawer } from './SparePartDrawer'
import { StockInboundDrawer } from './StockInboundDrawer'
import { StockWarningTable } from './StockWarningTable'

interface SparePartsPageProps {
  workshopCode: string
  workshopLabel: string
  initialSpareParts: SparePart[]
  initialSparePartTotal: number
  initialStockWarnings: StockWarning[]
}

export function SparePartsPage({
  workshopCode,
  workshopLabel,
  initialSpareParts,
  initialSparePartTotal,
  initialStockWarnings,
}: SparePartsPageProps) {
  const {
    sparePartPage, sparePartPageSize, sparePartKeyword,
    setSpareParts, setSparePartTotal, setSparePartLoading, setStockWarnings,
    stockWarnings,
    openSparePartDrawer,
  } = useEquipmentStore()

  useEffect(() => {
    setSpareParts(initialSpareParts)
    setSparePartTotal(initialSparePartTotal)
    setStockWarnings(initialStockWarnings)
  }, [initialSpareParts, initialSparePartTotal, initialStockWarnings, setSpareParts, setSparePartTotal, setStockWarnings])

  const fetchData = useCallback(async () => {
    setSparePartLoading(true)
    try {
      const [partsRes, warnings] = await Promise.all([
        fetchSparePartsClient({
          workshop: workshopCode,
          keyword: sparePartKeyword || undefined,
          page: sparePartPage, page_size: sparePartPageSize,
        }),
        fetchStockWarningsClient(workshopCode),
      ])
      setSpareParts(partsRes.items)
      setSparePartTotal(partsRes.total)
      setStockWarnings(warnings)
    } catch (e) {
      console.error('获取备件数据失败:', e)
    } finally {
      setSparePartLoading(false)
    }
  }, [workshopCode, sparePartKeyword, sparePartPage, sparePartPageSize, setSpareParts, setSparePartTotal, setSparePartLoading, setStockWarnings])

  useEffect(() => {
    queueMicrotask(fetchData)
  }, [fetchData])

  return (
    <ConfigProvider locale={zhCN}>
      <App>
        <div style={{ marginBottom: 24 }}>
          <h2 style={{
            fontSize: 22, fontWeight: 600, color: '#1a1a1a',
            margin: 0, marginBottom: 4, lineHeight: 1.3,
          }}>
            备件管理 · {workshopLabel}
          </h2>
          <p style={{ fontSize: 14, color: '#787671', margin: 0, lineHeight: 1.5 }}>
            {workshopLabel} · 备件库存 · 入库管理 · 库存预警 · 物料追踪
          </p>
        </div>
        {/* 库存预警：仅存在低于最低库存的备件时展示 */}
        {stockWarnings.length > 0 && (
          <div
            style={{
              background: '#ffffff',
              padding: 20,
              borderRadius: 12,
              border: '1px solid #e5e3df',
              marginBottom: 16,
            }}
          >
            <div style={{ fontSize: 15, fontWeight: 600, color: '#1a1a1a', marginBottom: 12 }}>
              库存预警
            </div>
            <StockWarningTable />
          </div>
        )}
        <div
          style={{
            background: '#ffffff',
            padding: 20,
            borderRadius: 12,
            border: '1px solid #e5e3df',
          }}
        >
          <SparePartTable onRefresh={fetchData} />
        </div>

        <SparePartDrawer onRefresh={fetchData} workshopCode={workshopCode} />
        <StockInboundDrawer onRefresh={fetchData} />
      </App>
    </ConfigProvider>
  )
}
