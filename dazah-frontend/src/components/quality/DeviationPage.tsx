'use client'

import { useEffect } from 'react'
import { App, Button } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { DeviationTable } from './DeviationTable'
import { useDeviationStore } from '@/stores/quality'
import { fetchDeviations } from '@/lib/api/client/quality'

import Link from 'next/link'

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export function DeviationPage() {
  const { message } = App.useApp()
  const {
    setDeviations,
    setTotal,
    setLoading,
    page,
    pageSize,
    statusFilter,
    levelFilter,
    departmentFilter,
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

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-deviation', 'list', {
      keyword,
      statusFilter,
      levelFilter,
      departmentFilter,
      deviationCodeFilter,
      productKeywordFilter,
      hasOccurredBeforeFilter,
      isClosedFilter,
      investigationCompletedFrom,
      investigationCompletedTo,
      rootCauseKeywordFilter,
      correctiveActionsKeywordFilter,
      page,
      pageSize,
    }],
    queryFn: () => fetchDeviations({
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
    }),
  })

  useEffect(() => {
    if (data) {
      setDeviations(data.items as any[])
      setTotal(data.total)
    }
  }, [data, setDeviations, setTotal])

  useEffect(() => {
    setLoading(loading)
  }, [loading, setLoading])

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载偏差台账数据失败'))
    }
  }, [error, message])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>偏差登记表</h1>
        <Link href="/quality/deviations/new">
          <Button type="primary" icon={<PlusOutlined />}>
            新建偏差
          </Button>
        </Link>
      </div>
      <DeviationTable loading={loading} />
    </div>
  )
}
