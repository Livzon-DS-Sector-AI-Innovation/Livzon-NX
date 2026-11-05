'use client'

// 设备健康度榜单卡：红/黄档设备列表（评分升序），点击跳转台账。
// 数据来自 GET /api/v1/equipment/health/board（每日 03:30 快照）。

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { HeartOutlined } from '@ant-design/icons'
import { Spin } from 'antd'
import type { HealthBoard, HealthGrade } from '@/types/equipment'
import { fetchHealthBoardClient } from '@/lib/api/equipment-client'

const GRADE_STYLE: Record<HealthGrade, { label: string; color: string; bg: string }> = {
  R: { label: '红', color: '#e03131', bg: '#fde0ec' },
  Y: { label: '黄', color: '#dd5b00', bg: '#ffe8d4' },
  G: { label: '绿', color: '#1aae39', bg: '#d9f3e1' },
}

export function HealthBoardCard() {
  const router = useRouter()
  const [board, setBoard] = useState<HealthBoard | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  // 所有 setState 都在首个 await 之后，避免 effect 内同步 setState
  const load = useCallback(async () => {
    try {
      const data = await fetchHealthBoardClient()
      setBoard(data)
      setFailed(false)
    } catch {
      setFailed(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const retry = useCallback(() => {
    setLoading(true)
    void load()
  }, [load])

  const items = (board?.items ?? []).filter((i) => i.grade !== 'G').slice(0, 8)
  const summary = board?.summary ?? { total: 0, G: 0, Y: 0, R: 0 }

  return (
    <section
      style={{
        background: '#ffffff',
        borderRadius: 12,
        border: '1px solid #e5e3df',
        padding: '20px 24px',
      }}
      data-testid="health-board-card"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <HeartOutlined style={{ fontSize: 16, color: '#5645d4' }} />
        <span style={{ fontSize: 15, fontWeight: 600 }}>设备健康度</span>
        <span style={{ color: '#8a867d', fontSize: 12, marginLeft: 'auto' }}>
          共 {summary.total} 台 · 每日 03:30 快照
        </span>
      </div>

      <Spin spinning={loading}>
        {failed ? (
          <div style={{ color: '#8a867d', fontSize: 13, padding: '12px 0' }}>
            健康快照加载失败，
            <a onClick={retry} role="button" tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && retry()}
              style={{ cursor: 'pointer' }}>重试</a>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              {(['R', 'Y', 'G'] as HealthGrade[]).map((g) => (
                <span
                  key={g}
                  data-testid={`health-summary-${g}`}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    padding: '2px 10px',
                    borderRadius: 4,
                    fontSize: 12,
                    fontWeight: 600,
                    color: GRADE_STYLE[g].color,
                    background: GRADE_STYLE[g].bg,
                  }}
                >
                  {GRADE_STYLE[g].label}档 {summary[g]} 台
                </span>
              ))}
            </div>
            {items.length === 0 ? (
              <div style={{ color: '#8a867d', fontSize: 13, padding: '8px 0' }}>
                全部设备处于绿档，暂无需关注项
              </div>
            ) : (
              items.map((item) => (
                <div
                  key={item.equipment_id}
                  role="button"
                  tabIndex={0}
                  onClick={() =>
                    router.push(
                      `/equipment?workshop=${encodeURIComponent(item.workshop_code ?? '')}&module=assets`,
                    )
                  }
                  onKeyDown={(e) =>
                    e.key === 'Enter' &&
                    router.push(
                      `/equipment?workshop=${encodeURIComponent(item.workshop_code ?? '')}&module=assets`,
                    )
                  }
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '6px 0',
                    fontSize: 13,
                    cursor: 'pointer',
                    borderBottom: '1px dashed #eceae6',
                  }}
                >
                  <span
                    style={{
                      ...GRADE_STYLE[item.grade],
                      display: 'inline-flex',
                      padding: '1px 8px',
                      borderRadius: 4,
                      background: GRADE_STYLE[item.grade].bg,
                    }}
                  >
                    {Math.round(item.score)}
                  </span>
                  <span style={{ fontWeight: 500 }}>{item.equipment_name ?? '-'}</span>
                  <span style={{ color: '#8a867d', fontSize: 12 }}>
                    {item.equipment_no ?? ''}
                  </span>
                  <span style={{ color: '#8a867d', fontSize: 12, marginLeft: 'auto' }}>
                    {item.workshop_code ?? ''}
                  </span>
                </div>
              ))
            )}
          </>
        )}
      </Spin>
    </section>
  )
}
