'use client'
import Link from 'next/link'
import { Card, Row, Col, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import {
  CloudServerOutlined,
  DatabaseOutlined,
  ToolOutlined,
  ShoppingOutlined,
  RobotOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { InboundOutboundIcon, DIRECTION_STYLE, WarehouseQueryProvider } from '@/components/warehouse'
import { fetchWarehouseHomeQuickFormLinks } from '@/lib/api/client/warehouse'

const { Text } = Typography

// 快捷表单卡：链接来自仓储设置-页面映射维护的表单链接（DB 配置），
// 未配置表单的入口自动隐藏，不再写死飞书表单 ID。
const quickActions = [
  {
    key: 'raw-inbound',
    pageKey: 'inbound-ledger',
    field: 'inbound_form_url' as const,
    title: '原辅料及包材入库',
    subtitle: '入库总账',
    direction: '入库' as const,
  },
  {
    key: 'raw-outbound',
    pageKey: 'raw-ledger',
    field: 'outbound_form_url' as const,
    title: '原辅料出库',
    subtitle: '出库总账',
    direction: '出库' as const,
  },
  {
    key: 'packaging-outbound',
    pageKey: 'packaging-ledger',
    field: 'outbound_form_url' as const,
    title: '包材出库',
    subtitle: '出库总账',
    direction: '出库' as const,
  },
  {
    key: 'liquid-raw-inbound',
    pageKey: 'liquid-raw-inbound',
    field: 'inbound_form_url' as const,
    title: '液体原辅料入库',
    subtitle: '液体原辅料入库',
    direction: '入库' as const,
  },
  {
    key: 'liquid-sugar-inbound',
    pageKey: 'liquid-sugar-inbound',
    field: 'inbound_form_url' as const,
    title: '液糖入库',
    subtitle: '液糖入库',
    direction: '入库' as const,
  },
  {
    key: 'product-inbound',
    pageKey: 'product-inbound-ledger',
    field: 'inbound_form_url' as const,
    title: '成品入库',
    subtitle: '入库总账',
    direction: '入库' as const,
  },
  {
    key: 'product-outbound',
    pageKey: 'product-outbound-ledger',
    field: 'outbound_form_url' as const,
    title: '成品出库',
    subtitle: '发货情况',
    direction: '出库' as const,
  },
]

const modules = [
  {
    key: 'raw-materials',
    title: '原辅料及包材',
    desc: '原辅料/包材库存总表、明细表、出入库总账、供应商及物料对照表',
    icon: <DatabaseOutlined style={{ fontSize: 24, color: '#fff' }} />,
    path: '/warehouse/materials/raw-summary',
    color: '#5645d4',
  },
  {
    key: 'hardware',
    title: '五金',
    desc: '各车间五金库存管理、费用统计与分析',
    icon: <ToolOutlined style={{ fontSize: 24, color: '#fff' }} />,
    path: '/warehouse/hardware/dashboard',
    color: '#2a9d99',
  },
  {
    key: 'product',
    title: '成品库存',
    desc: '成品汇总、发货情况、入库总账、各产品库存明细',
    icon: <ShoppingOutlined style={{ fontSize: 24, color: '#fff' }} />,
    path: '/warehouse/product/summary',
    color: '#1aae39',
  },
  {
    key: 'ai-analysis',
    title: 'AI 分析',
    desc: '库存异常检测、趋势分析、智能问答、分析报告',
    icon: <RobotOutlined style={{ fontSize: 24, color: '#fff' }} />,
    path: '/warehouse/ai-analysis',
    color: '#7b3ff2',
  },
  {
    key: 'settings',
    title: '仓储设置',
    desc: '飞书数据源配置、页面映射管理',
    icon: <SettingOutlined style={{ fontSize: 24, color: '#fff' }} />,
    path: '/warehouse/settings',
    color: '#0075de',
  },
]

export default function WarehousePage() {
  // 表单链接配置（页面映射中维护的入库/出库表单链接，仅含已配置项）
  const { data: quickFormLinks } = useQuery({
    queryKey: ['warehouse-home-quick-form-links'],
    queryFn: fetchWarehouseHomeQuickFormLinks,
  })
  const visibleQuickActions = quickActions.filter((action) => {
    const links = quickFormLinks?.[action.pageKey]
    return Boolean(links?.[action.field])
  })

  return (
    <WarehouseQueryProvider>
      <div className="space-y-6">
      <div>
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
          仓储管理
        </h1>
        <p className="text-[14px] text-[var(--color-steel)]">
          原辅料、包材、成品、五金等仓储业务数据管理
        </p>
      </div>

      {visibleQuickActions.length > 0 && (
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)] mb-3">
            快捷操作
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
            {visibleQuickActions.map((action) => (
              <a
                href={quickFormLinks?.[action.pageKey]?.[action.field] ?? '#'}
                target="_blank"
                rel="noopener noreferrer"
                key={action.key}
                className="block"
              >
                <div className="p-4 rounded-lg border border-[var(--color-hairline)] bg-white hover:border-[var(--color-primary)] hover:shadow-md cursor-pointer transition-all h-full flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <div
                      className="w-11 h-11 rounded-lg flex items-center justify-center text-white"
                      style={{ backgroundColor: DIRECTION_STYLE[action.direction].color }}
                    >
                      <InboundOutboundIcon direction={action.direction} />
                    </div>
                    <Tag color={DIRECTION_STYLE[action.direction].tagColor} className="mr-0">
                      {action.direction}
                    </Tag>
                  </div>
                  <div>
                    <Text strong className="block text-[14px] leading-snug">
                      {action.title}
                    </Text>
                    <Text type="secondary" className="text-xs">
                      {action.subtitle}
                    </Text>
                  </div>
                </div>
              </a>
            ))}

            {/* 外部系统入口：大宗物料管理系统（固定内网地址，新窗口打开） */}
            <a
              href="http://10.10.10.180:9002/Login"
              target="_blank"
              rel="noopener noreferrer"
              className="block"
            >
              <div className="p-4 rounded-lg border border-[var(--color-hairline)] bg-white hover:border-[var(--color-primary)] hover:shadow-md cursor-pointer transition-all h-full flex flex-col gap-3">
                <div
                  className="w-11 h-11 rounded-lg flex items-center justify-center text-white"
                  style={{ backgroundColor: '#5645d4' }}
                >
                  <CloudServerOutlined style={{ fontSize: 20 }} />
                </div>
                <Text strong className="block text-[14px] leading-snug">
                  大宗物料管理系统
                </Text>
              </div>
            </a>
          </div>
        </div>
      )}

      {/* 子模块导航区 */}
      <div>
        <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)] mb-3">
          功能模块
        </h2>
        <Row gutter={[16, 16]}>
          {modules.map((mod) => (
            <Col xs={24} sm={12} lg={8} key={mod.key}>
              <Link href={mod.path}>
                <Card
                  hoverable
                  className="h-full cursor-pointer transition-shadow hover:shadow-md"
                >
                  <div className="flex items-start gap-4">
                    <div
                      className="w-12 h-12 rounded-lg flex items-center justify-center shrink-0"
                      style={{ backgroundColor: mod.color }}
                    >
                      {mod.icon}
                    </div>
                    <div>
                      <h3 className="text-[16px] font-semibold text-[var(--color-charcoal)] mb-1">
                        {mod.title}
                      </h3>
                      <p className="text-[14px] text-[var(--color-steel)] leading-relaxed">
                        {mod.desc}
                      </p>
                    </div>
                  </div>
                </Card>
              </Link>
            </Col>
          ))}
        </Row>
      </div>
    </div>
    </WarehouseQueryProvider>
  )
}
