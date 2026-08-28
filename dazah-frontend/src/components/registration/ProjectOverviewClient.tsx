'use client'

import { App, Alert, Space } from 'antd'
import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'

import { fetchDeclarationProgressWorkbook, fetchProjectLedgerWorkbook } from '@/lib/api/client/registration'
import { registrationDeclarationProgressSheets } from '@/lib/registration-declaration-progress'
import { registrationProjectLedgerSheets } from '@/lib/registration-project-ledger'
import type { ProjectOverview } from '@/types/registration'

import { ProjectDashboardPage } from '@/components/registration'

const BASE_OVERVIEW: ProjectOverview = {
  module_name: '申报项目',
  path: '/registration/project',
  modules: [
    {
      key: 'project-ledger',
      name: '申报台账',
      description: '维护申报项目主记录、子记录历史以及整本台账导入导出。',
      path: '/registration/project-ledger',
      workbook_name: '1. 注册台账.xlsx',
      updated_at: null,
      total_records: 0,
      sheet_count: registrationProjectLedgerSheets.length,
      child_pages: registrationProjectLedgerSheets.map((sheet) => ({
        key: sheet.key,
        name: sheet.name,
        path: sheet.path,
      })),
      api_endpoints: [],
    },
    {
      key: 'declaration-progress',
      name: '申报进度',
      description: '维护 7 个申报进度子表、主子记录层级、颜色标记以及整本工作簿导入导出。',
      path: '/registration/declaration-progress',
      workbook_name: '宁夏-注册项目信息统计表-2026.06.25.xlsx',
      updated_at: null,
      total_records: 0,
      sheet_count: registrationDeclarationProgressSheets.length,
      child_pages: registrationDeclarationProgressSheets.map((sheet) => ({
        key: sheet.key,
        name: sheet.name,
        path: sheet.path,
      })),
      api_endpoints: [],
    },
  ],
}

export default function ProjectOverviewClient() {
  const { message } = App.useApp()
  const { data: overview = BASE_OVERVIEW, isLoading: loading, error } = useQuery<ProjectOverview>({
    queryKey: ['registration-project', 'overview'],
    queryFn: async () => {
      const [ledgerOverview, declarationOverview] = await Promise.all([
        fetchProjectLedgerWorkbook(),
        fetchDeclarationProgressWorkbook(),
      ])

      return {
        ...BASE_OVERVIEW,
        modules: [
          {
            ...BASE_OVERVIEW.modules[0],
            workbook_name: ledgerOverview.workbook_name,
            updated_at: ledgerOverview.updated_at,
            total_records: ledgerOverview.total_records,
            sheet_count: ledgerOverview.sheets.length,
          },
          {
            ...BASE_OVERVIEW.modules[1],
            workbook_name: declarationOverview.workbook_name,
            updated_at: declarationOverview.updated_at,
            total_records: declarationOverview.total_records,
            sheet_count: declarationOverview.sheets.length,
          },
        ],
      }
    },
  })

  useEffect(() => {
    if (error) {
      const nextError = error instanceof Error ? error.message : '申报项目总览刷新失败'
      message.warning(nextError)
    }
  }, [error, message])

  const errorMessage = error instanceof Error ? error.message : error ? '申报项目总览刷新失败' : null

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      {errorMessage ? (
        <Alert
          type="warning"
          showIcon
          message="申报项目总览刷新失败"
          description={`${errorMessage}${loading ? '，正在继续重试。' : '，当前先展示最新页面壳子。'}`}
        />
      ) : null}
      <ProjectDashboardPage overview={overview} />
    </Space>
  )
}
