'use client'

// 生产/排产页顶部共用的 9 个导航块：同位置同目标，一一对应。
// 产品 Tab 按业务约定位置摆放（点击切换产品上下文，不跳转页面）：
// 首位汇总（SUMMARY，五产线聚合视图）、第 2 位霉酚酸（系统代码 MC）、
// 第 3 位盐酸林可霉素（LN，Tab 展示短名「林可」，悬停提示全名）、
// 第 4 位多拉菌素、第 5 位 L-苯丙氨酸、第 6 位洛伐他汀（LV）、
// 第 7 位美伐他汀（MV）——他汀复用 MC 看板管线；
// 第 8/9 位 L-色氨酸（TY）、氟苯尼考（FL，Tab 展示短名，悬停提示全名）。

import { useEffect, useState } from 'react'
import { Col, Row, Typography } from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'
import {
  getProductionLineStatus,
} from '@/actions/production'
import {
  restoreProductContext,
  useProductContextStore,
} from '@/stores/product-context'

const { Text } = Typography

// 产品 Tab 位置表：代码与后端排产存档 product_code 一致
// （FA/MC/DR/LV/MV/TY/FL/LN）；SUMMARY 为汇总视图（五产线聚合），非单一产品。
// 全名过长的产品（盐酸林可霉素/2%氟苯尼考预混剂）Tab 展示短名，fullName 用于悬停提示
interface ProductTab {
  code: string
  name: string
  color: string
  fullName?: string
}

const PRODUCT_TAB_SLOTS: readonly ProductTab[] = [
  { code: 'SUMMARY', name: '汇总', color: '#5645d4' },
  { code: 'MC', name: '霉酚酸', color: '#1677ff' },
  {
    code: 'LN',
    name: '林可',
    color: '#13c2c2',
    fullName: '盐酸林可霉素',
  },
  { code: 'DR', name: '多拉菌素', color: '#d46b08' },
  { code: 'FA', name: 'L-苯丙氨酸', color: '#389e0d' },
  { code: 'LV', name: '洛伐他汀', color: '#c41d7f' },
  { code: 'MV', name: '美伐他汀', color: '#08979c' },
  { code: 'TY', name: 'L-色氨酸', color: '#cf1322' },
  {
    code: 'FL',
    name: '氟苯尼考',
    color: '#d4b106',
    fullName: '2%氟苯尼考预混剂',
  },
]

export default function BoardNavBlocks({
  hideCodes,
}: {
  /** 本页不可用的产品 Tab（如排产页无汇总排产，隐藏 SUMMARY） */
  hideCodes?: readonly string[]
} = {}) {
  const productCode = useProductContextStore((s) => s.productCode)
  const setProductCode = useProductContextStore((s) => s.setProductCode)
  // 停产产品导航块置灰 + 角标（状态全平台共享；拉取失败不阻塞导航）
  const [haltedLines, setHaltedLines] = useState<string[]>([])
  // 各停产产线最近一次事件（悬停提示"自何日起停产"）
  const [latestEvents, setLatestEvents] = useState<
    Record<string, { created_at: string | null; reason: string | null }>
  >({})

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await getProductionLineStatus()
        if (!cancelled && res.code === 200 && res.data) {
          setHaltedLines(res.data.halted ?? [])
          setLatestEvents(res.data.latest_events ?? {})
        }
      } catch {
        // 状态不可用时导航块按生产中展示
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // 挂载后恢复上次选择的产品 Tab（生产概览/排产计划两页共用）
  useEffect(() => {
    restoreProductContext()
  }, [])

  // 恢复出的产品在本页被隐藏时（如排产页残留汇总），回落到首个可见产品，
  // 避免高亮落在不可用 Tab 上、页面数据按不可用产品取数
  useEffect(() => {
    if (hideCodes?.includes(productCode)) {
      const fallback =
        PRODUCT_TAB_SLOTS.find((tab) => !hideCodes.includes(tab.code))?.code ??
        'FA'
      setProductCode(fallback)
    }
  }, [productCode, hideCodes, setProductCode])

  const visibleTabs = PRODUCT_TAB_SLOTS.filter(
    (tab) => !hideCodes?.includes(tab.code),
  )

  return (
    <Row gutter={[12, 12]}>
      {visibleTabs.map((tab) => {
        const halted = haltedLines.includes(tab.code)
        const latest = latestEvents[tab.code]
        const haltedSince = latest?.created_at?.slice(5, 10).replace('-', '月')
        const haltedSuffix = halted
          ? `（停产中${haltedSince ? `，自 ${haltedSince}日 起` : ''}${latest?.reason ? ` · ${latest.reason}` : ''}）`
          : ''
        return (
        // 弹性等宽：宽屏 9 块一行铺满（24 栅格 3/块放不下第 9 块），
        // 窄屏按 144px 基准自然换行
        <Col key={tab.code} flex="1 1 144px">
          <div
            title={`切换到 ${tab.fullName ?? tab.name}${tab.code === 'SUMMARY' ? '（五产线聚合）' : haltedSuffix || ' 生产线与排产数据'}`}
            onClick={() => setProductCode(tab.code)}
            data-testid={`nav-block:${tab.code}`}
            className="flex items-center justify-center gap-2 rounded-lg border bg-white cursor-pointer transition-colors"
            style={{
              height: 56,
              borderColor:
                productCode === tab.code
                  ? 'var(--color-primary)'
                  : 'var(--color-hairline)',
              backgroundColor:
                productCode === tab.code ? 'var(--color-primary-soft, #f0f7ff)' : undefined,
              opacity: halted ? 0.55 : 1,
            }}
          >
            <ExperimentOutlined style={{ color: tab.color, fontSize: 18 }} />
            <Text strong style={{ fontSize: 13 }}>
              {tab.name}
            </Text>
            {halted && (
              <span
                data-testid={`nav-halted-tag:${tab.code}`}
                style={{
                  fontSize: 10,
                  lineHeight: '14px',
                  padding: '0 4px',
                  borderRadius: 3,
                  color: '#8c8c8c',
                  background: 'var(--color-hairline-soft, #f0f0f0)',
                }}
              >
                停产中
              </span>
            )}
          </div>
        </Col>
        )
      })}
    </Row>
  )
}
