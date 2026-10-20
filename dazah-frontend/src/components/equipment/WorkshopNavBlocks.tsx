'use client'

import { useEffect } from 'react'
import { useRouter, usePathname, useSearchParams } from 'next/navigation'
import { Segmented } from 'antd'
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

interface WorkshopNavBlocksProps {
  /** 当前功能页 key，用于按授权过滤不可见车间 */
  pageKey: EquipmentPageKey
}

/**
 * 设备模块车间切换块：数据以 URL query ?workshop= 为准（可分享、SSR 取数），
 * store 跨页记忆上次选择——无参数进入时自动补上记忆的车间。
 */
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

  // 无参数进入：跳到上次选择的车间（有记忆且合法时）
  useEffect(() => {
    if (urlWorkshop) return
    const saved = useEquipmentWorkshopStore.getState().workshopCode
    if (saved !== '201-1') {
      router.replace(`${pathname}?workshop=${encodeURIComponent(saved)}`, { scroll: false })
    }
  }, [urlWorkshop, pathname, router])

  const options = EQUIPMENT_WORKSHOPS
    .filter((ws) => hasEquipmentWorkshopAccess(user, pageKey, ws.code))
    .map((ws) => ({ label: ws.label, value: ws.code }))

  const active = urlWorkshop ?? workshopCode

  return (
    <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-start' }}>
      <Segmented
        options={options}
        value={active}
        onChange={(value) => {
          const code = String(value)
          setWorkshopCode(code)
          router.push(`${pathname}?workshop=${encodeURIComponent(code)}`, { scroll: false })
        }}
      />
    </div>
  )
}
