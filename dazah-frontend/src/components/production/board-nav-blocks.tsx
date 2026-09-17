'use client'

// 生产/排产页顶部共用的 6 个导航块：同位置同目标，一一对应。
// 产品 Tab 按业务约定位置摆放（点击切换产品上下文，不跳转页面）：
// 首位汇总（SUMMARY，五产线聚合视图）、第 2 位霉酚酸（系统代码 MC）、
// 第 3 位多拉菌素、第 4 位 L-苯丙氨酸、第 5 位洛伐他汀（LV）、
// 第 6 位美伐他汀（MV）——他汀复用 MC 看板管线。

import { useEffect } from 'react'
import { Col, Row, Typography } from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'
import {
  restoreProductContext,
  useProductContextStore,
} from '@/stores/product-context'

const { Text } = Typography

// 产品 Tab 位置表：代码与后端排产存档 product_code 一致（FA/MC/DR/LV/MV）；
// SUMMARY 为汇总视图（五产线聚合），非单一产品
interface ProductTab {
  code: string
  name: string
  color: string
}

const PRODUCT_TAB_SLOTS: readonly ProductTab[] = [
  { code: 'SUMMARY', name: '汇总', color: '#5645d4' },
  { code: 'MC', name: '霉酚酸', color: '#1677ff' },
  { code: 'DR', name: '多拉菌素', color: '#d46b08' },
  { code: 'FA', name: 'L-苯丙氨酸', color: '#389e0d' },
  { code: 'LV', name: '洛伐他汀', color: '#c41d7f' },
  { code: 'MV', name: '美伐他汀', color: '#08979c' },
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
      {PRODUCT_TAB_SLOTS.map((tab) => (
        <Col xs={12} sm={8} md={4} key={tab.code}>
          <div
            title={`切换到 ${tab.name}${tab.code === 'SUMMARY' ? '（五产线聚合）' : ' 看板与排产数据'}`}
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
        </Col>
      ))}
    </Row>
  )
}
