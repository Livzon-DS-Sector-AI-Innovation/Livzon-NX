'use client'

import { useCallback, useEffect } from 'react'
import { DeviationTable } from './DeviationTable'
import { useDeviationStore } from '@/stores/quality'
import { fetchFeishuDeviationLedgerRecords } from '@/lib/api/quality'

export function DeviationPage() {
  const {
    setDeviations,
    setTotal,
    setLoading,
    loading,
    page,
    pageSize,
    keyword,
    deviationCodeFilter,
    productKeywordFilter,
    hasOccurredBeforeFilter,
    isClosedFilter,
    investigationCompletedFrom,
    investigationCompletedTo,
    rootCauseKeywordFilter,
    correctiveActionsKeywordFilter,
  } = useDeviationStore()

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const result = await fetchFeishuDeviationLedgerRecords({
        page,
        page_size: pageSize,
        keyword: keyword || undefined,
        deviation_code: deviationCodeFilter || undefined,
        product_keyword: productKeywordFilter || undefined,
        has_occurred_before: hasOccurredBeforeFilter || undefined,
        is_closed: isClosedFilter || undefined,
        investigation_completed_from: investigationCompletedFrom || undefined,
        investigation_completed_to: investigationCompletedTo || undefined,
        root_cause_keyword: rootCauseKeywordFilter || undefined,
        corrective_actions_keyword: correctiveActionsKeywordFilter || undefined,
      })
      setDeviations(result.items as Parameters<typeof setDeviations>[0])
      setTotal(result.total)
    } catch (error) {
      console.warn('加载偏差数据失败:', error)
    } finally {
      setLoading(false)
    }
  }, [
    page,
    pageSize,
    keyword,
    deviationCodeFilter,
    productKeywordFilter,
    hasOccurredBeforeFilter,
    isClosedFilter,
    investigationCompletedFrom,
    investigationCompletedTo,
    rootCauseKeywordFilter,
    correctiveActionsKeywordFilter,
    setDeviations,
    setTotal,
    setLoading,
  ])

  useEffect(() => {
    loadData()
  }, [loadData])

  return (
    <div>
      <DeviationTable loading={loading} onRefresh={loadData} />
    </div>
  )
}
