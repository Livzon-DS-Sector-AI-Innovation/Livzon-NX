'use client'

import { useEffect, useCallback, useRef, useState } from 'react'
import { App, Button } from 'antd'
import { QrcodeOutlined, ReloadOutlined } from '@ant-design/icons'
import { EquipmentCategory, Location, Equipment, EquipmentStatistics, DepartmentOption } from '@/types/equipment'
import { useEquipmentStore } from '@/stores/equipment'
import { fetchEquipmentsClient, fetchEquipmentStatisticsClient, fetchCategoriesClient, fetchLocationsClient, fetchDepartmentsClient } from '@/lib/api/equipment-client'

import { fetchEquipmentQrcodePdf } from '@/lib/api/client/equipmentQrcode'
import { EquipmentTable } from './EquipmentTable'
import { EquipmentDrawer } from './EquipmentDrawer'
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

// 状态筛选按钮配置：点击筛选、再点取消
const STATUS_FILTERS = [
  { key: '' as const, label: '总数', color: '#1a1a1a', dotColor: '#787671' },
  { key: '在用' as const, label: '在用', color: '#1aae39', dotColor: '#1aae39' },
  { key: '维修中' as const, label: '维修中', color: '#dd5b00', dotColor: '#dd5b00' },
  { key: '停用' as const, label: '停用', color: '#787671', dotColor: '#787671' },
]

export function EquipmentPage({
  workshopCode,
  initialCategories,
  initialLocations,
  initialEquipments,
  initialTotal,
  initialStatistics,
  initialDepartments,
}: EquipmentPageProps) {
  const {
    categories,
    locations,
    statistics,
    equipments,
    failureCodes,
    selectedCategory,
    selectedLocation,
    statusFilter,
    departmentFilter,
    departments,
    keyword,
    loading,
    setStatusFilter,
    setDepartments,
    setCategories,
    setLocations,
    setEquipments,
    setTotal,
    setStatistics,
    setLoading,
    setSelectedCategory,
    setSelectedLocation,
  } = useEquipmentStore()

  const [resetKey, setResetKey] = useState(0)
  const pageSizeRef = useRef(20)
  const [qrcodeExporting, setQrcodeExporting] = useState(false)
  const { message } = App.useApp()

  const handleExportQrcode = useCallback(async () => {
    if (qrcodeExporting) return
    setQrcodeExporting(true)
    try {
      await fetchEquipmentQrcodePdf(workshopCode)
      message.success('设备报修码 PDF 已开始下载')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '设备码导出失败')
    } finally {
      setQrcodeExporting(false)
    }
  }, [qrcodeExporting, workshopCode, message])

  // 初始化 store 数据（SSR 预取）
  useEffect(() => {
    setCategories(initialCategories)
    setLocations(initialLocations)
    setEquipments(initialEquipments)
    setTotal(initialTotal)
    setStatistics(initialStatistics)
  }, [
    initialCategories, initialEquipments, initialLocations,
    initialStatistics, initialTotal,
    setCategories, setEquipments, setLocations, setStatistics, setTotal,
  ])

  useEffect(() => {
    setDepartments(initialDepartments)
  }, [initialDepartments, setDepartments])

  // 客户端补偿加载
  useEffect(() => {
    const loadMissing = async () => {
      const tasks: Promise<void>[] = []
      if (!categories.length) {
        tasks.push(
          fetchCategoriesClient().then(setCategories).catch(() => {}),
        )
      }
      if (!locations.length) {
        tasks.push(
          fetchLocationsClient().then(setLocations).catch(() => {}),
        )
      }
      if (!departments.length) {
        tasks.push(
          fetchDepartmentsClient().then(setDepartments).catch(() => {}),
        )
      }
      if (tasks.length) await Promise.allSettled(tasks)
    }
    void loadMissing()
  }, [categories.length, departments.length, locations.length, setCategories, setDepartments, setLocations])

  // 统计随车间刷新（SSR 预取失败或数据滞后时兜底）
  useEffect(() => {
    void fetchEquipmentStatisticsClient(workshopCode).then(setStatistics).catch(() => {})
  }, [workshopCode, setStatistics])

  const fetchData = useCallback(async (p: number, ps: number) => {
    setLoading(true)
    try {
      const res = await fetchEquipmentsClient({
        workshop: workshopCode,
        category_id: selectedCategory,
        location_id: selectedLocation,
        department_id: departmentFilter,
        status: statusFilter || undefined,
        keyword: keyword || undefined,
        page: p,
        page_size: ps,
      })
      setEquipments(res.items)
      setTotal(res.total)
    } catch {
      // 静默失败，保持上一次数据
    } finally {
      setLoading(false)
    }
  }, [workshopCode, selectedCategory, selectedLocation, departmentFilter, statusFilter, keyword, setEquipments, setTotal, setLoading])

  useEffect(() => {
    void fetchData(1, pageSizeRef.current)
    setResetKey(k => k + 1)
  }, [fetchData])

  const currentStats = statistics ?? initialStatistics
  const hasActiveFilters = Boolean(selectedCategory || selectedLocation || departmentFilter || keyword)

  const refresh = useCallback(() => {
    void fetchData(1, pageSizeRef.current)
    setResetKey(k => k + 1)
  }, [fetchData])

  return (
    <div className="flex flex-col gap-3" style={{ height: 'calc(100vh - 210px)', minHeight: 400 }}>
      {/* 状态筛选按钮行 */}
      <div className="flex items-center gap-3 flex-wrap">
        {STATUS_FILTERS.map(({ key, label, color, dotColor }) => {
          const isActive = statusFilter === key
          const value = key === '' ? currentStats.total : (currentStats.by_status[key] || 0)
          return (
            <button
              key={key || 'all'}
              type="button"
              onClick={() => setStatusFilter(key)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                cursor: 'pointer',
                background: isActive ? '#f0eeec' : 'transparent',
                border: isActive ? '1px solid #c8c4be' : '1px solid transparent',
                borderRadius: 20, padding: '4px 14px',
                fontSize: 13, fontWeight: isActive ? 600 : 400,
                color: isActive ? '#1a1a1a' : '#5d5b54',
                transition: 'all 0.15s ease', fontFamily: 'inherit',
              }}
            >
              <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: dotColor, flexShrink: 0 }} />
              {label}
              <span style={{ fontWeight: 600, color, marginLeft: 2 }}>{value}</span>
            </button>
          )
        })}
        {hasActiveFilters && (
          <Button
            type="text" size="small" icon={<ReloadOutlined />}
            onClick={() => { setSelectedCategory(null); setSelectedLocation(null) }}
            style={{ color: '#787671' }}
          >
            重置筛选
          </Button>
        )}
        <div style={{ flex: 1 }} />
        <Button
          size="small" icon={<QrcodeOutlined />}
          loading={qrcodeExporting}
          onClick={() => { void handleExportQrcode() }}
        >
          导出设备码
        </Button>
      </div>

      {/* 表格（含搜索/下拉筛选/操作按钮） */}
      <EquipmentTable
        loading={loading}
        resetKey={resetKey}
        onPageChange={(p, ps) => { pageSizeRef.current = ps; void fetchData(p, ps) }}
        workshopCode={workshopCode}
      />

      {/* 抽屉 */}
      <EquipmentDrawer workshopCode={workshopCode} onRefresh={refresh} />
      <RepairDrawer
        equipments={equipments.map(e => ({
          id: e.id, equipment_no: e.equipment_no, name: e.name, importance: e.importance,
        }))}
        symptoms={failureCodes.symptoms}
        onRefresh={refresh}
      />
    </div>
  )
}
