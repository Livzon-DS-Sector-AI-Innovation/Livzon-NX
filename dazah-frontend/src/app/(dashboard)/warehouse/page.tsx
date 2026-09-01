'use client'
import Link from 'next/link'
import { Card, Row, Col, Tag, Typography } from 'antd'
import {
  CloudServerOutlined,
  DatabaseOutlined,
  ToolOutlined,
  ShoppingOutlined,
  RobotOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { InboundOutboundIcon, DIRECTION_STYLE } from '@/components/warehouse'

const { Text } = Typography

// 飞书出入库表单公共前缀
const FEISHU_FORM_BASE = 'https://j0eukrlohu.feishu.cn/share/base/form/'

const quickActions = [
  {
    key: 'raw-inbound',
    title: '原辅料及包材入库',
    subtitle: '入库总账',
    direction: '入库' as const,
    feishuFormId: 'shrcnw9CyyTl8PdAvOyQZqK9oie',
  },
  {
    key: 'raw-outbound',
    title: '原辅料出库',
    subtitle: '出库总账',
    direction: '出库' as const,
    feishuFormId: 'shrcnHN5pqjlDlKc3iyUi7Fts7b',
  },
  {
    key: 'packaging-outbound',
    title: '包材出库',
    subtitle: '出库总账',
    direction: '出库' as const,
    feishuFormId: 'shrcneDAUnAAhPs1yFMfOq0Uhkf',
  },
  {
    key: 'product-inbound',
    title: '成品入库',
    subtitle: '入库总账',
    direction: '入库' as const,
    feishuFormId: 'shrcnDSOkJ2pyfcd3azP25WHJ9f',
  },
  {
    key: 'product-outbound',
    title: '成品出库',
    subtitle: '发货情况',
    direction: '出库' as const,
    feishuFormId: 'shrcnnZl0PPBDqISGj02c9h2JBh',
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
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
          仓储管理
        </h1>
        <p className="text-[14px] text-[var(--color-steel)]">
          原辅料、包材、成品、五金等仓储业务数据管理
        </p>
      </div>

      {/* 快捷操作区：CSS Grid 五等分撑满整行，随页面宽度自适应 */}
      <div>
        <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)] mb-3">
          快捷操作
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
          {quickActions.map((action) => (
            <a
              href={FEISHU_FORM_BASE + action.feishuFormId}
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
  )
}
