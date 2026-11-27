'use client'

import { useMemo } from 'react'
import Alert from '@/components/shared/PlatformNotice'
import BoardNavBlocks from '@/components/production/board-nav-blocks'
import ScheduleAnomalyLedger from '@/components/production/ScheduleAnomalyLedger'
import {
  hasProductionAnomalyProduct,
  PRODUCTION_PAGE_KEYS,
  useProductionPermissions,
} from '@/components/production/useProductionPermissions'
import { PRODUCTION_SCHEDULING_SECTIONS } from '@/lib/production-overview-sections'
import { useAuthStore } from '@/stores/auth'

// 异常记录与排产共用产品口径：汇总无排产业务、FL 为合成预混工艺
const ANOMALY_HIDE_CODES: readonly string[] = ['SUMMARY', 'FL']

export default function ProductionAnomaliesPage() {
  const user = useAuthStore((state) => state.user)
  const { canQuery, canOperate } = useProductionPermissions(
    PRODUCTION_PAGE_KEYS.anomalies,
  )
  const visibleProducts = useMemo(
    () =>
      PRODUCTION_SCHEDULING_SECTIONS.filter((section) =>
        hasProductionAnomalyProduct(user, section.key),
      ),
    [user],
  )
  const hideCodes = useMemo(
    () => [
      ...ANOMALY_HIDE_CODES,
      ...PRODUCTION_SCHEDULING_SECTIONS.filter(
        (item) => !hasProductionAnomalyProduct(user, item.key),
      ).map((item) => item.key),
    ],
    [user],
  )

  if (!canQuery || visibleProducts.length === 0) {
    return (
      <div className="p-6">
        <Alert
          type="warning"
          showIcon
          title="未获得异常记录查看权限，请联系管理员配置页面权限。"
        />
      </div>
    )
  }

  return (
    <div className="p-6" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <BoardNavBlocks hideCodes={hideCodes} />
      <ScheduleAnomalyLedger
        visibleProducts={visibleProducts}
        canOperate={canOperate}
      />
    </div>
  )
}
