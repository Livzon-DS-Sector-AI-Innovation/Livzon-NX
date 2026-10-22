'use client'

import {
  AlertOutlined,
  ExperimentOutlined,
  ScheduleOutlined,
} from '@ant-design/icons'
import type {
  StockWarning,
  MaintenancePlan,
  CalibrationPlan,
} from '@/types/equipment'

// ============================================================
// 预警面板
// ============================================================
export function WarningPanels({
  stockWarnings,
  overduePlans,
  calibrationPlans,
}: {
  stockWarnings: StockWarning[]
  overduePlans: MaintenancePlan[]
  calibrationPlans: CalibrationPlan[]
}) {
  const today = new Date()
  const thirtyDaysLater = new Date(today.getTime() + 30 * 24 * 60 * 60 * 1000)
  const upcomingCals = calibrationPlans
    .filter(c => c.next_calibration_date && new Date(c.next_calibration_date) <= thirtyDaysLater && new Date(c.next_calibration_date) >= today)
    .slice(0, 5)

  const panels = [
    {
      title: '备件库存预警',
      count: stockWarnings.length,
      icon: <AlertOutlined />,
      accent: 'var(--color-error)',
      bg: '#fff1f0',
      border: '#ffa8a8',
      emptyText: '暂无库存预警',
      items: stockWarnings.slice(0, 5).map(w => ({
        key: w.spare_part_id,
        label: w.name,
        sub: `${w.code}`,
        meta: (
          <span style={{ color: 'var(--color-error)', fontWeight: 600, fontSize: 13 }}>
            仅剩 {w.current_qty}{' '}
            <span style={{ color: 'var(--color-stone)', fontWeight: 400 }}>/ 最低 {w.min_qty}</span>
          </span>
        ),
      })),
    },
    {
      title: '逾期维护计划',
      count: overduePlans.length,
      icon: <ScheduleOutlined />,
      accent: '#dd5b00',
      bg: '#fff7e6',
      border: '#ffd591',
      emptyText: '暂无逾期计划',
      items: overduePlans.slice(0, 5).map(p => ({
        key: p.id,
        label: p.plan_name || p.equipment_name || '',
        sub: p.equipment_name || p.equipment_no || '',
        meta: (
          <span style={{ color: '#dd5b00', fontWeight: 600, fontSize: 13 }}>
            应于 {p.next_maintenance_date || '—'}
          </span>
        ),
      })),
    },
    {
      title: '校准即将到期',
      count: upcomingCals.length,
      icon: <ExperimentOutlined />,
      accent: '#7b3ff2',
      bg: '#f5f0ff',
      border: '#d6b6f6',
      emptyText: '暂无到期校准',
      items: upcomingCals.map(c => {
        const daysLeft = Math.ceil(
          (new Date(c.next_calibration_date!).getTime() - today.getTime()) / (1000 * 60 * 60 * 24),
        )
        return {
          key: c.id,
          label: c.equipment_name || c.equipment_no || '',
          sub: c.calibration_type,
          meta: (
            <span
              style={{
                color: daysLeft <= 7 ? 'var(--color-error)' : '#dd5b00',
                fontWeight: 600,
                fontSize: 13,
              }}
            >
              {daysLeft} 天后到期
            </span>
          ),
        }
      }),
    },
  ]

  return (
    <div className="equipment-warning-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
      {panels.map((panel, pi) => (
        <div
          key={panel.title}
          style={{
            background: 'var(--color-canvas)',
            borderRadius: 12,
            border: '1px solid var(--color-hairline)',
            borderLeft: `3px solid ${panel.accent}`,
            padding: '20px 20px 16px',
            animation: `fadeInUp 0.5s ease both`,
            animationDelay: `${pi * 100}ms`,
            transition: 'box-shadow 0.2s ease, border-color 0.2s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.boxShadow = 'rgba(15,15,15,0.06) 0px 4px 12px 0px'
            e.currentTarget.style.borderColor = panel.border
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.boxShadow = 'none'
            e.currentTarget.style.borderColor = 'var(--color-hairline)'
          }}
        >
          {/* 标题行 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: 8,
                background: panel.bg,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 16,
                color: panel.accent,
                flexShrink: 0,
              }}
            >
              {panel.icon}
            </div>
            <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--color-ink)' }}>{panel.title}</span>
            {panel.count > 0 && (
              <span
                style={{
                  background: panel.accent,
                  color: '#ffffff',
                  fontSize: 12,
                  fontWeight: 700,
                  borderRadius: 9999,
                  padding: '1px 8px',
                  minWidth: 22,
                  textAlign: 'center',
                  fontFeatureSettings: '"tnum"',
                }}
              >
                {panel.count}
              </span>
            )}
          </div>

          {/* 列表 */}
          {panel.items.length === 0 ? (
            <div style={{ padding: '20px 0', textAlign: 'center', color: 'var(--color-stone)', fontSize: 13 }}>
              {panel.emptyText}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {panel.items.map((item, ii) => (
                <div
                  key={item.key}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 10px',
                    background: '#fafaf9',
                    borderRadius: 6,
                    border: '1px solid #ede9e4',
                    animation: `fadeInUp 0.3s ease both`,
                    animationDelay: `${ii * 50}ms`,
                    transition: 'border-color 0.15s ease',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = panel.border }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#ede9e4' }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 500,
                        color: 'var(--color-ink)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {item.label}
                    </div>
                    {item.sub && (
                      <div style={{ fontSize: 12, color: 'var(--color-stone)', marginTop: 1 }}>{item.sub}</div>
                    )}
                  </div>
                  <div style={{ flexShrink: 0, marginLeft: 12 }}>{item.meta}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
