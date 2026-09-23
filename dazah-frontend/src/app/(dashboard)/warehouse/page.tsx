'use client'
import { Tag, Typography } from 'antd'
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
import { ModuleLandingCards, type ModuleLandingEntry } from '@/components/shared/ModuleLandingCards'
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

const modules: ModuleLandingEntry[] = [
  {
    title: '原辅料及包材',
    description: '库存状态、明细与出入库台账',
    icon: <DatabaseOutlined />,
    href: '/warehouse/materials/dashboard',
    dashboard: true,
  },
  {
    title: '五金',
    description: '五金库存、费用统计与分析',
    icon: <ToolOutlined />,
    href: '/warehouse/hardware/dashboard',
    dashboard: true,
  },
  {
    title: '成品库存',
    description: '成品库存、发货情况与产品明细',
    icon: <ShoppingOutlined />,
    href: '/warehouse/product/dashboard',
    dashboard: true,
  },
  {
    title: 'AI 分析',
    description: '库存异常检测、趋势分析与报告',
    icon: <RobotOutlined />,
    href: '/warehouse/ai-analysis',
  },
  {
    title: '仓储设置',
    description: '飞书数据源与页面映射配置',
    icon: <SettingOutlined />,
    href: '/warehouse/settings',
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
      <ModuleLandingCards title="仓储管理" description="查看库存状态、出入库业务与仓储配置" entries={modules} />

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

    </div>
    </WarehouseQueryProvider>
  )
}
