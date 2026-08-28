'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Input,
  Progress,
  Space,
  Statistic,
  Table,
  Tag,
} from 'antd'
import type { TableProps } from 'antd'
import { ReloadOutlined, SearchOutlined, SyncOutlined } from '@ant-design/icons'
import { fetchMaterialCatalog, fetchMaterialSourceConfig } from '@/lib/api/purchasing'
import type {
  MaterialCatalogListMeta,
  MaterialCatalogRecordResponse,
} from '@/types/purchasing'
import {
  MATERIAL_SYNC_POLL_INTERVAL_MS,
  formatMaterialSyncCompletedMessage,
  formatMaterialSyncProgress,
} from './ProcurementMaterialSourceSettingsClient'

const DEFAULT_PAGE_SIZE = 20

type MaterialLibraryClientProps = {
  initialRecords: MaterialCatalogRecordResponse[]
  initialMeta: MaterialCatalogListMeta
  initialLoadFailed?: boolean
}

function syncStatusTag(status: string) {
  if (status === 'success') return <Tag color="success">同步成功</Tag>
  if (status === 'syncing') return <Tag color="processing">同步中</Tag>
  if (status === 'error') return <Tag color="error">同步失败</Tag>
  return <Tag>未同步</Tag>
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN')
}

export function MaterialLibraryClient({
  initialRecords,
  initialMeta,
  initialLoadFailed = false,
}: MaterialLibraryClientProps) {
  const { message } = App.useApp()
  const [records, setRecords] = useState(initialRecords)
  const [meta, setMeta] = useState(initialMeta)
  const [page, setPage] = useState(initialMeta.page)
  const [keyword, setKeyword] = useState('')
  const [materialCode, setMaterialCode] = useState('')
  const [materialDescription, setMaterialDescription] = useState('')
  const [ruleModel, setRuleModel] = useState('')
  const [loading, setLoading] = useState(false)

  const loadRecords = useCallback(
    async (nextPage = page, resetFilters = false) => {
      setLoading(true)
      try {
        const response = await fetchMaterialCatalog({
          keyword: resetFilters ? undefined : keyword || undefined,
          material_code: resetFilters ? undefined : materialCode || undefined,
          material_description: resetFilters
            ? undefined
            : materialDescription || undefined,
          rule_model: resetFilters ? undefined : ruleModel || undefined,
          page: nextPage,
          page_size: DEFAULT_PAGE_SIZE,
        })
        setRecords(response.data ?? [])
        setMeta(response.meta)
        setPage(nextPage)
      } catch {
        message.error('物料编码库加载失败，请稍后重试')
      } finally {
        setLoading(false)
      }
    },
    [page, keyword, materialCode, materialDescription, ruleModel, message],
  )

  useEffect(() => {
    if (meta.sync_status !== 'syncing') {
      return
    }
    const timer = setInterval(async () => {
      try {
        const response = await fetchMaterialSourceConfig()
        if (response.code !== 200 || !response.data) {
          return
        }
        const next = response.data
        setMeta((current) => ({
          ...current,
          sync_status: next.sync_status,
          sync_error: next.sync_error,
          last_synced_at: next.last_synced_at,
          last_sync_record_count: next.last_sync_record_count,
          sync_total_records: next.sync_total_records,
          sync_fetched_count: next.sync_fetched_count,
        }))
        if (next.sync_status !== 'syncing') {
          if (next.sync_status === 'success') {
            message.success(
              formatMaterialSyncCompletedMessage(next.last_sync_record_count ?? 0),
            )
          } else if (next.sync_status === 'error') {
            message.error(next.sync_error || '采购物料数据同步失败')
          }
          void loadRecords()
        }
      } catch {
        // 轮询失败时保持当前状态，等待下一次轮询
      }
    }, MATERIAL_SYNC_POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [meta.sync_status, message, loadRecords])

  const handleReset = () => {
    setKeyword('')
    setMaterialCode('')
    setMaterialDescription('')
    setRuleModel('')
    void loadRecords(1, true)
  }

  const columns = useMemo<TableProps<MaterialCatalogRecordResponse>['columns']>(
    () => [
      {
        title: '物料编码',
        dataIndex: 'material_code',
        key: 'material_code',
        width: 200,
        fixed: 'left',
        ellipsis: true,
      },
      {
        title: '物料说明',
        dataIndex: 'material_description',
        key: 'material_description',
        width: 280,
        ellipsis: true,
      },
      {
        title: '规格型号',
        dataIndex: 'rule_model',
        key: 'rule_model',
        width: 220,
        ellipsis: true,
      },
      {
        title: '主要单位',
        dataIndex: 'material_unit',
        key: 'material_unit',
        width: 110,
        ellipsis: true,
      },
      {
        title: '物料模板',
        dataIndex: 'material_template',
        key: 'material_template',
        width: 140,
        ellipsis: true,
      },
      {
        title: '物料大类',
        dataIndex: 'material_category',
        key: 'material_category',
        width: 130,
        ellipsis: true,
      },
      {
        title: '物料小类',
        dataIndex: 'material_subcategory',
        key: 'material_subcategory',
        width: 130,
        ellipsis: true,
      },
      {
        title: '物料成本大类',
        dataIndex: 'material_cost_category',
        key: 'material_cost_category',
        width: 130,
        ellipsis: true,
      },
      {
        title: '最近同步',
        dataIndex: 'last_synced_at',
        key: 'last_synced_at',
        width: 180,
        render: (value: string | null | undefined) => formatDateTime(value),
      },
    ],
    [],
  )

  const syncFetched = meta.sync_fetched_count ?? 0
  const syncTotal = meta.sync_total_records
  const syncPercent =
    syncTotal && syncTotal > 0
      ? Math.min(100, Math.round((syncFetched / syncTotal) * 100))
      : undefined

  const emptyText = meta.sync_status === 'not_synced'
    ? '尚未同步物料数据，请管理员前往采购设置执行同步'
    : '当前筛选条件下暂无物料记录'

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-[13px] text-[var(--color-stone)]">采购管理 / 物料编码库</p>
          <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">
            物料编码库
          </h1>
          <p className="max-w-[760px] text-[14px] leading-6 text-[var(--color-steel)]">
            展示采购设置中已保存的飞书多维表格同步到本地的物料数据，支持按编码、说明和规格型号查询。
          </p>
        </div>
        <Button
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={() => void loadRecords(page)}
        >
          刷新
        </Button>
      </div>

      {initialLoadFailed && (
        <Alert
          showIcon
          type="warning"
          message="物料编码库暂时无法加载"
          description="请确认后端服务和数据库迁移已完成；如果尚未同步，请联系管理员在采购设置中执行同步。"
        />
      )}

      <div className="grid gap-3 md:grid-cols-3">
        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4">
          <Statistic title="物料记录" value={meta.total} suffix="条" />
        </section>
        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4">
          <p className="text-[13px] text-[var(--color-stone)]">数据状态</p>
          <div className="mt-2">
            {syncStatusTag(meta.sync_status)}
            {meta.sync_status === 'syncing' && (
              <div className="mt-2">
                <div className="flex items-center gap-1.5">
                  <SyncOutlined spin className="text-[var(--color-primary)]" />
                  <span className="text-[12px] text-[var(--color-steel)]">
                    {formatMaterialSyncProgress(syncFetched, syncTotal)}
                  </span>
                </div>
                {syncTotal && syncTotal > 0 && (
                  <Progress
                    percent={syncPercent}
                    status="active"
                    size="small"
                    className="mt-1.5"
                  />
                )}
              </div>
            )}
          </div>
        </section>
        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4">
          <p className="text-[13px] text-[var(--color-stone)]">最近同步时间</p>
          <p className="mt-2 text-[16px] font-semibold text-[var(--color-charcoal)]">
            {formatDateTime(meta.last_synced_at)}
          </p>
        </section>
      </div>

      {meta.sync_status === 'error' && meta.sync_error && (
        <Alert
          showIcon
          type="error"
          message="最近一次同步失败"
          description={meta.sync_error}
        />
      )}

      <Card>
        <div className="mb-4 grid gap-3 border-b border-[var(--color-hairline)] bg-[var(--color-surface-soft)] p-4 lg:grid-cols-[minmax(220px,1.4fr)_minmax(160px,1fr)_minmax(180px,1fr)_minmax(160px,1fr)_auto]">
          <Input.Search
            allowClear
            enterButton={<SearchOutlined />}
            placeholder="搜索编码、说明或规格型号"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onSearch={() => void loadRecords(1)}
          />
          <Input
            allowClear
            placeholder="物料编码"
            value={materialCode}
            onChange={(event) => setMaterialCode(event.target.value)}
            onPressEnter={() => void loadRecords(1)}
          />
          <Input
            allowClear
            placeholder="物料说明"
            value={materialDescription}
            onChange={(event) => setMaterialDescription(event.target.value)}
            onPressEnter={() => void loadRecords(1)}
          />
          <Input
            allowClear
            placeholder="规格型号"
            value={ruleModel}
            onChange={(event) => setRuleModel(event.target.value)}
            onPressEnter={() => void loadRecords(1)}
          />
          <Space>
            <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={() => void loadRecords(1)}>
              查询
            </Button>
            <Button onClick={handleReset}>重置</Button>
          </Space>
        </div>

        <Table<MaterialCatalogRecordResponse>
          columns={columns}
          dataSource={records}
          loading={loading}
          rowKey="id"
          scroll={{ x: 860 }}
          locale={{ emptyText }}
          pagination={{
            current: page,
            pageSize: DEFAULT_PAGE_SIZE,
            total: meta.total,
            showSizeChanger: false,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (nextPage) => void loadRecords(nextPage),
          }}
        />
      </Card>
    </div>
  )
}
