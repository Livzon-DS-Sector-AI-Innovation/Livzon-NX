import { Alert, Space } from 'antd'

import { DeclarationProgressDashboardPage } from '@/components/registration'
import {
  fetchDeclarationProgressSheetDetailServer,
  fetchDeclarationProgressWorkbookServer,
} from '@/lib/api/server/registration'
import type { DeclarationProgressSheetDetail } from '@/types/registration'

export const dynamic = 'force-dynamic'

export default async function DeclarationProgressDashboardRoute() {
  let overview:
    | Awaited<ReturnType<typeof fetchDeclarationProgressWorkbookServer>>
    | null = null
  let fulfilledSheets: DeclarationProgressSheetDetail[] = []
  let failedCount = 0
  let errorMessage: string | null = null

  try {
    overview = await fetchDeclarationProgressWorkbookServer()
    const sheetResults = await Promise.allSettled(
      overview.sheets.map((sheet) => fetchDeclarationProgressSheetDetailServer(sheet.sheet_key))
    )

    fulfilledSheets = sheetResults
      .filter(
        (item): item is PromiseFulfilledResult<DeclarationProgressSheetDetail> =>
          item.status === 'fulfilled'
      )
      .map((item) => item.value)

    failedCount = sheetResults.length - fulfilledSheets.length
  } catch (error) {
    errorMessage = error instanceof Error ? error.message : '申报进度加载失败'
  }

  if (!overview) {
    return (
      <Alert
        type="error"
        showIcon
        title="申报进度加载失败"
        description={errorMessage || '申报进度加载失败'}
      />
    )
  }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      {failedCount > 0 ? (
        <Alert
          type="warning"
          showIcon
          title="申报进度部分子表加载超时"
          description={`共 ${failedCount} 个子表未及时返回，当前先展示已成功加载的数据。`}
        />
      ) : null}
      <DeclarationProgressDashboardPage
        overview={{
          ...overview,
          sheets: fulfilledSheets,
        }}
      />
    </Space>
  )
}
