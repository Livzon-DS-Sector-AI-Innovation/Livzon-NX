import { RightOutlined } from '@ant-design/icons'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
import type { InspectionFeishuWorkshopSummary } from '@/types/inspection-feishu'

const C = {
  ink: '#1a1a1a',
  slate: '#5d5b54',
  stone: '#a4a097',
  hairline: '#e5e3df',
  rowDivider: '#f2f0ee',
  track: '#f0efec',
  green: '#1aae39',
  orange: '#e67e22',
  red: '#c0392b',
}

const NAME_COL_WIDTH = 96
const COUNT_COL_WIDTH = 92
const ABNORMAL_COL_WIDTH = 64

/** 设备仪表盘的“今日巡检进度”汇总卡：全部车间一行一条，未接入灰态。 */
export function InspectionProgressCard({
  summaries,
}: {
  summaries: InspectionFeishuWorkshopSummary[]
}) {
  const byWorkshop = new Map(summaries.map((s) => [s.workshop_code, s]))
  const date = summaries[0]?.date
  const enabledCount = summaries.length
  const totalDevices = summaries.reduce((sum, s) => sum + (s.total_devices || 0), 0)
  const inspected = summaries.reduce((sum, s) => sum + (s.inspected || 0), 0)
  const abnormal = summaries.reduce((sum, s) => sum + (s.abnormal || 0), 0)
  const amDone = summaries.reduce((sum, s) => sum + (s.am_inspected || 0), 0)
  const pmDone = summaries.reduce((sum, s) => sum + (s.pm_inspected || 0), 0)

  return (
    <section
      style={{
        background: '#ffffff',
        border: `1px solid ${C.hairline}`,
        borderRadius: 12,
        padding: '18px 22px 8px',
        marginBottom: 28,
      }}
      aria-label="今日巡检进度"
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 8,
          marginBottom: 10,
        }}
      >
        <h3 style={{ fontSize: 16, fontWeight: 600, color: C.ink, margin: 0 }}>
          今日巡检进度{date ? `（${date}）` : ''}
        </h3>
        <div
          style={{
            display: 'flex',
            gap: 18,
            flexWrap: 'wrap',
            fontSize: 13,
            color: C.slate,
          }}
        >
          <span>
            已接入{' '}
            <b style={{ color: enabledCount > 0 ? C.green : C.stone }}>{enabledCount}</b>
            /{EQUIPMENT_WORKSHOPS.length} 车间
          </span>
          <span>
            总进度 <b style={{ color: C.ink }}>{inspected}</b>/{totalDevices} 台
          </span>
          <span>
            上午 {amDone}/{totalDevices} · 下午 {pmDone}/{totalDevices}
          </span>
          <span>
            异常{' '}
            <b style={{ color: abnormal > 0 ? C.red : C.green, fontWeight: 600 }}>
              {abnormal}
            </b>{' '}
            台
          </span>
        </div>
      </div>

      <div>
        {EQUIPMENT_WORKSHOPS.map((workshop) => {
          const summary = byWorkshop.get(workshop.code)
          if (!summary) {
            return (
              <div
                key={workshop.code}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 16,
                  padding: '9px 0',
                  borderTop: `1px solid ${C.rowDivider}`,
                  fontSize: 13,
                  color: C.stone,
                }}
              >
                <span style={{ width: NAME_COL_WIDTH }}>{workshop.label}</span>
                <span style={{ flex: 1, fontSize: 12 }}>未接入</span>
              </div>
            )
          }
          const pct = summary.total_devices > 0
            ? Math.round((summary.inspected / summary.total_devices) * 100)
            : 0
          const barColor = summary.abnormal > 0 ? C.orange : C.green
          return (
            <a
              key={workshop.code}
              href={`/equipment/inspection/${workshop.code}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 16,
                padding: '9px 0',
                borderTop: `1px solid ${C.rowDivider}`,
                textDecoration: 'none',
                fontSize: 13,
                color: C.ink,
              }}
            >
              <span style={{ width: NAME_COL_WIDTH, fontWeight: 600 }}>
                {workshop.label}
              </span>
              <div
                style={{
                  flex: 1,
                  height: 8,
                  background: C.track,
                  borderRadius: 4,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${pct}%`,
                    height: '100%',
                    background: barColor,
                    borderRadius: 4,
                  }}
                />
              </div>
              <span
                style={{
                  width: COUNT_COL_WIDTH,
                  textAlign: 'right',
                  color: C.slate,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {summary.inspected}/{summary.total_devices} 台
              </span>
              <span
                style={{
                  width: ABNORMAL_COL_WIDTH,
                  textAlign: 'right',
                  color: summary.abnormal > 0 ? C.red : C.stone,
                  fontWeight: summary.abnormal > 0 ? 600 : 400,
                }}
              >
                异常 {summary.abnormal}
              </span>
              <RightOutlined style={{ fontSize: 11, color: '#c8c4be' }} />
            </a>
          )
        })}
      </div>

      <p style={{ fontSize: 12, color: '#b5b1a8', margin: '8px 0 10px' }}>
        点击已接入车间查看巡检明细；未接入车间需在该车间巡检页配置飞书镜像
      </p>
    </section>
  )
}
