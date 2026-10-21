import { getCurrentUser } from '@/actions/auth'
import { getFireEquipmentDetail } from '@/actions/safety'
import { FireInspectionScanView } from '@/components/safety'
import { SAFETY_PAGE_TABLE_KEYS } from '@/lib/safety-page-tables'

export const dynamic = 'force-dynamic'

/** 扫码点检页：飞书扫码直达，展示器材详情并按检查卡提交点检。 */
export default async function FireEquipmentScanPage({
  params,
}: {
  params: Promise<{ equipment_id: string }>
}) {
  const { equipment_id: equipmentId } = await params
  const pageKey = SAFETY_PAGE_TABLE_KEYS.fireEquipmentInspection
  const [user, detailRes] = await Promise.all([
    getCurrentUser(),
    getFireEquipmentDetail({ pageKey, equipmentId }),
  ])
  const detail = detailRes.code === 200 && detailRes.data ? detailRes.data : null
  const error = detail ? null : detailRes.message || '加载器材详情失败'

  return (
    <div style={{ padding: '16px 12px 32px' }}>
      <FireInspectionScanView
        pageKey={pageKey}
        inspectorName={user?.name ?? ''}
        detail={detail}
        error={error}
      />
    </div>
  )
}
