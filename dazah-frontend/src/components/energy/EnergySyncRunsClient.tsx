'use client'

import { ReloadOutlined, SyncOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Empty, Space, Table, Tag } from 'antd'
import { triggerEnergySync } from '@/actions/energy'
import { fetchEnergySyncRuns, type EnergySyncRun } from '@/lib/api/energy'

export function EnergySyncRunsClient() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const runsQuery = useQuery({ queryKey: ['energy-sync-runs'], queryFn: () => fetchEnergySyncRuns({ page: 1, page_size: 100 }) })
  const syncMutation = useMutation({
    mutationFn: () => triggerEnergySync({ force: true }),
    onSuccess: (run) => {
      message.success(run.status === 'success' ? '同步完成' : '同步已结束，请检查状态')
      void queryClient.invalidateQueries({ queryKey: ['energy-sync-runs'] })
      void queryClient.invalidateQueries({ queryKey: ['energy-sources'] })
    },
    onError: (error: Error) => message.error(error.message),
  })

  const status = (value: string) => <Tag color={value === 'success' ? 'green' : value === 'partial' ? 'orange' : value === 'failed' ? 'red' : 'blue'}>{value}</Tag>

  return (
    <main style={{ maxWidth: 1280, margin: '0 auto', padding: '28px 32px 48px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0, color: '#1a1a1a', fontSize: 28, fontWeight: 600 }}>同步运行记录</h1>
          <p style={{ margin: '6px 0 0', color: '#787671' }}>查看自动与手动同步的执行范围、快照数量和脱敏错误信息。</p>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => runsQuery.refetch()} loading={runsQuery.isFetching}>刷新</Button>
          <Button type="primary" icon={<SyncOutlined />} onClick={() => syncMutation.mutate()} loading={syncMutation.isPending}>立即重试</Button>
        </Space>
      </div>
      <Card style={{ marginTop: 24 }}>
        {runsQuery.isError ? <Empty description={(runsQuery.error as Error).message || '运行记录读取失败'} /> : (
          <Table<EnergySyncRun>
            loading={runsQuery.isLoading}
            rowKey="id"
            dataSource={runsQuery.data?.data}
            pagination={{ total: Number(runsQuery.data?.meta?.total ?? 0), pageSize: 20, showSizeChanger: false }}
            scroll={{ x: 960 }}
            columns={[
              { title: '开始时间', dataIndex: 'started_at', width: 180, render: (value) => new Date(value).toLocaleString() },
              { title: '触发方式', dataIndex: 'trigger_type', width: 100 },
              { title: '状态', dataIndex: 'status', width: 100, render: status },
              { title: '文档 / 工作表', key: 'source', render: (_, record) => `${record.document_count} / ${record.sheet_count}` },
              { title: '新增快照', dataIndex: 'snapshot_count', width: 100 },
              { title: '事实数据', dataIndex: 'fact_count', width: 100 },
              { title: '错误数', dataIndex: 'error_count', width: 90 },
              { title: '错误摘要', dataIndex: 'error_message', ellipsis: true },
            ]}
          />
        )}
      </Card>
    </main>
  )
}
