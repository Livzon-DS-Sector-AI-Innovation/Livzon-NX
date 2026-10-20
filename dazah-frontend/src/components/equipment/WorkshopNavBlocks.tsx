'use client'

// 设备模块五个功能页顶部共用的 9 个车间切换块（复刻生产模块产线块样式）：
// 数据以 URL query ?workshop= 为准（服务端取数、可分享），store 跨页记忆
// 上次选择——无参数进入时自动补上；非管理员按授权车间过滤。

import { useEffect } from 'react'
import { useRouter, usePathname, useSearchParams } from 'next/navigation'
import { Col, Row, Typography } from 'antd'
import { ApartmentOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/stores/auth'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
import {
  restoreEquipmentWorkshopContext,
  useEquipmentWorkshopStore,
} from '@/stores/equipment-workshop'
import {
  EQUIPMENT_PAGE_KEYS,
  hasEquipmentPageAccess,
  hasEquipmentWorkshopAccess,
  type EquipmentPageKey,
} from '@/lib/equipment-page-permissions'

const { Text } = Typography

// 车间专属色（与生产产线块同一套调色板）
const WORKSHOP_COLORS: Record<string, string> = {
  '101-1': '#1677ff',
  '101-2': '#13c2c2',
  '102-1': '#d46b08',
  '102-2': '#389e0d',
  '103': '#c41d7f',
  '201-1': '#5645d4',
  '201-2': '#08979c',
  '201-3': '#cf1322',
  '203': '#d4b106',
}

interface WorkshopNavBlocksProps {
  /** 当前功能页 key，用于按授权过滤不可见车间 */
  pageKey: EquipmentPageKey
}

export function WorkshopNavBlocks({ pageKey }: WorkshopNavBlocksProps) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const workshopCode = useEquipmentWorkshopStore((s) => s.workshopCode)
  const setWorkshopCode = useEquipmentWorkshopStore((s) => s.setWorkshopCode)
  const user = useAuthStore((s) => s.user)

  useEffect(() => {
    restoreEquipmentWorkshopContext()
  }, [])

  const urlWorkshop = searchParams.get('workshop')

  // 无参数进入：跳到上次选择的车间（有记忆且非缺省时）
  useEffect(() => {
    if (urlWorkshop) return
    const saved = useEquipmentWorkshopStore.getState().workshopCode
    if (saved !== '201-1') {
      router.replace(`${pathname}?workshop=${encodeURIComponent(saved)}`, { scroll: false })
    }
  }, [urlWorkshop, pathname, router])

  const visible = EQUIPMENT_WORKSHOPS.filter((ws) =>
    hasEquipmentWorkshopAccess(user, pageKey, ws.code),
  )
  const active = urlWorkshop ?? workshopCode
  // 汇总块（仿生产模块 SUMMARY 首块）：点击跳全局汇总页，仅在持有汇总页授权时展示
  const showSummary = hasEquipmentPageAccess(user, EQUIPMENT_PAGE_KEYS.stats)

  return (
    <Row gutter={[12, 12]} style={{ marginBottom: 8 }}>
      {showSummary && (
        <Col flex="1 1 144px">
          <div
            title="切换到 设备汇总（全车间聚合）"
            onClick={() => router.push('/equipment/stats')}
            data-testid="workshop-block:summary"
            className="flex items-center justify-center gap-2 rounded-lg border cursor-pointer transition-colors"
            style={{
              height: 56,
              borderColor: '#5645d4',
              backgroundColor: 'rgba(86, 69, 212, 0.08)',
            }}
          >
            <ApartmentOutlined style={{ color: '#5645d4', fontSize: 18 }} />
            <Text strong style={{ fontSize: 13, color: '#5645d4' }}>
              汇总
            </Text>
          </div>
        </Col>
      )}
      {visible.map((ws) => {
        const isActive = active === ws.code
        return (
          // 弹性等宽：宽屏 9 块一行铺满，窄屏按 144px 基准自然换行
          <Col key={ws.code} flex="1 1 144px">
            <div
              title={`切换到 ${ws.label}`}
              onClick={() => {
                setWorkshopCode(ws.code)
                router.push(`${pathname}?workshop=${encodeURIComponent(ws.code)}`, { scroll: false })
              }}
              data-testid={`workshop-block:${ws.code}`}
              className="flex items-center justify-center gap-2 rounded-lg border bg-white cursor-pointer transition-colors"
              style={{
                height: 56,
                borderColor: isActive
                  ? 'var(--color-primary)'
                  : 'var(--color-hairline)',
                backgroundColor: isActive
                  ? 'var(--color-primary-soft, #f0f7ff)'
                  : undefined,
              }}
            >
              <ApartmentOutlined
                style={{ color: WORKSHOP_COLORS[ws.code] ?? '#5667a3', fontSize: 18 }}
              />
              <Text strong style={{ fontSize: 13 }}>
                {ws.label}
              </Text>
            </div>
          </Col>
        )
      })}
    </Row>
  )
}
