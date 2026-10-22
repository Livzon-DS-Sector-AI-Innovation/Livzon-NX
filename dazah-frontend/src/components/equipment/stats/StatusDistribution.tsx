'use client'

import type {
  EquipmentStatistics,
} from '@/types/equipment'

// ============================================================
// 设备状态分布条
// ============================================================
const statusColorMap: Record<string, string> = {
  '在用': 'var(--color-success)',
  '备用': '#0075de',
  '维修中': '#dd5b00',
  '停用': 'var(--color-stone)',
  '报废': '#c8c4be',
}

export function StatusDistribution({ statistics }: { statistics: EquipmentStatistics }) {
  const total = statistics.total || 1
  const entries = Object.entries(statistics.by_status)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])

  if (entries.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-stone)', fontSize: 14 }}>
        暂无设备数据
      </div>
    )
  }

  return (
    <div>
      {/* 层叠条 */}
      <div
        style={{
          display: 'flex',
          height: 12,
          borderRadius: 6,
          overflow: 'hidden',
          marginBottom: 20,
          background: 'var(--color-surface-soft)',
        }}
      >
        {entries.map(([status, count]) => (
          <div
            key={status}
            style={{
              width: `${(count / total) * 100}%`,
              background: statusColorMap[status] || '#c8c4be',
              transition: 'width 0.8s cubic-bezier(0.22, 0.61, 0.36, 1)',
              minWidth: count > 0 ? 4 : 0,
            }}
            title={`${status}: ${count}`}
          />
        ))}
      </div>

      {/* 图例列表 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {entries.map(([status, count], i) => {
          const pct = ((count / total) * 100).toFixed(1)
          return (
            <div
              key={status}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                animation: `fadeInUp 0.4s ease both`,
                animationDelay: `${i * 60}ms`,
              }}
            >
              <div
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: 3,
                  background: statusColorMap[status] || '#c8c4be',
                  flexShrink: 0,
                }}
              />
              <span style={{ flex: 1, fontSize: 14, color: 'var(--color-ink)', fontWeight: 500 }}>
                {status}
              </span>
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-ink)', fontFeatureSettings: '"tnum"' }}>
                {count}
              </span>
              <span style={{ fontSize: 13, color: 'var(--color-stone)', width: 48, textAlign: 'right', fontFeatureSettings: '"tnum"' }}>
                {pct}%
              </span>
              {/* 微型进度条 */}
              <div style={{ width: 80, height: 4, borderRadius: 2, background: 'var(--color-surface-soft)', overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%',
                    width: `${pct}%`,
                    background: statusColorMap[status] || '#c8c4be',
                    borderRadius: 2,
                    transition: 'width 1s ease',
                  }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
