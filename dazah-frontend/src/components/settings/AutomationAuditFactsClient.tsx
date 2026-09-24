'use client'

import { useCallback, useEffect, useState } from 'react'
import { Alert, App, Button, Descriptions, Drawer, Empty, Space, Table, Tabs, Tag, Timeline, Typography } from 'antd'
import { EyeOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  fetchLivzonTaskRun,
  fetchLivzonTaskVersions,
  fetchPlatformLivzonTaskRuns,
  fetchPlatformLivzonTasks,
  type LivzonTaskItem,
  type LivzonTaskRun,
  type LivzonTaskRunDetail,
  type LivzonTaskVersion,
} from '@/lib/api/agent'
import { auditStatusLabel, auditToolLabel } from './auditLabels'

const { Text } = Typography

function formatTime(value?: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

export default function AutomationAuditFactsClient() {
  const { message } = App.useApp()
  const [activeTab, setActiveTab] = useState<'definitions' | 'runs'>('definitions')
  const [definitions, setDefinitions] = useState<LivzonTaskItem[]>([])
  const [runs, setRuns] = useState<LivzonTaskRun[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedDefinition, setSelectedDefinition] = useState<LivzonTaskItem | null>(null)
  const [versions, setVersions] = useState<LivzonTaskVersion[]>([])
  const [selectedRun, setSelectedRun] = useState<LivzonTaskRunDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      if (activeTab === 'definitions') {
        const result = await fetchPlatformLivzonTasks(page, pageSize)
        setDefinitions(result.items)
        setTotal(result.total)
      } else {
        const result = await fetchPlatformLivzonTaskRuns(page, pageSize)
        setRuns(result.items)
        setTotal(result.total)
      }
      setLoadError(null)
    } catch (error) {
      if (activeTab === 'definitions') setDefinitions([])
      else setRuns([])
      setTotal(0)
      setLoadError(error instanceof Error ? error.message : '加载自动化记录失败')
    } finally {
      setLoading(false)
    }
  }, [activeTab, page, pageSize])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timeoutId)
  }, [load])

  const openDefinition = async (item: LivzonTaskItem) => {
    setSelectedDefinition(item)
    setVersions([])
    setDetailLoading(true)
    try {
      setVersions(await fetchLivzonTaskVersions(item.id))
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载版本历史失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const openRun = async (item: LivzonTaskRun) => {
    setSelectedRun(null)
    setDetailLoading(true)
    try {
      setSelectedRun(await fetchLivzonTaskRun(item.id))
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载运行详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const pagination = {
    current: page,
    pageSize,
    total,
    showSizeChanger: true,
    showTotal: (count: number) => `共 ${count} 条`,
    onChange: (nextPage: number, nextPageSize: number) => {
      setPage(nextPageSize === pageSize ? nextPage : 1)
      setPageSize(nextPageSize)
    },
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="m-0 text-[20px] font-semibold">自动化版本与运行</h2>
          <Text type="secondary">查看平台自动化定义的版本变化和实际运行结果。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
      </div>
      {loadError && <Alert type="error" showIcon title="自动化记录加载失败" description={loadError} action={<Button onClick={() => void load()}>重试</Button>} />}
      <Tabs activeKey={activeTab} onChange={(key) => { setActiveTab(key as 'definitions' | 'runs'); setPage(1); setTotal(0) }} items={[
        { key: 'definitions', label: '定义与版本', children: (
          <Table rowKey="id" dataSource={definitions} loading={loading} pagination={pagination} scroll={{ x: 920 }}
            locale={{ emptyText: '暂无自动化定义' }} columns={[
              { title: '自动化', dataIndex: 'name', ellipsis: true },
              { title: '负责人 ID', dataIndex: 'owner_user_id', width: 230, ellipsis: true },
              { title: '状态', dataIndex: 'status', width: 110, render: (value: string) => <Tag>{auditStatusLabel(value)}</Tag> },
              { title: '当前版本', dataIndex: 'active_version', width: 110, render: (value?: number | null) => value ?? '-' },
              { title: '最近运行', dataIndex: 'last_run_at', width: 180, render: formatTime },
              { title: '详情', width: 90, fixed: 'right' as const, render: (_: unknown, item: LivzonTaskItem) => <Button type="link" icon={<EyeOutlined />} onClick={() => void openDefinition(item)}>查看</Button> },
            ]} />
        ) },
        { key: 'runs', label: '运行记录', children: (
          <Table rowKey="id" dataSource={runs} loading={loading} pagination={pagination} scroll={{ x: 940 }}
            locale={{ emptyText: '暂无运行记录' }} columns={[
              { title: '运行 ID', dataIndex: 'id', width: 230, ellipsis: true },
              { title: '自动化 ID', dataIndex: 'automation_id', width: 230, ellipsis: true },
              { title: '状态', dataIndex: 'status', width: 110, render: (value: string) => <Tag color={value === 'succeeded' ? 'success' : value === 'failed' ? 'error' : 'processing'}>{auditStatusLabel(value)}</Tag> },
              { title: '开始时间', dataIndex: 'started_at', width: 180, render: formatTime },
              { title: '失败原因', dataIndex: 'error_message', ellipsis: true, render: (value?: string | null) => value || '-' },
              { title: '详情', width: 90, fixed: 'right' as const, render: (_: unknown, item: LivzonTaskRun) => <Button type="link" icon={<EyeOutlined />} onClick={() => void openRun(item)}>查看</Button> },
            ]} />
        ) },
      ]} />
      <Drawer open={!!selectedDefinition} loading={detailLoading} size="min(860px, 92vw)" title={`${selectedDefinition?.name || ''} · 版本历史`} onClose={() => setSelectedDefinition(null)} destroyOnHidden>
        {versions.length ? <Timeline items={versions.map((version) => ({
          children: <div><Space><Text strong>版本 {version.version}</Text><Text type="secondary">{formatTime(version.created_at)}</Text></Space><div>{version.change_summary || '未填写变更摘要'}</div></div>,
        }))} /> : <Empty description="暂无版本记录" />}
      </Drawer>
      <Drawer open={!!selectedRun} loading={detailLoading} size="min(860px, 92vw)" title="自动化运行详情" onClose={() => setSelectedRun(null)} destroyOnHidden>
        {selectedRun && <div className="space-y-5">
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="运行 ID">{selectedRun.run.id}</Descriptions.Item>
            <Descriptions.Item label="自动化 ID">{selectedRun.run.automation_id}</Descriptions.Item>
            <Descriptions.Item label="结果">{auditStatusLabel(selectedRun.run.status)}</Descriptions.Item>
            <Descriptions.Item label="开始时间">{formatTime(selectedRun.run.started_at)}</Descriptions.Item>
            <Descriptions.Item label="结束时间">{formatTime(selectedRun.run.finished_at)}</Descriptions.Item>
            {selectedRun.run.error_message && <Descriptions.Item label="失败原因">{selectedRun.run.error_message}</Descriptions.Item>}
          </Descriptions>
          <Table rowKey="id" size="small" pagination={false} dataSource={selectedRun.steps} locale={{ emptyText: '暂无步骤记录' }} columns={[
            { title: '步骤', dataIndex: 'step_key' },
            { title: '工具', dataIndex: 'operation', render: (value?: string | null) => value ? <span title={`原始工具标识：${value}`}>{auditToolLabel(value)}</span> : '-' },
            { title: '结果', dataIndex: 'status', render: (value: string) => auditStatusLabel(value) },
            { title: '失败原因', dataIndex: 'error_message', render: (value?: string | null) => value || '-' },
          ]} />
        </div>}
      </Drawer>
    </div>
  )
}
