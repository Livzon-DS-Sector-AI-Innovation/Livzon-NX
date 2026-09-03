'use client'

import { useEffect } from 'react'
import { Alert, App, Button } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { DeviationTable } from './DeviationTable'
import { useDeviationStore } from '@/stores/quality'
import { fetchDeviations } from '@/lib/api/client/quality'
import { useDeviationPermissions } from './useDeviationPermissions'
import type { DeviationListItem } from '@/types/quality'

import Link from 'next/link'

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export function DeviationPage() {
  const { message } = App.useApp()
  const { canQuery, canOperate, authorizationKey } = useDeviationPermissions()
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
    queryKey: ['quality-deviation', 'list', authorizationKey, {
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
      status: statusFilter || undefined,
      level: levelFilter || undefined,
      department: departmentFilter || undefined,
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
    enabled: canQuery,
  })

  useEffect(() => {
    if (canQuery && data) {
      setDeviations(data.items as DeviationListItem[])
      setTotal(data.total)
    } else {
      setDeviations([])
      setTotal(0)
    }
  }, [canQuery, data, setDeviations, setTotal])

  useEffect(() => {
    setLoading(loading)
  }, [loading, setLoading])

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载偏差台账数据失败'))
    }
  }, [error, message])

  if (!canQuery) {
    return <Alert type="info" showIcon title="可以访问偏差台账，但尚未获得查询数据权限，请联系系统管理员。" />
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>偏差登记表</h1>
        {canOperate && <Link href="/quality/deviations/new">
          <Button type="primary" icon={<PlusOutlined />}>
            新建偏差
          </Button>
        </Link>}
      </div>
      <DeviationTable loading={loading} />
    </div>
  )
}
