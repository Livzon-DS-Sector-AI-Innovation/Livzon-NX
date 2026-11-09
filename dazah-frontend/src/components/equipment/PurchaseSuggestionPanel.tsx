'use client'

// 备件采购建议面板（方案C）：列表 + 批量提交采购 + 登记到货 + 取消。
// 数据来自 GET /spare-parts/purchase-suggestions；写操作走 Server Actions。

import { useCallback, useEffect, useState } from 'react'
import { App, Button, InputNumber, Popconfirm, Select, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { PurchaseSuggestion, PurchaseSuggestionStatus } from '@/types/equipment'
import { fetchPurchaseSuggestionsClient } from '@/lib/api/equipment-client'
import {
  cancelPurchaseSuggestion,
  registerSuggestionArrival,
  submitPurchaseSuggestions,
  updateSuggestionQty,
} from '@/actions/equipment'

const STATUS_TAG: Record<PurchaseSuggestionStatus, { color: string; label: string }> = {
  suggested: { color: 'orange', label: '待提交' },
  submitted: { color: 'blue', label: '已提交采购' },
  partial: { color: 'gold', label: '部分到货' },
  done: { color: 'green', label: '已完成' },
  cancelled: { color: 'default', label: '已取消' },
}

export function PurchaseSuggestionPanel({ workshopCode }: { workshopCode: string }) {
  const { message, modal } = App.useApp()
  const [items, setItems] = useState<PurchaseSuggestion[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<PurchaseSuggestionStatus | undefined>(undefined)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  // 所有 setState 都在首个 await 之后（避免 effect 内同步 setState）
  const load = useCallback(async () => {
    const res = await fetchPurchaseSuggestionsClient({
      status: statusFilter,
      workshop: workshopCode || undefined,
      page: 1,
      page_size: 100,
    }).catch(() => null)
    setItems(res?.items ?? [])
    setTotal(res?.total ?? 0)
    setLoading(false)
    setSelectedIds([])
  }, [statusFilter, workshopCode])

  useEffect(() => {
    void load()
  }, [load])

  const handleBatchSubmit = async () => {
    if (selectedIds.length === 0) return
    setSubmitting(true)
    try {
      const result = (await submitPurchaseSuggestions(selectedIds)) as {
        submitted?: number
        failed?: Array<{ reason: string }>
        purchase_request_id?: string
      } | null
      const ok = result?.submitted ?? 0
      const failed = result?.failed ?? []
      if (ok > 0) {
        message.success(
          `已提交 ${ok} 条${result?.purchase_request_id ? `（采购申请 ${result.purchase_request_id.slice(0, 8)}…）` : ''}`,
        )
      }
      if (failed.length > 0) {
        message.warning(`${failed.length} 条未提交：${failed[0].reason}`)
      }
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '提交采购失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleArrival = (record: PurchaseSuggestion) => {
    let qty = record.suggest_qty - record.arrived_qty
    modal.confirm({
      title: `登记到货：${record.spare_part_name ?? ''}`,
      content: (
        <div style={{ paddingTop: 8 }}>
          建议采购 {record.suggest_qty} {record.unit ?? ''}，已到 {record.arrived_qty}。
          <InputNumber
            min={1}
            defaultValue={Math.max(1, qty)}
            style={{ marginLeft: 8 }}
            onChange={(v) => {
              qty = v ?? 1
            }}
          />
        </div>
      ),
      okText: `入库 ${''}`,
      onOk: async () => {
        try {
          await registerSuggestionArrival(record.id, qty)
          message.success('到货已入库')
          await load()
        } catch (e) {
          message.error(e instanceof Error ? e.message : '登记到货失败')
        }
      },
    })
  }

  const columns: ColumnsType<PurchaseSuggestion> = [
    {
      title: '备件',
      key: 'part',
      width: 200,
      ellipsis: true,
      render: (_: unknown, r) => (
        <span>
          {r.spare_part_name ?? '-'}
          <span style={{ color: '#8a867d', marginLeft: 6, fontSize: 12 }}>{r.spare_part_code ?? ''}</span>
        </span>
      ),
    },
    { title: '库存/安全线', key: 'qty', width: 110, render: (_: unknown, r) => `${r.current_qty} / ${r.safety_qty}` },
    {
      title: '建议数量',
      dataIndex: 'suggest_qty',
      key: 'suggest_qty',
      width: 130,
      render: (v: number, r) =>
        r.status === 'suggested' ? (
          <InputNumber
            size="small"
            min={1}
            value={v}
            onChange={async (nv) => {
              if (nv && nv !== v) {
                try {
                  await updateSuggestionQty(r.id, nv)
                  message.success('数量已更新')
                  await load()
                } catch {
                  message.error('更新数量失败')
                }
              }
            }}
          />
        ) : (
          <span>{v}</span>
        ),
    },
    { title: '已到货', dataIndex: 'arrived_qty', key: 'arrived_qty', width: 80 },
    {
      title: '参考单价',
      dataIndex: 'unit_price',
      key: 'unit_price',
      width: 90,
      render: (v: number | null) => (v != null ? `¥${v}` : '-'),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: PurchaseSuggestionStatus) => (
        <Tag color={STATUS_TAG[s].color}>{STATUS_TAG[s].label}</Tag>
      ),
    },
    {
      title: '采购回执',
      dataIndex: 'purchase_ref',
      key: 'purchase_ref',
      width: 150,
      ellipsis: true,
      render: (v: string | null) => v || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: unknown, r) => (
        <Space size={4}>
          {(r.status === 'submitted' || r.status === 'partial') && (
            <Button size="small" onClick={() => handleArrival(r)}>
              登记到货
            </Button>
          )}
          {['suggested', 'submitted', 'partial'].includes(r.status) && (
            <Popconfirm
              title="确认取消该采购建议？"
              onConfirm={async () => {
                try {
                  await cancelPurchaseSuggestion(r.id)
                  message.success('已取消')
                  await load()
                } catch (e) {
                  message.error(e instanceof Error ? e.message : '取消失败')
                }
              }}
            >
              <Button size="small" danger>
                取消
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div data-testid="purchase-suggestion-panel">
      <div style={{ display: 'flex', gap: 12, marginBottom: 12, alignItems: 'center' }}>
        <Select<PurchaseSuggestionStatus | undefined>
          allowClear
          placeholder="状态筛选"
          style={{ width: 140 }}
          value={statusFilter}
          onChange={(v) => {
            setLoading(true)
            setStatusFilter(v)
          }}
          options={Object.entries(STATUS_TAG).map(([value, v]) => ({
            value: value as PurchaseSuggestionStatus,
            label: v.label,
          }))}
        />
        <span style={{ color: '#8a867d', fontSize: 12 }}>共 {total} 条</span>
        <Button
          type="primary"
          loading={submitting}
          disabled={selectedIds.length === 0}
          onClick={handleBatchSubmit}
        >
          提交采购（{selectedIds.length}）
        </Button>
      </div>
      <Table<PurchaseSuggestion>
        size="small"
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={items}
        pagination={false}
        scroll={{ x: 'max-content' }}
        rowSelection={{
          selectedRowKeys: selectedIds,
          onChange: (keys) => setSelectedIds(keys as string[]),
          getCheckboxProps: (r) => ({ disabled: r.status !== 'suggested' }),
        }}
        locale={{ emptyText: '暂无采购建议（库存均处于安全线以上，或每日 07:30 自动扫描生成）' }}
      />
    </div>
  )
}
