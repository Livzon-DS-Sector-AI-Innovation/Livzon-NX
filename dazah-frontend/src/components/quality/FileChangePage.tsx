'use client'

import { useQuery } from '@tanstack/react-query'
import { ChangeTable } from './ChangeTable'
import { useChangeStore } from '@/stores/quality'
import { fetchChanges } from '@/lib/api/client/quality'

export function FileChangePage() {
  const {
    page,
    pageSize,
    changeCodeFilter,
    applicantDepartmentFilter,
    changeObjectFilter,
    changeLevelFilter,
    applicationDateFrom,
    applicationDateTo,
    plannedApprovalDateFrom,
    plannedApprovalDateTo,
    executionDateFrom,
    executionDateTo,
    closureDateFrom,
    closureDateTo,
    contentKeywordFilter,
  } = useChangeStore()

  const { data, isLoading } = useQuery({
    queryKey: ['quality-file-change', 'list', {
      changeCodeFilter,
      applicantDepartmentFilter,
      changeObjectFilter,
      changeLevelFilter,
      applicationDateFrom,
      applicationDateTo,
      plannedApprovalDateFrom,
      plannedApprovalDateTo,
      executionDateFrom,
      executionDateTo,
      closureDateFrom,
      closureDateTo,
      contentKeywordFilter,
      page,
      pageSize,
    }],
    queryFn: () => fetchChanges({
      change_type: 'file',
      page,
      page_size: pageSize,
      change_code: changeCodeFilter || undefined,
      applicant_department: applicantDepartmentFilter || undefined,
      change_object: changeObjectFilter || undefined,
      change_level: changeLevelFilter || undefined,
      application_date_from: applicationDateFrom || undefined,
      application_date_to: applicationDateTo || undefined,
      planned_approval_date_from: plannedApprovalDateFrom || undefined,
      planned_approval_date_to: plannedApprovalDateTo || undefined,
      execution_date_from: executionDateFrom || undefined,
      execution_date_to: executionDateTo || undefined,
      closure_date_from: closureDateFrom || undefined,
      closure_date_to: closureDateTo || undefined,
      content_keyword: contentKeywordFilter || undefined,
    }),
  })

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>文件变更台账</h1>
      </div>
      <ChangeTable
        changes={data?.items ?? []}
        total={data?.total ?? 0}
        loading={isLoading}
        showPlans={false}
        changeType="file"
      />
    </div>
  )
}
