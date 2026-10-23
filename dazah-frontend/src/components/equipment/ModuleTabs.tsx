'use client'

// 设备统一工作台的功能模块切换 Tab：替换原各功能页的标题/副标题行，
// 在当前车间内切换功能模块（URL 组合 /equipment?workshop=<车间>&module=<模块>，
// 可分享/刷新保位）；按用户页面授权过滤不可见模块。

import { useEffect, useMemo } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Tabs } from 'antd'
import { useAuthStore } from '@/stores/auth'
import {
  EQUIPMENT_MODULE_TABS,
  hasEquipmentPageAccess,
  isEquipmentModule,
  type EquipmentModule,
} from '@/lib/equipment-page-permissions'

export function ModuleTabs({
  workshop,
  activeModule,
}: {
  workshop: string
  activeModule?: EquipmentModule
}) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const user = useAuthStore((s) => s.user)

  const visible = useMemo(
    () => EQUIPMENT_MODULE_TABS.filter((tab) => hasEquipmentPageAccess(user, tab.key)),
    [user],
  )

  // 未指定模块（或指定模块无权限）时自动落到首个有权限的模块，避免空内容
  useEffect(() => {
    const param = searchParams.get('module')
    const current = isEquipmentModule(param) ? param : undefined
    if (current && visible.some((tab) => tab.module === current)) return
    const fallback = visible[0]?.module
    if (fallback) {
      router.replace(
        `/equipment?workshop=${encodeURIComponent(workshop)}&module=${fallback}`,
        { scroll: false },
      )
    }
  }, [searchParams, visible, workshop, router])

  const go = (module: string) => {
    router.push(
      `/equipment?workshop=${encodeURIComponent(workshop)}&module=${module}`,
      { scroll: false },
    )
  }

  return (
    <div
      data-testid="equipment-module-tabs"
      className="rounded-xl border bg-white"
      style={{ padding: '12px 20px 0', marginBottom: 16, borderColor: '#e5e3df' }}
    >
      <Tabs
        activeKey={activeModule}
        onChange={go}
        items={visible.map((tab) => ({ key: tab.module, label: tab.label }))}
      />
    </div>
  )
}
