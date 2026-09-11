'use client'

// 生产/排产页顶部共用的 6 个导航块：同位置同目标，一一对应。
// 第 5 位为当前产品 L-苯丙氨酸（点击切换产品上下文，不跳转页面），
// 其余为占位（其他产品接入后在此配置）。

import { Col, Row, Typography } from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'
import { useProductContextStore } from '@/stores/product-context'

const { Text } = Typography

export default function BoardNavBlocks() {
  const setProductCode = useProductContextStore((s) => s.setProductCode)

  return (
    <Row gutter={[12, 12]}>
      {Array.from({ length: 6 }).map((_, index) =>
        index === 4 ? (
          <Col xs={12} sm={8} md={4} key={index}>
            <div
              title="切换到 L-苯丙氨酸 看板与排产数据"
              onClick={() => setProductCode('FA')}
              className="flex items-center justify-center gap-2 rounded-lg border border-[var(--color-primary)] bg-white cursor-pointer"
              style={{ height: 56 }}
            >
              <ExperimentOutlined style={{ color: '#389e0d', fontSize: 18 }} />
              <Text strong style={{ fontSize: 13 }}>
                L-苯丙氨酸
              </Text>
            </div>
          </Col>
        ) : (
          <Col xs={12} sm={8} md={4} key={index}>
            <div
              className="flex items-center justify-center rounded-lg border border-dashed border-[var(--color-hairline)] bg-white/60"
              style={{ height: 56 }}
            >
              <Text type="secondary" style={{ fontSize: 12 }}>
                导航入口
              </Text>
            </div>
          </Col>
        ),
      )}
    </Row>
  )
}
