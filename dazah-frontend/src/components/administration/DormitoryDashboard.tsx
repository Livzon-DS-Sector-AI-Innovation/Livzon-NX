'use client'

import { useState } from 'react'

import { Button, Card, Drawer, Space, Statistic, Table, Typography } from 'antd'
import { ReloadOutlined, UserAddOutlined } from '@ant-design/icons'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'

import PlatformNotice from '@/components/shared/PlatformNotice'
import { fetchDormitoryStats } from '@/lib/api/mapped-feishu'
import type { DormitoryRoomSummary } from '@/types/administration'

import DormitoryCheckinModal from './DormitoryCheckinModal'

const MODULE_CODE = 'administration'

const ROOM_COLUMNS = [
  { title: '宿舍编号', dataIndex: 'room_no', key: 'room_no', width: 110 },
  { title: '宿舍类型', dataIndex: 'dorm_type', key: 'dorm_type', width: 100 },
  { title: '房间类型', dataIndex: 'room_type', key: 'room_type', width: 100 },
  { title: '床位数量', dataIndex: 'bed_count', key: 'bed_count', width: 90, align: 'center' as const },
  { title: '已住人数', dataIndex: 'occupied', key: 'occupied', width: 90, align: 'center' as const },
  { title: '剩余床位', dataIndex: 'vacant', key: 'vacant', width: 90, align: 'center' as const },
]

/** 固定东八区，避免 SSR（UTC 容器）与浏览器输出不一致导致水合不匹配。 */
function formatSyncedAt(value: string | null | undefined): string {
  if (!value) return '尚未同步'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '尚未同步'
    : date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}

interface DormitoryDashboardProps {
  /** 办理入住成功后由弹窗触发；父级刷新台账数据。 */
  onCheckinSuccess?: () => void
}

/** 宿舍入住率简易仪表盘：总房间/空房/满人 + 点击查看房间列表 + 入住办理入口。 */
function DormitoryDashboardContent({ onCheckinSuccess }: DormitoryDashboardProps) {
  const [drawer, setDrawer] = useState<'empty' | 'full' | null>(null)
  const [checkinOpen, setCheckinOpen] = useState(false)
  const statsQuery = useQuery({
    queryKey: ['dormitory-dashboard-stats', MODULE_CODE],
    queryFn: () => fetchDormitoryStats(MODULE_CODE),
    staleTime: 30_000,
    refetchInterval: 120_000,
    retry: 1,
  })
  const stats = statsQuery.data

  if (statsQuery.isError) {
    return (
      <PlatformNotice
        type="error"
        title={(statsQuery.error as Error).message || '读取宿舍入住统计失败'}
      />
    )
  }

  const drawerTitle = drawer === 'empty' ? '空房间列表' : '满人房间列表'
  const drawerRooms: DormitoryRoomSummary[] =
    drawer === 'empty' ? (stats?.empty_room_list ?? []) : (stats?.full_room_list ?? [])

  return (
    <Card size="small" className="mb-5" loading={statsQuery.isLoading && !stats}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Space size={8} wrap>
          <Typography.Text strong>宿舍入住概览</Typography.Text>
          <Typography.Text type="secondary" className="text-xs">
            数据截至 {formatSyncedAt(stats?.synced_at)}
          </Typography.Text>
        </Space>
        <Space size={8}>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => statsQuery.refetch()}
            loading={statsQuery.isFetching}
          >
            刷新
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<UserAddOutlined />}
            onClick={() => setCheckinOpen(true)}
          >
            新员工入住
          </Button>
        </Space>
      </div>
      <div className="flex flex-wrap gap-3">
        <div className="min-w-[110px] flex-1 rounded border border-[var(--color-hairline)] p-3">
          <Statistic title="总房间" value={stats?.total_rooms ?? 0} />
          <Typography.Text type="secondary" className="text-xs">
            床位 {stats?.total_beds ?? 0} 张
          </Typography.Text>
        </div>
        <button
          type="button"
          onClick={() => setDrawer('empty')}
          className="min-w-[110px] flex-1 cursor-pointer rounded border border-[var(--color-hairline)] p-3 text-left transition-colors hover:border-[var(--color-hairline-strong,var(--color-hairline))]"
        >
          <Statistic title="空房间" value={stats?.empty_rooms ?? 0} styles={{ content: { color: "#52c41a" } }} />
          <Typography.Text type="secondary" className="text-xs">
            点击查看房间 →
          </Typography.Text>
        </button>
        <div className="min-w-[110px] flex-1 rounded border border-[var(--color-hairline)] p-3">
          <Statistic title="未住满" value={stats?.partial_rooms ?? 0} />
          <Typography.Text type="secondary" className="text-xs">
            还有空床位
          </Typography.Text>
        </div>
        <button
          type="button"
          onClick={() => setDrawer('full')}
          className="min-w-[110px] flex-1 cursor-pointer rounded border border-[var(--color-hairline)] p-3 text-left transition-colors hover:border-[var(--color-hairline-strong,var(--color-hairline))]"
        >
          <Statistic title="满人房间" value={stats?.full_rooms ?? 0} styles={{ content: { color: "#faad14" } }} />
          <Typography.Text type="secondary" className="text-xs">
            点击查看房间 →
          </Typography.Text>
        </button>
        <div className="min-w-[110px] flex-1 rounded border border-[var(--color-hairline)] p-3">
          <Statistic
            title="床位入住率"
            value={Math.round((stats?.occupancy_rate ?? 0) * 100)}
            suffix="%"
          />
          <Typography.Text type="secondary" className="text-xs">
            已住 {stats?.occupied_beds ?? 0} 张
          </Typography.Text>
        </div>
      </div>
      {stats && stats.total_rooms === 0 ? (
        <Typography.Text type="secondary" className="mt-3 block text-xs">
          宿舍清单暂无数据：请确认已在「飞书设置」绑定宿舍清单并完成同步。
        </Typography.Text>
      ) : null}

      <Drawer
        title={drawerTitle}
        open={drawer !== null}
        onClose={() => setDrawer(null)}
        size="large"
      >
        <Table
          size="small"
          rowKey="room_no"
          columns={ROOM_COLUMNS}
          dataSource={drawerRooms}
          pagination={false}
        />
      </Drawer>

      {checkinOpen ? (
        <DormitoryCheckinModal
          open={checkinOpen}
          onClose={() => setCheckinOpen(false)}
          onCheckedin={() => {
            statsQuery.refetch()
            onCheckinSuccess?.()
          }}
        />
      ) : null}
    </Card>
  )
}

/** 应用根上没有全局 QueryClientProvider（MappedDatasetPage 同款：组件自带）。 */
export default function DormitoryDashboard(props: DormitoryDashboardProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, retry: 1 },
        },
      }),
  )
  return (
    <QueryClientProvider client={queryClient}>
      <DormitoryDashboardContent {...props} />
    </QueryClientProvider>
  )
}

