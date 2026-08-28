// 仓储快捷操作方向类型
export type StockDirection = '入库' | '出库'

// 箭头路径映射：入库（箭头落入托盘）/ 出库（箭头离开托盘）
const ARROW_PATHS: Record<StockDirection, { down: string; head: string }> = {
  入库: { down: 'M12 3v10', head: 'm8 9 4 4 4-4' },
  出库: { down: 'M12 13V3', head: 'm8 7 4-4 4 4' },
}

// 出入库图标：根据方向渲染箭头落入/离开托盘
export function InboundOutboundIcon({ direction }: { direction: StockDirection }) {
  const { down, head } = ARROW_PATHS[direction]
  return (
    <svg
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={down} />
      <path d={head} />
      <path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
    </svg>
  )
}

// 方向 -> 图标底色 + Tag 颜色
export const DIRECTION_STYLE: Record<StockDirection, { color: string; tagColor: string }> = {
  入库: { color: '#1aae39', tagColor: 'green' },
  出库: { color: '#dd5b00', tagColor: 'orange' },
}
