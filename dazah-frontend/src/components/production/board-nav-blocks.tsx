'use client'

// 生产/排产页顶部共用的 6 个导航块：同位置同目标，一一对应。
// 产品 Tab 按业务约定位置摆放（点击切换产品上下文，不跳转页面）：
// 第 2 位 MC（霉酚酸）、第 3 位多拉菌素、第 4 位 L-苯丙氨酸、
// 第 5 位洛伐他汀（LV）、第 6 位美伐他汀（MV）——他汀复用 MP 看板管线；
// 首位为空占位。

import { useEffect } from 'react'
import { Col, Row, Typography } from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'
import {
  restoreProductContext,
  useProductContextStore,
} from '@/stores/product-context'

const { Text } = Typography

// 产品 Tab 位置表：代码与后端排产存档 product_code 一致（FA/MP/DR）；
// named 为命名占位（暂无 product_code，仅展示名称，不可切换产品上下文）
interface ProductTab {
  code: string
  name: string
  color: string
}

interface NamedSlot {
  name: string
}

const PRODUCT_TAB_SLOTS: readonly (ProductTab | NamedSlot | null)[] = [
  null,
  { code: 'MC', name: 'MC', color: '#1677ff' },
  { code: 'DR', name: '多拉菌素', color: '#d46b08' },
  { code: 'FA', name: 'L-苯丙氨酸', color: '#389e0d' },
  { code: 'LV', name: '洛伐他汀', color: '#c41d7f' },
  { code: 'MV', name: '美伐他汀', color: '#722ed1' },
]

export default function BoardNavBlocks() {
  const productCode = useProductContextStore((s) => s.productCode)
  const setProductCode = useProductContextStore((s) => s.setProductCode)

  // 挂载后恢复上次选择的产品 Tab（生产概览/排产计划两页共用）
  useEffect(() => {
    restoreProductContext()
  }, [])

  return (
    <Row gutter={[12, 12]}>
      {PRODUCT_TAB_SLOTS.map((tab, index) => (
        <Col xs={12} sm={8} md={4} key={index}>
          {tab ? (
            'code' in tab ? (
              <div
                title={`切换到 ${tab.name} 看板与排产数据`}
                onClick={() => setProductCode(tab.code)}
                className="flex items-center justify-center gap-2 rounded-lg border bg-white cursor-pointer transition-colors"
                style={{
                  height: 56,
                  borderColor:
                    productCode === tab.code
                      ? 'var(--color-primary)'
                      : 'var(--color-hairline)',
                  backgroundColor:
                    productCode === tab.code ? 'var(--color-primary-soft, #f0f7ff)' : undefined,
                }}
              >
                <ExperimentOutlined style={{ color: tab.color, fontSize: 18 }} />
                <Text strong style={{ fontSize: 13 }}>
                  {tab.name}
                </Text>
              </div>
            ) : (
              <div
                title={`${tab.name}看板暂未接入`}
                className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--color-hairline)] bg-white/60"
                style={{ height: 56 }}
              >
                <ExperimentOutlined style={{ color: '#8c8c8c', fontSize: 18 }} />
                <Text type="secondary" style={{ fontSize: 13 }}>
                  {tab.name}
                </Text>
              </div>
            )
          ) : (
            <div
              className="flex items-center justify-center rounded-lg border border-dashed border-[var(--color-hairline)] bg-white/60"
              style={{ height: 56 }}
            >
              <Text type="secondary" style={{ fontSize: 12 }}>
                导航入口
              </Text>
            </div>
          )}
        </Col>
      ))}
    </Row>
  )
}
