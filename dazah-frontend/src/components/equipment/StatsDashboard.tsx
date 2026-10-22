'use client'

import { ConfigProvider } from 'antd'
import {
  CheckCircleFilled,
  WarningFilled,
  ToolFilled,
  ThunderboltFilled,
  ApartmentOutlined,
  BarChartOutlined,
  PieChartOutlined,
  DashboardOutlined,
  AimOutlined,
  AlertOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import type {
  EquipmentStatus,
  WorkOrderStatus,
  WorkOrderPriority,
  WorkOrderType,
  EquipmentStatistics,
  WorkOrderStatistics,
  StockWarning,
  MaintenancePlan,
  CalibrationPlan,
  WorkOrder,
} from '@/types/equipment'
import type { InspectionFeishuWorkshopSummary } from '@/types/inspection-feishu'
import { KpiCard } from './stats/KpiCard'
import { StatusDistribution } from './stats/StatusDistribution'
import { CategoryDistribution } from './stats/CategoryDistribution'
import { WorkOrderPipeline } from './stats/WorkOrderPipeline'
import { WarningPanels } from './stats/WarningPanels'
import { RecentWorkOrders } from './stats/RecentWorkOrders'
import { InspectionProgressCard } from './inspection/InspectionProgressCard'

// ============================================================
// 类型定义
// ============================================================
interface DashboardData {
  equipmentStats: EquipmentStatistics | null
  workOrderStats: WorkOrderStatistics | null
  stockWarnings: StockWarning[]
  overduePlans: MaintenancePlan[]
  calibrationPlans: CalibrationPlan[]
  recentWorkOrders: WorkOrder[]
  inspectionSummaries: InspectionFeishuWorkshopSummary[]
}

interface StatsDashboardProps {
  initialData: DashboardData
}

// ============================================================
// 主仪表盘组件
// ============================================================
export function StatsDashboard({ initialData }: StatsDashboardProps) {
  const {
    equipmentStats,
    workOrderStats,
    stockWarnings,
    overduePlans,
    calibrationPlans,
    recentWorkOrders,
    inspectionSummaries,
  } = initialData

  const eq = equipmentStats || { total: 0, by_status: {} as Record<EquipmentStatus, number>, by_category: {} as Record<string, number>, by_location: {} as Record<string, number> }
  const wo = workOrderStats || { total: 0, by_status: {} as Record<WorkOrderStatus, number>, by_type: {} as Record<WorkOrderType, number>, by_priority: {} as Record<WorkOrderPriority, number> }

  const quickLinks = [
    { label: '设备台账', icon: <ApartmentOutlined /> },
    { label: '维护管理', icon: <ToolFilled /> },
    { label: '备件管理', icon: <DashboardOutlined /> },
    { label: '巡检管理', icon: <AimOutlined /> },
  ]

  return (
    <ConfigProvider>
      {/* 全局 keyframes */}
      <style>{`
        @media (max-width: 767px) {
          .equipment-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
          .equipment-chart-grid, .equipment-warning-grid { grid-template-columns: minmax(0, 1fr) !important; }
        }
        .equipment-order-pipeline:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(16px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes shimmer {
          0%   { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%      { opacity: 0.6; }
        }
        @keyframes dotFloat {
          0%, 100% { transform: translateY(0) scale(1); }
          50%      { transform: translateY(-4px) scale(1.15); }
        }
        .kpi-card:hover .kpi-decor-dot {
          animation: dotFloat 0.6s ease;
        }
      `}</style>

      <div
        style={{
          // 与统一工作台/飞书配置页一致：铺满内容区宽度，不再 1280 居中限宽
          width: '100%',
        }}
      >
        {/* ========== 页面标题 ========== */}
        <div
          style={{
            marginBottom: 28,
            animation: 'fadeInUp 0.5s ease both',
          }}
        >
          <h1
            style={{
              fontSize: 22,
              fontWeight: 600,
              color: 'var(--color-ink)',
              lineHeight: 1.25,
              margin: 0,
              letterSpacing: '-0.01em',
            }}
          >
            设备管理概览
          </h1>
          <p
            style={{
              fontSize: 14,
              color: 'var(--color-stone)',
              margin: '6px 0 0',
              lineHeight: 1.5,
            }}
          >
            实时数据仪表盘 · 设备部全景视图
          </p>
        </div>

        {/* ========== 快捷入口行 ========== */}
        {/* 模块路由已按车间拆分，入口目标车间未定：暂以占位呈现，不可跳转 */}
        <div
          className="equipment-summary-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 12,
            marginBottom: 28,
          }}
        >
          {quickLinks.map((link, i) => (
            <div
              key={link.label}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '14px 20px',
                background: 'var(--color-canvas)',
                borderRadius: 12,
                border: '1px solid var(--color-hairline)',
                animation: `fadeInUp 0.45s ease both`,
                animationDelay: `${80 + i * 70}ms`,
                opacity: 0.8,
              }}
            >
              <div
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 10,
                  background: 'var(--color-surface-soft)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 17,
                  color: 'var(--color-stone)',
                  flexShrink: 0,
                }}
              >
                {link.icon}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-slate)', lineHeight: 1.3 }}>
                  {link.label}
                </div>
                <div style={{ fontSize: 12, color: 'var(--color-stone)', marginTop: 1 }}>
                  待接入
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* ========== 今日巡检进度 ========== */}
        <InspectionProgressCard summaries={inspectionSummaries} />

        {/* ========== KPI 卡片行 ========== */}
        {/* 在线率无真实监测口径、工单与备件模块未启用：相关 KPI 以「待接入」呈现 */}
        <div
          className="equipment-summary-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 16,
            marginBottom: 28,
          }}
        >
          <KpiCard
            label="设备总数"
            value={eq.total}
            suffix="台"
            icon={<ApartmentOutlined />}
            accentColor="#5645d4"
            trend={{ direction: 'up', text: '设备台账' }}
            index={0}
          />
          <KpiCard
            label="设备在线率"
            value="待接入"
            placeholder
            note="设备在线监测未接入"
            icon={<CheckCircleFilled />}
            accentColor="#a4a097"
            index={1}
          />
          <KpiCard
            label="待处理工单"
            value="待接入"
            placeholder
            note="工单模块未启用"
            icon={<AlertOutlined />}
            accentColor="#a4a097"
            index={2}
          />
          <KpiCard
            label="库存预警"
            value="待接入"
            placeholder
            note="备件模块未启用"
            icon={<WarningFilled />}
            accentColor="#a4a097"
            index={3}
          />
        </div>

        {/* ========== 第二行：设备全景 + 工单概览 ========== */}
        <div
          className="equipment-chart-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
            gap: 16,
            marginBottom: 28,
          }}
        >
          {/* 设备状态分布 */}
          <div
            style={{
              background: 'var(--color-canvas)',
              borderRadius: 12,
              border: '1px solid var(--color-hairline)',
              padding: '20px 24px',
              animation: 'fadeInUp 0.5s ease both',
              animationDelay: '320ms',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
              <BarChartOutlined style={{ fontSize: 16, color: '#5645d4' }} />
              <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-ink)', margin: 0 }}>
                设备状态分布
              </h3>
              <span style={{ fontSize: 12, color: 'var(--color-stone)', marginLeft: 'auto' }}>
                共 {eq.total} 台
              </span>
            </div>
            <StatusDistribution statistics={eq} />
          </div>

          {/* 设备分类分布 */}
          <div
            style={{
              background: 'var(--color-canvas)',
              borderRadius: 12,
              border: '1px solid var(--color-hairline)',
              padding: '20px 24px',
              animation: 'fadeInUp 0.5s ease both',
              animationDelay: '400ms',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
              <PieChartOutlined style={{ fontSize: 16, color: '#7b3ff2' }} />
              <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-ink)', margin: 0 }}>
                按分类分布
              </h3>
            </div>
            <CategoryDistribution statistics={eq} />
          </div>
        </div>

        {/* ========== 第三行：工单流转 ========== */}
        <div
          style={{
            background: 'var(--color-canvas)',
            borderRadius: 12,
            border: '1px solid var(--color-hairline)',
            padding: '24px 28px',
            marginBottom: 28,
            animation: 'fadeInUp 0.5s ease both',
            animationDelay: '480ms',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
            <ThunderboltFilled style={{ fontSize: 16, color: '#dd5b00' }} />
            <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-ink)', margin: 0 }}>
              工单流转概览
            </h3>
            <span style={{ fontSize: 12, color: 'var(--color-stone)', marginLeft: 'auto' }}>
              共 {wo.total} 个工单
            </span>
          </div>
          <WorkOrderPipeline statistics={wo} />
        </div>

        {/* ========== 第四行：预警面板 ========== */}
        <div style={{ marginBottom: 28 }}>
          <WarningPanels
            stockWarnings={stockWarnings}
            overduePlans={overduePlans}
            calibrationPlans={calibrationPlans}
          />
        </div>

        {/* ========== 第五行：近期工单（全宽） ========== */}
        <div
          style={{
            background: 'var(--color-canvas)',
            borderRadius: 12,
            border: '1px solid var(--color-hairline)',
            padding: '20px 24px',
            animation: 'fadeInUp 0.5s ease both',
            animationDelay: '560ms',
            marginBottom: 28,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <FileTextOutlined style={{ fontSize: 16, color: '#0075de' }} />
            <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-ink)', margin: 0 }}>
              近期工单
            </h3>
          </div>
          <RecentWorkOrders orders={recentWorkOrders} />
        </div>
      </div>
    </ConfigProvider>
  )
}
