'use client'

import { useState } from 'react'

import DormitoryDashboard from '@/components/administration/DormitoryDashboard'
import { MappedDatasetPage } from '@/components/feishu-data'
import { ADMIN_DORMITORY_PAGE_KEY } from '@/lib/administration-pages'

/**
 * 宿舍管理工作区（客户端）：顶部入住率仪表盘（空房/满人点击看房间、
 * AI 推荐入住）+ 宿舍清单/员工住宿退宿清单/住宿标准三表页签。
 */
export default function DormitoryWorkspace() {
  // 入住办理成功后递增 key 重挂台账，立即看到新记录与最新占用
  const [datasetVersion, setDatasetVersion] = useState(0)
  return (
    <div>
      <DormitoryDashboard onCheckinSuccess={() => setDatasetVersion((v) => v + 1)} />
      <MappedDatasetPage
        key={datasetVersion}
        moduleCode="administration"
        pageKey={ADMIN_DORMITORY_PAGE_KEY}
        title="宿舍管理"
        enableAdvancedQuery
        enableExport
        defaultSort={{ tabName: '员工住宿退宿清单', fieldName: '房间编号', direction: 'asc' }}
      />
    </div>
  )
}
