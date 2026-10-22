'use client'

import type {
  WorkOrder,
} from '@/types/equipment'

// ============================================================
// 近期工单列表
// ============================================================
const workOrderStatusStyle: Record<string, { color: string; bg: string }> = {
  '待处理': { color: 'var(--color-error)', bg: '#fff1f0' },
  '执行中': { color: '#dd5b00', bg: '#fff7e6' },
  '待验收': { color: '#d4b106', bg: '#fffbe6' },
  '已完成': { color: 'var(--color-success)', bg: '#e6f7e6' },
  '已关闭': { color: 'var(--color-stone)', bg: 'var(--color-surface-soft)' },
}

export function RecentWorkOrders({ orders }: { orders: WorkOrder[] }) {
  if (orders.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-stone)', fontSize: 14 }}>
        暂无近期工单
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {orders.map((order, i) => {
        const style = workOrderStatusStyle[order.status] || { color: 'var(--color-stone)', bg: 'var(--color-surface-soft)' }
        return (
          <div
            key={order.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '10px 14px',
              background: '#fafaf9',
              borderRadius: 8,
              border: '1px solid #ede9e4',
              animation: `fadeInUp 0.3s ease both`,
              animationDelay: `${i * 60}ms`,
              transition: 'border-color 0.2s ease',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#c8c4be' }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#ede9e4' }}
          >
            {/* 左侧优先级色条 */}
            <div
              style={{
                width: 3,
                height: 32,
                borderRadius: 2,
                background:
                  order.priority === '紧急' ? 'var(--color-error)'
                  : order.priority === '高' ? '#dd5b00'
                  : order.priority === '中' ? '#0075de'
                  : '#c8c4be',
                flexShrink: 0,
              }}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-ink)' }}>
                {order.work_order_no}
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: 'var(--color-stone)',
                  marginTop: 1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {order.equipment_name || order.equipment_no} · {order.order_type}
              </div>
            </div>
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: 9999,
                background: style.bg,
                color: style.color,
                whiteSpace: 'nowrap',
              }}
            >
              {order.status}
            </span>
            <span style={{ fontSize: 12, color: 'var(--color-stone)', whiteSpace: 'nowrap' }}>
              {order.created_at ? new Date(order.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) : ''}
            </span>
          </div>
        )
      })}
    </div>
  )
}
