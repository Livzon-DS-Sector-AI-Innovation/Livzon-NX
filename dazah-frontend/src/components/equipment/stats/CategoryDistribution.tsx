'use client'

import {
} from '@ant-design/icons'
import type {
  EquipmentStatistics,
} from '@/types/equipment'

// ============================================================
// 分类分布水平条
// ============================================================
const categoryBarColors = ['#5645d4', '#7b3ff2', '#0075de', '#2a9d99', 'var(--color-success)', '#dd5b00', '#ff64c8', '#f5d75e']

export function CategoryDistribution({ statistics }: { statistics: EquipmentStatistics }) {
  const maxVal = Math.max(...Object.values(statistics.by_category), 1)
  const entries = Object.entries(statistics.by_category)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)

  if (entries.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-stone)', fontSize: 14 }}>
        暂无分类数据
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {entries.map(([name, count], i) => {
        const pct = (count / maxVal) * 100
        const color = categoryBarColors[i % categoryBarColors.length]
        return (
          <div
            key={name}
            style={{
              animation: `fadeInUp 0.4s ease both`,
              animationDelay: `${i * 60}ms`,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginBottom: 5,
                fontSize: 13,
              }}
            >
              <span style={{ color: 'var(--color-ink)', fontWeight: 500 }}>{name}</span>
              <span style={{ color: 'var(--color-stone)', fontWeight: 500, fontFeatureSettings: '"tnum"' }}>{count}</span>
            </div>
            <div
              style={{
                height: 8,
                borderRadius: 4,
                background: 'var(--color-surface-soft)',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${pct}%`,
                  background: `linear-gradient(90deg, ${color}DD, ${color})`,
                  borderRadius: 4,
                  transition: 'width 1s cubic-bezier(0.22, 0.61, 0.36, 1)',
                }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ============================================================
// 工单流转概览
// ============================================================
