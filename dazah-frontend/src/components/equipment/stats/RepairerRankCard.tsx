'use client'

// 维修人员排行卡：接单数 TOP5 + 均响应/均修复，随效能卡车间联动。
// 数据来自 GET /efficiency 的 repairer_ranking，无独立请求。

import { TeamOutlined } from '@ant-design/icons'
import { Typography } from 'antd'
import type { EfficiencyRepairerRank } from '@/types/equipment'
import { fmtMinutes } from './efficiency-format'

const { Text } = Typography

export function RepairerRankCard({
  ranking,
  workshopLabel,
}: {
  ranking: EfficiencyRepairerRank[]
  workshopLabel: string
}) {
  const total = ranking.reduce((acc, r) => acc + r.order_count, 0)

  return (
    <section
      style={{
        background: '#ffffff',
        borderRadius: 12,
        border: '1px solid #e5e3df',
        padding: '20px 24px',
      }}
      data-testid="repairer-rank-card"
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 14,
        }}
      >
        <TeamOutlined style={{ fontSize: 16, color: '#5645d4' }} />
        <h3 style={{ fontSize: 16, fontWeight: 600, color: '#1a1a1a', margin: 0 }}>
          维修人员排行
        </h3>
        <span style={{ fontSize: 12, color: '#a4a097', marginLeft: 'auto' }}>
          {workshopLabel}
        </span>
      </div>

      {ranking.length === 0 ? (
        <div
          style={{ padding: '24px 0', textAlign: 'center' }}
          data-testid="repairer-rank-empty"
        >
          <Text type="secondary">暂无接单数据</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>
            维修人员接单后展示排行
          </Text>
        </div>
      ) : (
        <>
          {ranking.map((r, i) => (
            <div
              key={r.assignee_id}
              data-testid="repairer-rank-row"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '8px 10px',
                borderRadius: 8,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#faf9f8'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent'
              }}
            >
              <span
                style={{
                  width: 22,
                  fontSize: 13,
                  fontWeight: 700,
                  textAlign: 'center',
                  color: i < 3 ? '#fa541c' : '#a4a097',
                  flexShrink: 0,
                }}
              >
                {i + 1}
              </span>
              <Text strong style={{ fontSize: 14, width: 76, flexShrink: 0 }} ellipsis>
                {r.assignee_name}
              </Text>
              <span style={{ flex: 1, textAlign: 'center' }}>
                <Text
                  strong
                  style={{
                    fontSize: 20,
                    color: i === 0 ? '#fa541c' : '#1a1a1a',
                    fontFeatureSettings: '"tnum"',
                  }}
                >
                  {r.order_count}
                </Text>
                <Text type="secondary" style={{ fontSize: 12, marginLeft: 2 }}>
                  单
                </Text>
              </span>
              <span style={{ textAlign: 'right', minWidth: 88 }}>
                <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                  均响应 {fmtMinutes(r.avg_response_minutes)}
                </Text>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  均修复 {fmtMinutes(r.avg_repair_minutes)}
                </Text>
              </span>
            </div>
          ))}
          <div style={{ marginTop: 8, textAlign: 'right' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              共 {ranking.length} 人接单 · 合计 {total} 单
            </Text>
          </div>
        </>
      )}
    </section>
  )
}
