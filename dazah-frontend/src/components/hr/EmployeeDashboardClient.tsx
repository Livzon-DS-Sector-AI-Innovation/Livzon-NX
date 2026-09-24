'use client'

import { useState } from 'react'
import { Alert, Button, Card, Space, Spin } from 'antd'
import { QrcodeOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from '@tanstack/react-query'
import { fetchEmployeeStats } from '@/lib/api/client/hr'
import type { EmployeeStats } from '@/types/hr'
import EmployeeDashboardView from './EmployeeDashboardView'
import EmployeeQrCode from './EmployeeQrCode'

function EmployeeDashboardInner() {
  const [qrOpen, setQrOpen] = useState(false)
  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ['hr', 'employees', 'stats'],
    queryFn: fetchEmployeeStats,
    refetchInterval: 60 * 1000,
  })
  const stats: EmployeeStats = data?.data || {}

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">员工管理仪表盘</h1>
        <Space>
          <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => refetch()}>
            刷新数据
          </Button>
          <Button icon={<QrcodeOutlined />} onClick={() => setQrOpen(true)}>生成填写二维码</Button>
        </Space>
      </div>
      <EmployeeQrCode open={qrOpen} onClose={() => setQrOpen(false)} />

      {isLoading ? (
        <Card>
          <Spin tip="员工统计加载中..." className="w-full py-16">
            <div />
          </Spin>
        </Card>
      ) : isError ? (
        <Alert
          type="error"
          showIcon
          message="员工统计数据加载失败"
          description="请确认后端服务可用后重试；数据仍会每分钟自动刷新。"
          action={<Button size="small" onClick={() => refetch()}>重试</Button>}
        />
      ) : (
        <EmployeeDashboardView stats={stats} />
      )}
    </div>
  )
}

export default function EmployeeDashboardClient() {
  // 看板数据分钟级变化，自建 QueryClient 隔离缓存并支持轮询刷新
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30 * 1000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  )
  return (
    <QueryClientProvider client={queryClient}>
      <EmployeeDashboardInner />
    </QueryClientProvider>
  )
}
