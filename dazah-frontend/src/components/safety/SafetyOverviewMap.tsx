'use client'

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button, Card, Collapse, Drawer, Empty, Space, Tag, Typography } from 'antd'
import {
  AimOutlined,
  EnvironmentOutlined,
  ExpandOutlined,
  QuestionCircleOutlined,
  ShrinkOutlined,
} from '@ant-design/icons'
import type {
  MapBuildingMarkers,
  MapRiskItem,
  SafetyOverviewData,
} from '@/actions/safety'

const { Text } = Typography

const T = {
  primary: '#5645d4',
  error: '#E03131',
  warning: '#DD5B00',
  gold: '#CA8A04',
  dark: '#8C1616',
  ink: '#1a1a1a',
  charcoal: '#37352f',
  slate: '#5d5b54',
  steel: '#787671',
  muted: '#bbb8b1',
  hairline: '#e5e3df',
  surface: '#f6f5f4',
  canvas: '#ffffff',
  rose: '#fde0ec',
  peach: '#ffe8d4',
  yellow: '#fef7d6',
  sky: '#dcecfa',
  lavender: '#e6e0f5',
}

// 落点来源配色与标签（后端 MapRiskItem.source）
const SOURCE_META: Record<string, { label: string; color: string; bg: string }> = {
  special_op: { label: '特殊作业', color: T.error, bg: T.rose },
  daily_risk: { label: '风险报备', color: T.warning, bg: T.peach },
  hazard: { label: '隐患', color: T.gold, bg: T.yellow },
  accident: { label: '事故', color: T.dark, bg: T.rose },
}

function sourceMeta(source: string) {
  return SOURCE_META[source] || { label: source, color: T.steel, bg: T.surface }
}

function itemTime(item: MapRiskItem): string {
  if (!item.happened_at) return '-'
  return new Date(item.happened_at).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function SafetyOverviewMap({
  overview,
}: {
  overview: SafetyOverviewData
}) {
  const router = useRouter()
  const [selected, setSelected] = useState<MapBuildingMarkers | null>(null)
  // 半宽为默认展示；全宽时底图建筑名清晰可读，便于核对风险归属
  const [fullWidth, setFullWidth] = useState(false)

  const buildings = overview.buildings ?? []
  const markers = overview.markers ?? []
  const unmapped = overview.unmapped ?? []
  const sourceTotals = overview.source_totals ?? {}

  const markerById = useMemo(() => {
    const map = new Map<string, MapBuildingMarkers>()
    for (const marker of markers) {
      map.set(marker.building_id, marker)
    }
    return map
  }, [markers])

  const totalMapped = markers.reduce((sum, m) => sum + m.total, 0)
  const totalUnmapped = unmapped.reduce((sum, g) => sum + g.total, 0)
  const totalItems = totalMapped + totalUnmapped

  const SOURCE_TOTAL_LABELS: Record<string, string> = {
    special_op: '特殊作业',
    daily_risk: '风险报备',
    accident: '事故',
    hazard: '隐患',
  }

  const renderItemRow = (item: MapRiskItem) => {
    const meta = sourceMeta(item.source)
    return (
      <div
        key={`${item.source}-${item.title}-${item.happened_at ?? ''}`}
        data-item-title={item.title}
        className="grid gap-2 px-3 py-2 rounded-lg cursor-pointer hover:bg-[var(--color-surface)] items-center"
        style={{ gridTemplateColumns: '76px 1fr 150px' }}
        onClick={() => item.detail_url && router.push(item.detail_url)}
      >
        <Tag
          style={{
            color: meta.color,
            backgroundColor: meta.bg,
            border: 'none',
            borderRadius: 6,
            fontSize: 11,
            fontWeight: 600,
            margin: 0,
            justifyContent: 'center',
            display: 'inline-flex',
          }}
        >
          {meta.label}
        </Tag>
        <Text className="text-xs truncate" style={{ color: T.charcoal }} title={item.title}>
          {item.title || '-'}
        </Text>
        <span className="flex items-center gap-1 justify-end min-w-0">
          <Text className="text-xs truncate" style={{ color: T.steel }}>
            {item.department || '-'} · {itemTime(item)}
          </Text>
          {item.matched_by === 'department' && (
            <Tag
              style={{
                color: T.steel,
                backgroundColor: T.surface,
                border: 'none',
                borderRadius: 6,
                fontSize: 10,
                fontWeight: 600,
                margin: 0,
                flexShrink: 0,
              }}
            >
              按部门
            </Tag>
          )}
        </span>
      </div>
    )
  }

  return (
    <Card
      variant="borderless"
      className="!shadow-sm"
      style={{ borderRadius: 12, border: `1px solid ${T.hairline}` }}
      title={
        <Space>
          <AimOutlined style={{ color: T.primary }} />
          <Text strong style={{ fontSize: 15, color: T.charcoal }}>
            厂区风险分区 · 当日分布
          </Text>
          <span
            className="text-xs font-semibold px-2 py-0.5 rounded"
            style={{ backgroundColor: T.rose, color: T.error, borderRadius: 6 }}
          >
            当日 {totalItems} 条 · 落点 {totalMapped} · 未映射 {totalUnmapped}
          </span>
        </Space>
      }
      extra={
        <Space size={12} wrap>
          {Object.entries(SOURCE_META).map(([key, meta]) => (
            <Space key={key} size={4}>
              <span
                className="inline-block w-2 h-2 rounded-full"
                style={{ backgroundColor: meta.color }}
              />
              <Text style={{ color: T.slate, fontSize: 11 }}>
                {SOURCE_TOTAL_LABELS[key] || meta.label}
                {sourceTotals[key] !== undefined ? ` ${sourceTotals[key]}` : ''}
              </Text>
            </Space>
          ))}
          <Button
            size="small"
            icon={fullWidth ? <ShrinkOutlined /> : <ExpandOutlined />}
            onClick={() => setFullWidth((v) => !v)}
          >
            {fullWidth ? '半宽' : '全宽'}
          </Button>
        </Space>
      }
    >
      {/* 底图（2.5D 等轴测矢量图）已包含建筑名称/道路/围墙，覆盖层只标
          注有风险的建筑数量气泡；坐标来自 campus_buildings 的投影标定 */}
      <div className="flex justify-center">
        <div
          className={`relative select-none ${fullWidth ? 'w-full' : 'w-full md:w-1/2'}`}
          style={{ borderRadius: 10, overflow: 'hidden', border: `1px solid ${T.hairline}` }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/safety/campus-map.svg"
            alt="厂区平面图"
            className="block w-full h-auto"
            draggable={false}
          />
          {buildings.map((building) => {
            const marker = markerById.get(building.id)
            if (!marker || marker.total <= 0) return null
            return (
              <button
                key={building.id}
                type="button"
                className="absolute flex items-center gap-1 px-1.5 py-0.5 cursor-pointer transition-transform hover:scale-110"
                style={{
                  left: `${building.x_pct}%`,
                  top: `${building.y_pct}%`,
                  transform: 'translate(-50%, -50%)',
                  backgroundColor: T.error,
                  color: '#ffffff',
                  border: '1.5px solid #ffffff',
                  borderRadius: 999,
                  boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
                  lineHeight: 1.2,
                  fontSize: 11,
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                }}
                title={`${building.name} · 当日 ${marker.total} 条，点击查看明细`}
                onClick={() => marker && setSelected(marker)}
              >
                {building.name} {marker.total}
              </button>
            )
          })}
        </div>
      </div>

      {unmapped.length > 0 && (
        <Collapse
          size="small"
          className="mt-3"
          items={[
            {
              key: 'unmapped',
              label: (
                <Space>
                  <QuestionCircleOutlined style={{ color: T.steel }} />
                  <Text style={{ color: T.slate, fontSize: 13 }}>
                    未映射地点 {totalUnmapped} 处（{unmapped.length} 组，地点文本未能对应分区）
                  </Text>
                </Space>
              ),
              children: (
                <div className="space-y-1">
                  {unmapped.map((group) => (
                    <Collapse
                      key={group.location_text}
                      size="small"
                      items={[
                        {
                          key: group.location_text,
                          label: (
                            <Space>
                              <EnvironmentOutlined style={{ color: T.muted }} />
                              <Text style={{ color: T.charcoal, fontSize: 12 }}>
                                {group.location_text}
                              </Text>
                              <Text style={{ color: T.steel, fontSize: 11 }}>
                                {group.total} 条
                              </Text>
                            </Space>
                          ),
                          children: (
                            <div>{(group.items ?? []).map((item) => renderItemRow(item))}</div>
                          ),
                        },
                      ]}
                    />
                  ))}
                </div>
              ),
            },
          ]}
        />
      )}

      <Drawer
        title={
          selected ? (
            <Space>
              <EnvironmentOutlined style={{ color: T.error }} />
              <span>{selected.name} · 当日风险明细</span>
              <Tag
                style={{
                  color: T.error,
                  backgroundColor: T.rose,
                  border: 'none',
                  borderRadius: 6,
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                {selected.total} 条
              </Tag>
            </Space>
          ) : null
        }
        placement="right"
        width={520}
        open={selected !== null}
        onClose={() => setSelected(null)}
      >
        {selected && (selected.items ?? []).length > 0 ? (
          <div className="space-y-1">
            {(selected.items ?? []).map((item) => renderItemRow(item))}
          </div>
        ) : (
          <Empty description="该分区暂无当日风险记录" />
        )}
      </Drawer>
    </Card>
  )
}
