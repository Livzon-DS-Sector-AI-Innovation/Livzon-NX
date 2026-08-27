'use client'

import { useEffect, useState } from 'react'
import { App, Button, Space } from 'antd'
import { PlusOutlined, SyncOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CapaTable } from './CapaTable'
import { useCapaStore } from '@/stores/quality'
import { fetchCapas } from '@/lib/api/client/quality'

import { syncCapasFromFeishu } from '@/actions/quality-capa'
import Link from 'next/link'

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export function CapaPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [pulling, setPulling] = useState(false)
  const {
    page,
    pageSize,
    statusFilter,
    sourceFilter,
    categoryFilter,
    keyword,
    capaCodeFilter,
    affectedProductFilter,
    sourceCodeFilter,
    evaluationResultFilter,
    closureDateFrom,
    closureDateTo,
    departmentFilter,
    qaConfirmerFilter,
  } = useCapaStore()

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-capa', 'list', {
      keyword,
      departmentFilter,
      statusFilter,
      sourceFilter,
      categoryFilter,
      capaCodeFilter,
      affectedProductFilter,
      sourceCodeFilter,
      evaluationResultFilter,
      closureDateFrom,
      closureDateTo,
      qaConfirmerFilter,
      page,
      pageSize,
    }],
    queryFn: () => fetchCapas({
      page,
      page_size: pageSize,
      status: statusFilter || undefined,
      source: sourceFilter || undefined,
      category: categoryFilter || undefined,
      keyword: keyword || undefined,
      capa_code: capaCodeFilter || undefined,
      affected_product: affectedProductFilter || undefined,
      source_code: sourceCodeFilter || undefined,
      evaluation_result: evaluationResultFilter || undefined,
      closure_date_from: closureDateFrom || undefined,
      closure_date_to: closureDateTo || undefined,
      department: departmentFilter || undefined,
      qa_confirmer: qaConfirmerFilter || undefined,
    }),
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载CAPA数据失败'))
    }
  }, [error, message])

  const handlePullFromFeishu = async () => {
    setPulling(true)
    try {
      const result = await syncCapasFromFeishu()
      message.success(`从飞书拉取完成：成功 ${result.synced ?? 0} 条，失败 ${result.failed ?? 0} 条`)
      queryClient.invalidateQueries({ queryKey: ['quality-capa'] })
    } catch (err) {
      message.error(getErrorMessage(err, '从飞书拉取失败'))
    } finally {
      setPulling(false)
    }
  }

  const capas = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-[22px] font-semibold m-0">CAPA登记汇总表</h1>
        <Space>
          <Button icon={<SyncOutlined />} loading={pulling} onClick={() => void handlePullFromFeishu()}>
            拉取飞书
          </Button>
          <Link href="/quality/capas/new">
            <Button type="primary" icon={<PlusOutlined />}>
              新建CAPA
            </Button>
          </Link>
        </Space>
      </div>
      <CapaTable capas={capas} total={total} loading={loading} />
    </div>
  )
}
