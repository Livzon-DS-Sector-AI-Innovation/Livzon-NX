'use client'

import { useEffect, useState } from 'react'
import { Modal, Typography } from 'antd'

const { Text } = Typography

export const HALT_CONFIRM_SECONDS = 5

/**
 * 产线状态切换确认框：确认按钮需 5 秒倒计时结束才可点，取消随时可点。
 * haltPending 为目标状态（null=关闭）；onConfirm/onCancel 由调用方处理。
 * 打开时通过 key 重挂载初始化倒计时，effect 仅负责每秒递减（定时器订阅）。
 */
export default function LineStatusConfirmModal({
  productName,
  pendingHalted,
  onCancel,
  onConfirm,
}: {
  productName: string
  pendingHalted: boolean | null
  onCancel: () => void
  onConfirm: () => void
}) {
  if (pendingHalted === null) {
    return null
  }
  return (
    <ConfirmDialog
      key={String(pendingHalted)}
      productName={productName}
      pendingHalted={pendingHalted}
      onCancel={onCancel}
      onConfirm={onConfirm}
    />
  )
}

function ConfirmDialog({
  productName,
  pendingHalted,
  onCancel,
  onConfirm,
}: {
  productName: string
  pendingHalted: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  // 挂载即开始倒计时（由外层 key 重挂载保证每次打开都从 5 秒起算）
  const [countdown, setCountdown] = useState(HALT_CONFIRM_SECONDS)

  useEffect(() => {
    if (countdown <= 0) return
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000)
    return () => clearTimeout(timer)
  }, [countdown])

  return (
    <Modal
      title={pendingHalted ? '确认停产' : '确认恢复生产'}
      open
      onOk={countdown <= 0 ? onConfirm : undefined}
      okButtonProps={{ disabled: countdown > 0 }}
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
    </Modal>
  )
}
