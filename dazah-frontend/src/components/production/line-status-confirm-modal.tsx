'use client'

import { useEffect, useState } from 'react'
import { Button, Input, Modal, Typography } from 'antd'

import { getLineHaltEvents, type LineHaltEvent } from '@/actions/production'

const { Text } = Typography

export const HALT_CONFIRM_SECONDS = 5

/** 拉取停产/复产事件（打开即取，失败静默：时间线仅供参考）。 */
function useHaltEvents(productCode: string, limit: number) {
  const [events, setEvents] = useState<LineHaltEvent[] | null>(null)
  useEffect(() => {
    let cancelled = false
    setEvents(null)
    void (async () => {
      try {
        const res = await getLineHaltEvents(productCode, limit)
        if (!cancelled && res.code === 200) {
          setEvents(res.data?.events ?? [])
        }
      } catch {
        // 时间线加载失败不阻塞确认操作
      }
    })()
    return () => {
      cancelled = true
    }
  }, [productCode, limit])
  return events
}

function eventLine(ev: LineHaltEvent) {
  return `${ev.created_at ? ev.created_at.slice(0, 16).replace('T', ' ') : '—'}　${
    ev.halted ? '停产' : '复产'
  }${ev.reason ? ` · ${ev.reason}` : ''}${ev.operator_name ? ` · ${ev.operator_name}` : ''}`
}

/**
 * 独立的停产历史弹窗：完整时间线（内部滚动，最多 50 条），
 * 只读查看，不涉及状态切换。
 */
export function LineHaltHistoryModal({
  productCode,
  productName,
  open,
  onClose,
}: {
  productCode: string
  productName: string
  open: boolean
  onClose: () => void
}) {
  const events = useHaltEvents(open ? productCode : '', 50)
  return (
    <Modal
      title={`${productName}停产历史`}
      open={open}
      onCancel={onClose}
      footer={null}
      zIndex={1100}
      data-testid="line-halt-history"
    >
      <Text type="secondary" className="block text-xs">
        最近 50 次，切换一次记一条；上线前的历史无法追溯
      </Text>
      {events === null ? (
        <Text type="secondary" className="text-xs">
          加载中…
        </Text>
      ) : events.length === 0 ? (
        <Text type="secondary" className="text-xs">
          暂无记录
        </Text>
      ) : (
        <ul className="mt-1 max-h-96 list-disc overflow-y-auto pl-5 text-xs leading-6">
          {events.map((ev, idx) => (
            <li key={ev.created_at ?? idx}>{eventLine(ev)}</li>
          ))}
        </ul>
      )}
    </Modal>
  )
}

/**
 * 产线状态切换确认框：确认按钮需 5 秒倒计时结束才可点，取消随时可点。
 * haltPending 为目标状态（null=关闭）；onConfirm/onCancel 由调用方处理。
 * 打开时通过 key 重挂载初始化倒计时，effect 仅负责每秒递减（定时器订阅）。
 * 历史只显示最近一条 + 「查看完整历史」入口，避免长列表把按钮顶下去。
 */
export default function LineStatusConfirmModal({
  productName,
  productCode,
  pendingHalted,
  onCancel,
  onConfirm,
  onOpenHistory,
}: {
  productName: string
  productCode: string
  pendingHalted: boolean | null
  onCancel: () => void
  onConfirm: (reason: string) => void
  onOpenHistory: () => void
}) {
  if (pendingHalted === null) {
    return null
  }
  return (
    <ConfirmDialog
      key={String(pendingHalted)}
      productName={productName}
      productCode={productCode}
      pendingHalted={pendingHalted}
      onCancel={onCancel}
      onConfirm={onConfirm}
      onOpenHistory={onOpenHistory}
    />
  )
}

function ConfirmDialog({
  productName,
  productCode,
  pendingHalted,
  onCancel,
  onConfirm,
  onOpenHistory,
}: {
  productName: string
  productCode: string
  pendingHalted: boolean
  onCancel: () => void
  onConfirm: (reason: string) => void
  onOpenHistory: () => void
}) {
  // 挂载即开始倒计时（由外层 key 重挂载保证每次打开都从 5 秒起算）
  const [countdown, setCountdown] = useState(HALT_CONFIRM_SECONDS)
  const [reason, setReason] = useState('')
  const latest = useHaltEvents(productCode, 1)

  useEffect(() => {
    if (countdown <= 0) return
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000)
    return () => clearTimeout(timer)
  }, [countdown])

  return (
    <Modal
      title={pendingHalted ? '确认停产' : '确认恢复生产'}
      open
      onOk={countdown <= 0 && reason.trim() ? () => onConfirm(reason) : undefined}
      okButtonProps={{ disabled: countdown > 0 || !reason.trim() }}
      onCancel={onCancel}
      okText={countdown > 0 ? `确认（${countdown}s）` : '确认'}
      cancelText="取消"
      data-testid="line-status-confirm"
    >
      <Text>
        {pendingHalted
          ? `确认将「${productName}」标记为停产？停产期间该产品看板将收起，汇总视图中隐藏该产线，全平台可见。`
          : `确认将「${productName}」恢复为生产中？看板与汇总数据将恢复展示。`}
      </Text>
      {/* antd reset.css 的 input{margin:0} 无层级，会压过 Tailwind 工具类
          （@layer utilities），因此间距挂在包裹 div 上而不是 Input 上 */}
      <div className="mt-2">
        <Input
          data-testid="line-status-reason"
          value={reason}
          maxLength={100}
          onChange={(e) => setReason(e.target.value)}
          prefix={<span style={{ color: '#ff4d4f' }}>* </span>}
          placeholder="原因（必填）：转产 / 检修 / 季节性停产 / 误操作…"
        />
      </div>
      {countdown <= 0 && !reason.trim() && (
        <Text type="danger" className="mt-1 block text-xs">
          请填写原因后再确认
        </Text>
      )}
      <div className="mt-2" data-testid="line-status-timeline">
        <Text type="secondary" className="block text-xs">
          {latest === null
            ? '最近记录：加载中…'
            : latest.length === 0
              ? '暂无停产记录'
              : `最近：${eventLine(latest[0])}`}
          　
          <Button
            type="link"
            size="small"
            className="!p-0 text-xs"
            onClick={onOpenHistory}
            data-testid="line-status-history-link"
          >
            查看完整历史
          </Button>
        </Text>
      </div>
    </Modal>
  )
}
