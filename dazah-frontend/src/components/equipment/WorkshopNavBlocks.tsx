'use client'

// 设备统一工作台顶部的 9 个车间切换块（复刻生产模块产线块样式）：
// 数据以 URL query ?workshop= 为准（服务端取数、可分享），store 跨页记忆
// 上次选择——无参数进入时自动补上；切换车间保留当前 ?module= 功能模块；
// 非管理员按当前模块授权的 visible_sections 过滤车间。

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
  hasEquipmentWorkshopAccess,
  type EquipmentPageKey,
} from '@/lib/equipment-page-permissions'

const { Text } = Typography

// 车间专属色（与生产产线块同一套调色板）
// 201-2-MC 承接原 201-2 的青色；201-2-DR 多拉产线用品红区分
const WORKSHOP_COLORS: Record<string, string> = {
  '101-1': '#1677ff',
  '101-2': '#13c2c2',
  '102-1': '#d46b08',
  '102-2': '#389e0d',
  '103': '#c41d7f',
  '201-1': '#5645d4',
  '201-2-MC': '#08979c',
  '201-2-DR': '#eb2f96',
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
  // 切换车间时保留当前功能模块（统一工作台 ?module= 参数）
  const moduleQuery = searchParams.get('module')
  const moduleSuffix = moduleQuery ? `&module=${encodeURIComponent(moduleQuery)}` : ''

  // 无参数进入：跳到上次选择的车间（有记忆且非缺省时）
  useEffect(() => {
    if (urlWorkshop) return
    const saved = useEquipmentWorkshopStore.getState().workshopCode
    if (saved !== '201-1') {
      router.replace(`${pathname}?workshop=${encodeURIComponent(saved)}${moduleSuffix}`, { scroll: false })
    }
  }, [urlWorkshop, pathname, router, moduleSuffix])

  const visible = EQUIPMENT_WORKSHOPS.filter((ws) =>
    hasEquipmentWorkshopAccess(user, pageKey, ws.code),
  )
  const active = urlWorkshop ?? workshopCode

  return (
    // 垂直间距由页面根容器 gap-3 统一提供（与生产概览页一致）
    <Row gutter={[12, 12]}>
      {visible.map((ws) => {
        const isActive = active === ws.code
        return (
          // 弹性等宽：宽屏 9 块一行铺满，窄屏按 144px 基准自然换行
          <Col key={ws.code} flex="1 1 144px">
            <div
              title={`切换到 ${ws.fullName ?? ws.label}`}
              onClick={() => {
                setWorkshopCode(ws.code)
                router.push(`${pathname}?workshop=${encodeURIComponent(ws.code)}${moduleSuffix}`, { scroll: false })
              }}
              data-testid={`workshop-block:${ws.code}`}
              className="flex items-center justify-center gap-2 rounded-lg border bg-[var(--color-canvas)] cursor-pointer transition-colors"
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
