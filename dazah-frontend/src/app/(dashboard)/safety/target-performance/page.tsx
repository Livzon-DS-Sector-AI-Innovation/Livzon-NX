import {
  getSafetyDutyAssessmentStats,
  getSafetyDutyAssessments,
  getSafetyTargetAgreementStats,
  getSafetyTargetAgreements,
  getSafetyTargets,
  getSafetyTargetStats,
} from '@/actions/safety'
import { TargetPerformancePanel } from '@/components/safety'

export const dynamic = 'force-dynamic'

const PAGE_KEY = 'safety:governance:target-performance'

export default async function TargetPerformancePage() {
  const [
    targetsRes,
    statsRes,
    agreementsRes,
    agreementStatsRes,
    assessmentsRes,
    assessmentStatsRes,
  ] = await Promise.all([
    getSafetyTargets({ page_size: 200 }).catch(() => null),
    getSafetyTargetStats().catch(() => null),
    getSafetyTargetAgreements({ page_size: 200 }).catch(() => null),
    getSafetyTargetAgreementStats().catch(() => null),
    getSafetyDutyAssessments({ page_size: 200 }).catch(() => null),
    getSafetyDutyAssessmentStats().catch(() => null),
  ])

  const initialTargets =
    targetsRes && targetsRes.code === 200 && targetsRes.data
      ? targetsRes.data.items
      : []
  const initialStats = statsRes && statsRes.code === 200 ? statsRes.data : null
  const initialAgreements =
    agreementsRes && agreementsRes.code === 200 && agreementsRes.data
      ? agreementsRes.data.items
      : []
  const initialAgreementStats =
    agreementStatsRes && agreementStatsRes.code === 200
      ? agreementStatsRes.data
      : null
  const initialAssessments =
    assessmentsRes && assessmentsRes.code === 200 && assessmentsRes.data
      ? assessmentsRes.data.items
      : []
  const initialAssessmentStats =
    assessmentStatsRes && assessmentStatsRes.code === 200
      ? assessmentStatsRes.data
      : null
  const initialError =
    targetsRes && targetsRes.code !== 200
      ? targetsRes.message || '加载目标责任与绩效数据失败'
      : agreementsRes && agreementsRes.code !== 200
        ? agreementsRes.message || '加载责任书数据失败'
        : assessmentsRes && assessmentsRes.code !== 200
          ? assessmentsRes.message || '加载考核数据失败'
          : null

  return (
    <TargetPerformancePanel
      pageKey={PAGE_KEY}
      initialTargets={initialTargets}
      initialStats={initialStats}
      initialAgreements={initialAgreements}
      initialAgreementStats={initialAgreementStats}
      initialAssessments={initialAssessments}
      initialAssessmentStats={initialAssessmentStats}
      initialError={initialError}
    />
  )
}
