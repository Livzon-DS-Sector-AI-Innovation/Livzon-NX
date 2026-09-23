'use client'

// 本月批次进度条：自适应轨道 + 四段色块 + 分界点三角箭头。
//
// 布局契约（箭头承重版）：
// - 轨道高度 24px（h-6），宽度撑满卡片内容区，随窗口缩放；
// - 已完成段：calc(达成率% − 17px)——剪掉的 17px 由箭头右半收尖段
//   补回，矩形 + 箭头右半 = 精确进度长度，箭头是承重结构而非装饰；
//   达成率极小时 calc 为负，width 不允许负值、浏览器钳为 0（0% 兜底）；
// - 箭头 34×48（竖直底边在左、尖端右指）：中点（17px 处，腰线交点）锚定
//   已完成矩形右缘（分界点）；左半 17px 骑在矩形末端上方形成端部隆起，
//   右半 17px 在轨道带内收尖，尖端恰好落在达成率%上；
// - 0% 兜底：矩形 0 宽、箭头 clamp 钳最左（底边贴 0）；100%：尖端贴右缘；
// - 残余三段在残余容器内按批次比例分摊：容器左垫 17px（箭头收尖段的
//   覆盖区，垫区取首个段色），子段百分比按内容区（= 恰好残余占比 × 轨道宽）
//   解析，可见长度比严格等于批数比、总宽恰为残余份额；未开始段 flex:1
//   吸收浮点残差，四段总和精确 100%；
// - 粒子特效层从箭头底边（矩形右缘 −17px）发射、只向左漂移，不影响布局。

import { useMemo, useState } from 'react'
import { Segmented, Tooltip } from 'antd'
import ProgressParticles from '@/components/production/progress-particles'

const SEG_COLORS = {
  done: '#33526e',
  pending: '#94a3b8',
  running: '#7ea6c9',
  idle: '#e8eef4',
} as const

/** 箭头横向总宽（px）：竖直底边在左，尖端 = left + 34，clamp 右边界需扣除 */
const ARROW_WIDTH = 34
/** 箭头右半收尖段宽（px）：已完成矩形剪掉的让位量（由尖端补回），
    也是箭头中点（腰线交点）到底边/尖端的距离 */
const ARROW_HALF_WIDTH = ARROW_WIDTH / 2
/** 箭头（34×48）相对轨道（24px）上探出高度：top = -12 */
const ARROW_OVERHANG = 12
/** 箭头颜色：与已完成段渐变末端色一致，视觉一体 */
const ARROW_COLOR = '#4a6d8c'

export interface BatchProgressBarProps {
  /** 已完成批次数（产量已录） */
  doneCount: number
  /** 待出产量批次数（已放罐未录产量） */
  pendingCount: number
  /** 运行中批次数 */
  runningCount: number
  /** 未开始批次数 */
  idleCount: number
  /** 已完成产能（kg）；产量口径分母分子 */
  doneYieldKg: number | null
  /** 本周期计划产能（kg）；null/0 时产量口径不可用 */
  plannedCapacityKg: number | null
  /** 历史周期隐藏口径切换等写操作入口 */
  historical?: boolean
  /** 段图例自定义文案（如 FL：已入库/在制/未投料）；缺省用发酵看板文案 */
  labels?: {
    done?: string
    pending?: string
    running?: string
    idle?: string
  }
  /** 隐藏计数为 0 的图例段（已完成段始终保留）；复用到非发酵看板时避免
   * 出现「待出产量 0 批」这类无意义图例 */
  hideZeroLegend?: boolean
}

type Basis = 'batches' | 'capacity'

const DEFAULT_LABELS = {
  done: '已完成',
  pending: '待出产量',
  running: '运行中',
  idle: '未开始',
} as const

export default function BatchProgressBar({
  doneCount,
  pendingCount,
  runningCount,
  idleCount,
  doneYieldKg,
  plannedCapacityKg,
  historical = false,
  labels = {},
  hideZeroLegend = false,
}: BatchProgressBarProps) {
  const segLabels = { ...DEFAULT_LABELS, ...labels }
  const capacityAvailable =
    plannedCapacityKg != null && plannedCapacityKg > 0 && doneYieldKg != null
  const [basis, setBasis] = useState<Basis>(
    capacityAvailable ? 'capacity' : 'batches',
  )

  const total = doneCount + pendingCount + runningCount + idleCount

  const { donePct, boundaryPct } = useMemo(() => {
    if (basis === 'capacity' && capacityAvailable && plannedCapacityKg) {
      const pct = Math.min(
        100,
        Math.max(0, ((doneYieldKg ?? 0) / plannedCapacityKg) * 100),
      )
      return { donePct: pct, boundaryPct: pct }
    }
    const pct = total > 0 ? (doneCount / total) * 100 : 0
    // 分界点 = 已完成段右缘；批次口径下待出产量段从分界点起排
    return { donePct: pct, boundaryPct: pct }
  }, [basis, capacityAvailable, plannedCapacityKg, doneYieldKg, doneCount, total])

  // 残余段（待出产量 + 运行中 + 未开始）在残余容器内按批次数比例分摊：
  // 长度比必须严格等于批数比（运行中 2 批 / 未开始 9 批 → 2:9，不许等长）
  const restCount = total - doneCount
  const shareOfRest = (count: number) =>
    restCount > 0 ? (count / restCount) * 100 : 0
  // 图例/提示里的「占比」口径：占本月总批次数
  const pctOfTotal = (count: number) => (total > 0 ? (count / total) * 100 : 0)

  const fmtKg = (kg: number | null) =>
    kg == null
      ? '--'
      : `${kg.toLocaleString('zh-CN', {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })} kg`

  const segments = [
    {
      key: 'done',
      label: segLabels.done,
      count: doneCount,
      color: SEG_COLORS.done,
      detail:
        basis === 'capacity' && capacityAvailable
          ? `${segLabels.done} ${doneCount} 批｜${fmtKg(doneYieldKg)}`
          : `${segLabels.done} ${doneCount} 批`,
      pct: donePct,
    },
    {
      key: 'pending',
      label: segLabels.pending,
      count: pendingCount,
      color: SEG_COLORS.pending,
      detail: `${segLabels.pending} ${pendingCount} 批`,
      pct: pctOfTotal(pendingCount),
      share: shareOfRest(pendingCount),
    },
    {
      key: 'running',
      label: segLabels.running,
      count: runningCount,
      color: SEG_COLORS.running,
      detail: `${segLabels.running} ${runningCount} 批`,
      pct: pctOfTotal(runningCount),
      share: shareOfRest(runningCount),
    },
    {
      key: 'idle',
      label: segLabels.idle,
      count: idleCount,
      color: SEG_COLORS.idle,
      detail: `${segLabels.idle} ${idleCount} 批`,
      pct: pctOfTotal(idleCount),
      share: shareOfRest(idleCount),
    },
  ] as const

  const legendSegments = hideZeroLegend
    ? segments.filter(seg => seg.key === 'done' || seg.count > 0)
    : segments

  return (
    <div>
      {/* 图例 + 口径切换 */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-4 flex-wrap">
          {legendSegments.map(seg => (
            <span key={seg.key} className="flex items-center gap-1">
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm"
                style={{ backgroundColor: seg.color }}
              />
              <span className="text-xs text-[var(--color-muted)]">
                {seg.label}
              </span>
            </span>
          ))}
        </div>
        {!historical && (
          <Segmented
            size="small"
            value={basis}
            onChange={v => setBasis(v as Basis)}
            options={[
              { label: '批次数量', value: 'batches' },
              { label: '产量(kg)', value: 'capacity', disabled: !capacityAvailable },
            ]}
          />
        )}
      </div>

      {/* 轨道 + 箭头（叠加层）。箭头 34×48 上下各探出轨道 12px：
          margin 上下各留 12px 以上容纳探出，避免箭尖戳出卡片边框 */}
      <div className="relative" style={{ marginTop: 12, marginBottom: 16 }}>
        <div
          className="flex h-6 rounded overflow-hidden"
          data-testid="batch-progress-track"
        >
          {/* 已完成段：达成率% − 17px——剪掉的 17px 由箭头右半收尖段补回，
              矩形右缘即分界点，箭头中点锚定于此；负 calc 被浏览器钳为 0 */}
          {segments[0].count > 0 || donePct > 0 ? (
            <Tooltip title={`${segments[0].detail} · 占比 ${donePct.toFixed(1)}%`}>
              <div
                data-testid="batch-seg-done"
                className="h-full overflow-hidden"
                style={{
                  width: `calc(${donePct}% - ${ARROW_HALF_WIDTH}px)`,
                  backgroundColor: SEG_COLORS.done,
                  backgroundImage:
                    'linear-gradient(90deg, #33526e, #4a6d8c)',
                  flexShrink: 0,
                }}
              />
            </Tooltip>
          ) : null}

          {/* 残余容器：flex:1 拿回已完成段剪掉的 17px；左垫 17px 是箭头
              收尖段覆盖区（垫区取首个段色），子段 % 按内容区解析 →
              可见长度恰为残余份额 × 轨道，比例严格等于批数比 */}
          <div
            data-testid="batch-seg-rest"
            className="flex h-full min-w-0 flex-1 overflow-hidden"
            style={{
              paddingLeft: `${ARROW_HALF_WIDTH}px`,
              backgroundColor:
                pendingCount > 0
                  ? SEG_COLORS.pending
                  : runningCount > 0
                    ? SEG_COLORS.running
                    : SEG_COLORS.idle,
            }}
          >
            {/* 待出产量段：内容区百分比（残余份额内按批次比例） */}
            {pendingCount > 0 ? (
              <Tooltip
                title={`${segments[1].detail} · 占比 ${segments[1].pct.toFixed(1)}%`}
              >
                <div
                  data-testid="batch-seg-pending"
                  className="h-full overflow-hidden"
                  style={{
                    width: `${segments[1].share}%`,
                    backgroundColor: SEG_COLORS.pending,
                    flexShrink: 0,
                    maxWidth: '100%',
                  }}
                />
              </Tooltip>
            ) : null}
            {runningCount > 0 ? (
              <Tooltip
                title={`${segments[2].detail} · 占比 ${segments[2].pct.toFixed(1)}%`}
              >
                <div
                  data-testid="batch-seg-running"
                  className="h-full overflow-hidden"
                  style={{
                    width: `${segments[2].share}%`,
                    backgroundColor: SEG_COLORS.running,
                    flexShrink: 0,
                  }}
                />
              </Tooltip>
            ) : null}
            {idleCount > 0 ? (
              <Tooltip
                title={`${segments[3].detail} · 占比 ${segments[3].pct.toFixed(1)}%`}
              >
                <div
                  data-testid="batch-seg-idle"
                  className="h-full flex-1 overflow-hidden"
                  style={{ backgroundColor: SEG_COLORS.idle, minWidth: 0 }}
                />
              </Tooltip>
            ) : null}
          </div>
        </div>

        {/* 粒子特效层：叠加在已完成段上方 */}
        <ProgressParticles
          progressPct={boundaryPct}
          ultra={
            basis === 'capacity' &&
            capacityAvailable &&
            (doneYieldKg ?? 0) >= (plannedCapacityKg ?? 0)
          }
        />

        {/* 一体式箭头：34×48（轨道 24px 的 2 倍，上下各探出 12px），
            与已完成段渐变末端同色 #4a6d8c。left = 达成率% − 34px，故
            中点（17px 处腰线交点）= 达成率% − 17px = 已完成矩形右缘，锚死分界点；
            尖端 = 达成率%。0% 卡最左、100% 卡最右（clamp 兜底不跑出容器）；
            data-boundary-pct / data-arrow-left 供测试断言
            （测试容器不认 clamp，style.left 会是空串） */}
        <div
          data-testid="batch-progress-arrow"
          data-boundary-pct={boundaryPct.toFixed(10)}
          data-arrow-left={`clamp(0px, calc(${boundaryPct}% - ${ARROW_WIDTH}px), calc(100% - ${ARROW_WIDTH}px))`}
          className="absolute"
          style={{
            top: -ARROW_OVERHANG,
            left: `clamp(0px, calc(${boundaryPct}% - ${ARROW_WIDTH}px), calc(100% - ${ARROW_WIDTH}px))`,
            zIndex: 3,
            pointerEvents: 'none',
          }}
        >
          <svg
            width={34}
            height={48}
            viewBox="0 0 34 48"
            style={{ display: 'block' }}
          >
            {/* 箭身：与已完成段渐变末端同色，视觉上从段右端无缝伸出 */}
            <polygon points="0,0 34,24 0,48" fill={ARROW_COLOR} />
          </svg>
        </div>
      </div>
    </div>
  )
}
