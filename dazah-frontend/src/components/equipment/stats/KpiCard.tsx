'use client'

import type { ReactNode } from 'react'
import { RiseOutlined, FallOutlined } from '@ant-design/icons'
import { useCountUp } from './useCountUp'

// ============================================================
// KPI 卡片
// ============================================================
export function KpiCard({
  label,
  value,
  suffix,
  icon,
  accentColor,
  trend,
  index,
  placeholder,
  note,
  onClick,
}: {
  label: string
  value: number | string
  suffix?: string
  icon: ReactNode
  accentColor: string
  trend?: { direction: 'up' | 'down'; text: string }
  index: number
  /** 待接入态：数据源未启用，以置灰文案替代数值 */
  placeholder?: boolean
  note?: string
  /** 可选点击行为：传入后卡片可点击（如跳转工单列表） */
  onClick?: () => void
}) {
  const numericValue = typeof value === 'number' ? value : 0
  const animatedValue = useCountUp(numericValue)

  return (
    <div
      className="kpi-card"
      role={onClick ? 'button' : undefined}
      style={{
        background: '#ffffff',
        borderRadius: 12,
        padding: '20px 24px',
        border: '1px solid #e5e3df',
        position: 'relative',
        overflow: 'hidden',
        animation: `fadeInUp 0.5s ease both`,
        animationDelay: `${index * 80}ms`,
        transition: 'box-shadow 0.2s ease, transform 0.2s ease',
        cursor: onClick ? 'pointer' : 'default',
      }}
      onClick={onClick}
      onKeyDown={onClick ? (e) => {
        if (e.key === 'Enter' || e.key === ' ') onClick()
      } : undefined}
      tabIndex={onClick ? 0 : undefined}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = 'rgba(15,15,15,0.08) 0px 4px 12px 0px'
        e.currentTarget.style.transform = 'translateY(-2px)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = 'none'
        e.currentTarget.style.transform = 'translateY(0)'
      }}
    >
      {/* 左上角彩色装饰条 */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: 4,
          height: '100%',
          background: accentColor,
          borderRadius: '4px 0 0 4px',
        }}
      />

      {/* 右上角装饰圆 */}
      <div
        style={{
          position: 'absolute',
          top: -12,
          right: -12,
          width: 64,
          height: 64,
          borderRadius: '50%',
          background: `${accentColor}0D`,
          pointerEvents: 'none',
        }}
      />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 500,
              color: '#5d5b54',
              marginBottom: 8,
              letterSpacing: '0.01em',
            }}
          >
            {label}
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 2 }}>
            <span
              style={
                placeholder
                  ? {
                      fontSize: 22,
                      fontWeight: 600,
                      color: '#a4a097',
                      lineHeight: 1.4,
                      letterSpacing: '0.02em',
                    }
                  : {
                      fontSize: 36,
                      fontWeight: 700,
                      color: '#1a1a1a',
                      lineHeight: 1,
                      letterSpacing: '-0.02em',
                      fontFeatureSettings: '"tnum"',
                    }
              }
            >
              {typeof value === 'number' ? animatedValue.toLocaleString() : value}
            </span>
            {!placeholder && suffix && (
              <span style={{ fontSize: 14, fontWeight: 500, color: '#787671', marginLeft: 2 }}>
                {suffix}
              </span>
            )}
          </div>
          {placeholder && note && (
            <div style={{ marginTop: 8, fontSize: 12, color: '#a4a097' }}>{note}</div>
          )}
          {trend && (
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                marginTop: 8,
                fontSize: 12,
                fontWeight: 500,
                color: trend.direction === 'up' ? '#1aae39' : '#e03131',
                background: trend.direction === 'up' ? '#e6f7e6' : '#fff1f0',
                borderRadius: 4,
                padding: '2px 8px',
              }}
            >
              {trend.direction === 'up' ? <RiseOutlined /> : <FallOutlined />}
              {trend.text}
            </div>
          )}
        </div>
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: 12,
            background: `${accentColor}14`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 22,
            color: accentColor,
            flexShrink: 0,
          }}
        >
          {icon}
        </div>
      </div>
    </div>
  )
}
