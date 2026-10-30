'use client'

// 响应时效分布卡：报修→接单时长五档分布（≤5/5-30/30-120/>120/未接单）。
// 五档之和 = 区间内全部工单；未接单档 > 0 红色提示积压。

import { FieldTimeOutlined } from '@ant-design/icons'
import { Typography } from 'antd'
import type { EfficiencyResponseBucket } from '@/types/equipment'

const { Text } = Typography

const BUCKET_COLORS: Record<string, string> = {
  '≤5分钟': '#52c41a',
  '5-30分钟': '#5645d4',
  '30-120分钟': '#fa8c16',
  '>120分钟': '#fa541c',
  '未接单': '#d9d6d1',
}

export function ResponseBucketCard({
  buckets,
  workshopLabel,
}: {
  buckets: EfficiencyResponseBucket[]
  workshopLabel: string
}) {
  const assigned = buckets
    .filter((b) => b.bucket !== '未接单')
    .reduce((acc, b) => acc + b.count, 0)
  const unassigned = buckets.find((b) => b.bucket === '未接单')?.count ?? 0
  const total = assigned + unassigned

  return (
    <section
      style={{
        background: '#ffffff',
        borderRadius: 12,
        border: '1px solid #e5e3df',
        padding: '20px 24px',
      }}
      data-testid="response-bucket-card"
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 14,
        }}
      >
        <FieldTimeOutlined style={{ fontSize: 16, color: '#5645d4' }} />
        <h3 style={{ fontSize: 16, fontWeight: 600, color: '#1a1a1a', margin: 0 }}>
          响应时效分布
        </h3>
        <span style={{ fontSize: 12, color: '#a4a097', marginLeft: 'auto' }}>
          {workshopLabel} · 已接单 {assigned} · 未接单 {unassigned}
        </span>
      </div>

      {total === 0 ? (
        <div
          style={{ padding: '24px 0', textAlign: 'center' }}
          data-testid="response-bucket-empty"
        >
          <Text type="secondary">暂无工单数据</Text>
        </div>
      ) : (
        <>
          {/* 横向堆叠比例条：hover 图例行时对应段高亮（纯 CSS group 不可用，用 title 提示） */}
          <div
            data-testid="response-bucket-bar"
            style={{ display: 'flex', height: 12, borderRadius: 6, overflow: 'hidden' }}
          >
            {buckets.map((b) =>
              b.count > 0 ? (
                <div
                  key={b.bucket}
                  title={`${b.bucket} ${b.count}单`}
                  style={{
                    width: `${b.ratio * 100}%`,
                    background: BUCKET_COLORS[b.bucket] ?? '#d9d6d1',
                  }}
                />
              ) : null,
            )}
          </div>
          <div style={{ marginTop: 12 }}>
            {buckets.map((b) => (
              <div
                key={b.bucket}
                data-testid="response-bucket-legend"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '4px 0',
                }}
              >
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: 2,
                    background: BUCKET_COLORS[b.bucket] ?? '#d9d6d1',
                    flexShrink: 0,
                  }}
                />
                <Text style={{ fontSize: 13, width: 84 }}>{b.bucket}</Text>
                <Text
                  strong
                  style={{
                    fontSize: 13,
                    width: 44,
                    textAlign: 'right',
                    fontFeatureSettings: '"tnum"',
                    color:
                      b.bucket === '未接单' && b.count > 0
                        ? '#e03131'
                        : undefined,
                  }}
                >
                  {b.count}单
                </Text>
                <Text type="secondary" style={{ fontSize: 12, width: 48, textAlign: 'right' }}>
                  {Math.round(b.ratio * 100)}%
                </Text>
                <span style={{ flex: 1 }} />
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
