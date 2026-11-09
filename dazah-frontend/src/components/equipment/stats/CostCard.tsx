'use client'

// 维修成本卡（方案C）：三段成本汇总 + TOP5 分组（设备/车间/故障类型切换）。
// 数据来自 GET /maintenance/work-orders/cost-report。

import { useCallback, useEffect, useState } from 'react'
import { PayCircleOutlined } from '@ant-design/icons'
import { Segmented, Spin, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { CostReport, CostReportBucket } from '@/types/equipment'
import { fetchCostReportClient } from '@/lib/api/equipment-client'

type GroupBy = 'equipment' | 'workshop' | 'fault_type'

const GROUP_LABEL: Record<GroupBy, string> = {
  equipment: '按设备',
  workshop: '按车间',
  fault_type: '按故障类型',
}

const BUCKET_TITLE: Record<GroupBy, string> = {
  equipment: '设备',
  workshop: '车间',
  fault_type: '故障类型',
}

export function CostCard() {
  const [report, setReport] = useState<CostReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [groupBy, setGroupBy] = useState<GroupBy>('equipment')

  const load = useCallback(
    async (g: GroupBy) => {
      const data = await fetchCostReportClient({ group_by: g }).catch(() => null)
      setReport(data)
      setFailed(data === null)
      setLoading(false)
    },
    [],
  )

  useEffect(() => {
    void load(groupBy)
  }, [groupBy, load])

  const columns: ColumnsType<CostReportBucket> = [
    { title: BUCKET_TITLE[groupBy], dataIndex: 'label', key: 'label', ellipsis: true },
    { title: '工单', dataIndex: 'orders', key: 'orders', width: 60 },
    { title: '备件', dataIndex: 'spare_cost', key: 'spare_cost', width: 90, render: (v: number) => `¥${v.toFixed(0)}` },
    { title: '工时', dataIndex: 'labor_cost', key: 'labor_cost', width: 90, render: (v: number) => `¥${v.toFixed(0)}` },
    { title: '外委', dataIndex: 'external_cost', key: 'external_cost', width: 90, render: (v: number) => `¥${v.toFixed(0)}` },
    { title: '合计', dataIndex: 'total_cost', key: 'total_cost', width: 100, render: (v: number) => <b>{`¥${v.toFixed(0)}`}</b> },
  ]

  const t = report?.totals

  return (
    <section
      style={{
        background: '#ffffff',
        borderRadius: 12,
        border: '1px solid #e5e3df',
        padding: '20px 24px',
      }}
      data-testid="maintenance-cost-card"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <PayCircleOutlined style={{ fontSize: 16, color: '#5645d4' }} />
        <span style={{ fontSize: 15, fontWeight: 600 }}>维修成本</span>
        <span style={{ color: '#8a867d', fontSize: 12 }}>
          {report ? `${report.month} 月` : ''}
        </span>
        <div style={{ marginLeft: 'auto' }}>
          <Segmented<GroupBy>
            value={groupBy}
            onChange={(v) => {
              setLoading(true)
              setGroupBy(v)
            }}
            options={(Object.keys(GROUP_LABEL) as GroupBy[]).map((g) => ({
              label: GROUP_LABEL[g],
              value: g,
            }))}
          />
        </div>
      </div>

      <Spin spinning={loading}>
        {failed ? (
          <div style={{ color: '#8a867d', fontSize: 13, padding: '12px 0' }}>成本报表加载失败</div>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12, color: '#5d5b54' }}>
                本月工单 <b>{t?.orders ?? 0}</b> 单
              </span>
              <span style={{ fontSize: 12, color: '#5d5b54' }}>
                备件 <b>¥{(t?.spare_cost ?? 0).toFixed(0)}</b>
              </span>
              <span style={{ fontSize: 12, color: '#5d5b54' }}>
                工时 <b>¥{(t?.labor_cost ?? 0).toFixed(0)}</b>
              </span>
              <span style={{ fontSize: 12, color: '#5d5b54' }}>
                外委 <b>¥{(t?.external_cost ?? 0).toFixed(0)}</b>
              </span>
              <span style={{ fontSize: 14, color: '#1a1a1a', fontWeight: 700 }}>
                合计 ¥{(t?.total_cost ?? 0).toFixed(0)}
              </span>
            </div>
            <Table<CostReportBucket>
              size="small"
              rowKey="label"
              columns={columns}
              dataSource={(report?.top ?? []).slice(0, 5)}
              pagination={false}
              locale={{ emptyText: '本月暂无工单成本数据' }}
            />
          </>
        )}
      </Spin>
    </section>
  )
}
