'use client'

import { CheckCircleFilled } from '@ant-design/icons'

// 飞书多维表格中「确认」列为复选框：已确认显示绿色对勾，与飞书一致。
export function ConfirmFlag({ confirmed }: { confirmed: boolean | null | undefined }) {
  if (confirmed) {
    return <CheckCircleFilled style={{ color: '#52c41a', fontSize: 18 }} aria-label="已确认" />
  }
  return (
    <span style={{ color: '#bfbfbf' }} aria-label="未确认">
      未确认
    </span>
  )
}

// 后端将飞书复选框归一为 approved/空文本，approved 视为已勾选
export function ConfirmFlagFromResult({ value }: { value: string | null | undefined }) {
  return <ConfirmFlag confirmed={(value || '').trim() === 'approved'} />
}
