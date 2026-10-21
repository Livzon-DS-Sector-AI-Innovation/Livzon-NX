'use client'

import {
  AimOutlined,
  AlertOutlined,
  CheckCircleFilled,
  ClockCircleFilled,
  ExperimentOutlined,
  FileTextOutlined,
  RightOutlined,
  ScheduleOutlined,
  ToolFilled,
  WarningFilled,
} from '@ant-design/icons'

const orderPipelineStages = [
  { status: '待处理', color: '#e03131', bg: '#fff1f0', icon: <AlertOutlined /> },
  { status: '执行中', color: '#dd5b00', bg: '#fff7e6', icon: <ToolFilled /> },
  { status: '待验收', color: '#d4b106', bg: '#fffbe6', icon: <ClockCircleFilled /> },
  { status: '已完成', color: '#1aae39', bg: '#e6f7e6', icon: <CheckCircleFilled /> },
  { status: '已关闭', color: '#787671', bg: '#f0eeec', icon: <CheckCircleFilled /> },
]

const priorityConfig: Record<WorkOrderPriority, { color: string; bg: string; dot: string; label: string }> = {
  '紧急': { color: '#e03131', bg: '#fff1f0', dot: '#e03131', label: '紧急' },
  '高': { color: '#dd5b00', bg: '#fff7e6', dot: '#dd5b00', label: '高' },
  '中': { color: '#0075de', bg: '#e6f0fa', dot: '#0075de', label: '中' },
  '低': { color: '#787671', bg: '#f0eeec', dot: '#787671', label: '低' },
}

const typeIcons: Record<string, ReactNode> = {
  '故障维修': <WarningFilled />,
  '计划维护': <ScheduleOutlined />,
  '巡检': <AimOutlined />,
  '校准': <ExperimentOutlined />,
}
import type { ReactNode } from 'react'
import type {
  WorkOrderPriority,
  WorkOrderStatistics,
} from '@/types/equipment'

const typeColors: Record<string, string> = {
  '故障维修': '#e03131',
  '计划维护': '#dd5b00',
  '巡检': '#0075de',
  '校准': '#7b3ff2',
}

export function WorkOrderPipeline({ statistics }: { statistics: WorkOrderStatistics }) {
  const total = statistics.total || 0

  return (
    <div>
      {/* ===== 横向流转卡片 ===== */}
      <div
        className="equipment-order-pipeline"
        role="region" aria-label="工单流转图" tabIndex={0}
        style={{
          display: 'flex',
          overflowX: 'auto',
          alignItems: 'stretch',
          gap: 0,
          marginBottom: 28,
        }}
      >
        {orderPipelineStages.map((stage, idx) => {
          const count = statistics.by_status[stage.status as keyof typeof statistics.by_status] || 0
          const pct = total > 0 ? ((count / total) * 100).toFixed(0) : '0'

          return (
            <div key={stage.status} style={{ display: 'flex', alignItems: 'stretch', flex: 1, minWidth: 152 }}>
              {/* 卡片 */}
              <div
                style={{
                  flex: 1,
                  background: '#ffffff',
                  borderRadius: 12,
                  border: `1.5px solid ${count > 0 ? stage.color : '#e5e3df'}`,
                  padding: '18px 16px',
                  textAlign: 'center',
                  animation: `fadeInUp 0.5s ease both`,
                  animationDelay: `${idx * 80}ms`,
                  transition: 'border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease',
                  position: 'relative',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = stage.color
                  e.currentTarget.style.boxShadow = `0 2px 12px ${stage.color}18`
                  e.currentTarget.style.transform = 'translateY(-3px)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = count > 0 ? stage.color : '#e5e3df'
                  e.currentTarget.style.boxShadow = 'none'
                  e.currentTarget.style.transform = 'translateY(0)'
                }}
              >
                {/* 顶部彩色圆点 + 百分比 */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, marginBottom: 8 }}>
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: stage.color,
                      display: 'inline-block',
                      flexShrink: 0,
                      animation: count > 0 ? 'pulse 2s ease infinite' : 'none',
                    }}
                  />
                  <span style={{ fontSize: 11, fontWeight: 500, color: '#787671', fontFeatureSettings: '"tnum"' }}>
                    {pct}%
                  </span>
                </div>

                {/* 数字 */}
                <div
                  style={{
                    fontSize: 32,
                    fontWeight: 700,
                    color: count > 0 ? stage.color : '#c8c4be',
                    lineHeight: 1.1,
                    fontFeatureSettings: '"tnum"',
                    marginBottom: 6,
                  }}
                >
                  {count}
                </div>

                {/* 图标 + 标签 */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
                  <span style={{ fontSize: 13, color: stage.color, display: 'flex' }}>
                    {stage.icon}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 500, color: '#5d5b54' }}>
                    {stage.status}
                  </span>
                </div>

                {/* 底部百分比条 */}
                <div
                  style={{
                    height: 3,
                    borderRadius: 2,
                    background: '#f0eeec',
                    marginTop: 12,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${pct}%`,
                      background: stage.color,
                      borderRadius: 2,
                      transition: 'width 0.8s cubic-bezier(0.22, 0.61, 0.36, 1)',
                    }}
                  />
                </div>
              </div>

              {/* 箭头连接 */}
              {idx < orderPipelineStages.length - 1 && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding: '0 4px',
                    flexShrink: 0,
                    zIndex: 1,
                  }}
                >
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: '50%',
                      background: '#f6f5f4',
                      border: '1px solid #e5e3df',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 10,
                      color: '#c8c4be',
                    }}
                  >
                    <RightOutlined />
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* ===== 底部两列分布 ===== */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
          gap: 16,
          borderTop: '1px solid #ede9e4',
          paddingTop: 20,
        }}
      >
        {/* 按类型分布 */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#5d5b54', marginBottom: 14, letterSpacing: '0.02em' }}>
            按类型分布
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {Object.entries(statistics.by_type)
              .sort((a, b) => b[1] - a[1])
              .map(([type, count], i) => {
                const maxType = Math.max(...Object.values(statistics.by_type), 1)
                const pct = (count / maxType) * 100
                const accent = typeColors[type] || '#5645d4'
                return (
                  <div
                    key={type}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      animation: `fadeInUp 0.4s ease both`,
                      animationDelay: `${i * 50}ms`,
                    }}
                  >
                    <span style={{ fontSize: 13, color: accent, width: 16, textAlign: 'center', flexShrink: 0 }}>
                      {typeIcons[type] || <FileTextOutlined />}
                    </span>
                    <span style={{ fontSize: 13, color: '#1a1a1a', fontWeight: 500, width: 60, flexShrink: 0 }}>
                      {type}
                    </span>
                    <div style={{ flex: 1, height: 6, borderRadius: 3, background: '#f0eeec', overflow: 'hidden' }}>
                      <div
                        style={{
                          height: '100%',
                          width: `${pct}%`,
                          background: `linear-gradient(90deg, ${accent}CC, ${accent})`,
                          borderRadius: 3,
                          transition: 'width 1s cubic-bezier(0.22, 0.61, 0.36, 1)',
                        }}
                      />
                    </div>
                    <span
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: '#1a1a1a',
                        width: 32,
                        textAlign: 'right',
                        flexShrink: 0,
                        fontFeatureSettings: '"tnum"',
                      }}
                    >
                      {count}
                    </span>
                  </div>
                )
              })}
          </div>
        </div>

        {/* 按优先级分布 */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#5d5b54', marginBottom: 14, letterSpacing: '0.02em' }}>
            按优先级分布
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
              gap: 10,
            }}
          >
            {Object.entries(priorityConfig).map(([priority, config], i) => {
              const count = statistics.by_priority[priority as keyof typeof statistics.by_priority] || 0
              const maxPriority = Math.max(...Object.values(statistics.by_priority), 1)
              const pct = ((count / maxPriority) * 100).toFixed(0)
              return (
                <div
                  key={priority}
                  style={{
                    background: '#fafaf9',
                    borderRadius: 10,
                    border: '1px solid #ede9e4',
                    padding: '14px 16px',
                    animation: `fadeInUp 0.4s ease both`,
                    animationDelay: `${i * 60}ms`,
                    transition: 'border-color 0.2s ease',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = config.color }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#ede9e4' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: '50%',
                        background: config.dot,
                        display: 'inline-block',
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ fontSize: 12, color: '#5d5b54', fontWeight: 500 }}>{config.label}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                    <span
                      style={{
                        fontSize: 24,
                        fontWeight: 700,
                        color: '#1a1a1a',
                        lineHeight: 1.1,
                        fontFeatureSettings: '"tnum"',
                      }}
                    >
                      {count}
                    </span>
                    <span style={{ fontSize: 11, color: '#a4a097' }}>个</span>
                  </div>
                  {/* 微型进度条 */}
                  <div
                    style={{
                      height: 3,
                      borderRadius: 2,
                      background: '#f0eeec',
                      marginTop: 8,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        height: '100%',
                        width: `${pct}%`,
                        background: config.color,
                        borderRadius: 2,
                        transition: 'width 0.8s ease',
                      }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
