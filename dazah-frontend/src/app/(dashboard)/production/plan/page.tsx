'use client'

import { useCallback, useEffect, useState } from 'react'
import dayjs from 'dayjs'
import { BarChartOutlined, ExclamationCircleOutlined } from '@ant-design/icons'
import {
  Card,
  Col,
  DatePicker,
  Progress,
  Row,
  Statistic,
  Table,
  Tabs,
  Tooltip,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getPlans, getSalesPlanDetails } from '@/actions/production'
import type { ProductionPlan, SalesPlanDetail } from '@/types/production'
import SyncSettingsButton from '@/components/production/SyncSettingsButton'
import { PRODUCTION_PAGE_KEYS } from '@/components/production/useProductionPermissions'

const { Title, Text } = Typography

const dash = '--'

// 汇总卡片占位：数据源接入前仅保留版面（口径：KG 与批分开统计）
const SUMMARY_PLACEHOLDERS = [
  { key: 'kg-planned', title: '计划产量（KG）' },
  { key: 'kg-actual', title: '实际完成（KG）' },
  { key: 'kg-rate', title: '完成率（KG）' },
  { key: 'batch-planned', title: '计划产量（批）' },
  { key: 'batch-actual', title: '实际完成（批）' },
  { key: 'batch-rate', title: '完成率（批）' },
]

// 页面内模块 Tab 的本地持久化键：刷新后停留在上次所在模块
const PLAN_PAGE_TAB_STORAGE_KEY = 'dazah.production.plan-page.tab'

// 生产/销售计划所选月份的会话级记忆键：刷新后停留在上次所选月份；
// 关闭标签页或重新登录（会话结束）后回到当月
const PLAN_PAGE_MONTH_STORAGE_KEY = 'dazah.production.plan-page.month'
const PLAN_PAGE_SALES_MONTH_STORAGE_KEY = 'dazah.production.plan-page.sales-month'

// 销售计划数据同步说明（悬浮/点击"飞书同步数据"旁的感叹号图标展示）
const SALES_SYNC_LOGIC_TIP =
  '更新逻辑：每天 8:00-20:00，系统每小时整点自动从飞书同步一次销售计划与生产计划数据；20:00 至次日 8:00 不自动同步，如有需要可在同步设置中手动同步。'

// ═══════════════════════════════════════════
// 主页面：飞书同步的生产计划台账
// ═══════════════════════════════════════════
export default function PlanPage() {
  // 当前模块 Tab：持久化到本地，刷新/重开页面后停留在上次所在模块
  const [activeTab, setActiveTab] = useState('plan')
  const [month, setMonth] = useState(dayjs().format('YYYY-MM'))
  // 月份恢复完成后再发起加载，避免先按当月请求再按记住的月份返工
  const [selectionRestored, setSelectionRestored] = useState(false)
  const [plans, setPlans] = useState<ProductionPlan[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const load = useCallback(async (p: number, m: string) => {
    setLoading(true)
    try {
      const res = await getPlans({ page: p, page_size: 20, month: m })
      if (res.code === 200) {
        setPlans(res.data || [])
        setTotal(res.meta?.total || 0)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selectionRestored) {
      load(page, month) // eslint-disable-line react-hooks/set-state-in-effect
    }
  }, [selectionRestored, page, month, load])

  const [salesPlans, setSalesPlans] = useState<SalesPlanDetail[]>([])
  const [salesLoading, setSalesLoading] = useState(true)
  const [salesPage, setSalesPage] = useState(1)
  const [salesTotal, setSalesTotal] = useState(0)
  // 数据月份筛选：初始当月（会话内记住所选），清空 = 全部月份
  const [salesMonth, setSalesMonth] = useState(dayjs().format('YYYY-MM'))

  const loadSales = useCallback(async (p: number, m: string) => {
    setSalesLoading(true)
    try {
      const res = await getSalesPlanDetails({
        page: p,
        page_size: 20,
        month: m || undefined,
      })
      if (res.code === 200) {
        setSalesPlans(res.data || [])
        setSalesTotal(res.meta?.total || 0)
      }
    } finally {
      setSalesLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selectionRestored) {
      loadSales(salesPage, salesMonth) // eslint-disable-line react-hooks/set-state-in-effect
    }
  }, [selectionRestored, salesPage, salesMonth, loadSales])

  // 来源表名：展示当前列表数据真实来源的飞书数据表名（同步时写入每行）；
  // 跨多月或存量行无表名时无法用单一表名概括，回退通用名
  const salesSourceTables = Array.from(
    new Set(
      salesPlans
        .map((row) => row.source_table_name?.trim())
        .filter((name): name is string => Boolean(name)),
    ),
  )
  const salesSourceTableLabel =
    salesSourceTables.length === 1 ? salesSourceTables[0] : '销售计划执行表'

  const changeSalesMonth = (d: dayjs.Dayjs | null) => {
    const m = d ? d.format('YYYY-MM') : ''
    setSalesMonth(m)
    setSalesPage(1)
    try {
      window.sessionStorage.setItem(PLAN_PAGE_SALES_MONTH_STORAGE_KEY, m)
    } catch {
      // 存储不可用时仅当次会话生效
    }
  }

  useEffect(() => {
    // 挂载后恢复会话内记住的月份（SSR 首帧保持默认当月，避免水合错位）；
    // 两个月份各自独立记忆，与 Tab 恢复同模式
    try {
      const savedMonth = window.sessionStorage.getItem(PLAN_PAGE_MONTH_STORAGE_KEY)
      const savedSalesMonth = window.sessionStorage.getItem(
        PLAN_PAGE_SALES_MONTH_STORAGE_KEY,
      )
      if (savedMonth) {
        setMonth(savedMonth) // eslint-disable-line react-hooks/set-state-in-effect
      }
      // 销售月份允许清空（= 全部月份）：从未选择过则默认当月
      setSalesMonth(savedSalesMonth ?? dayjs().format('YYYY-MM')) // eslint-disable-line react-hooks/set-state-in-effect
    } catch {
      // 存储不可用时保持默认当月
    }
    setSelectionRestored(true) // eslint-disable-line react-hooks/set-state-in-effect
  }, [])

  useEffect(() => {
    // 挂载后恢复上次所在模块（SSR 首帧保持默认，避免水合错位）
    try {
      const saved = window.localStorage.getItem(PLAN_PAGE_TAB_STORAGE_KEY)
      if (saved === 'plan' || saved === 'sales') {
        // 恢复必须在挂载后进行，与既有数据加载效果同模式
        setActiveTab(saved) // eslint-disable-line react-hooks/set-state-in-effect
      }
    } catch {
      // 存储不可用时保持默认
    }
  }, [])

  const handleTabChange = (key: string) => {
    setActiveTab(key)
    try {
      window.localStorage.setItem(PLAN_PAGE_TAB_STORAGE_KEY, key)
    } catch {
      // 存储不可用时仅当次会话生效
    }
  }

  const changeMonth = (d: dayjs.Dayjs | null) => {
    if (!d) return
    setPage(1)
    const m = d.format('YYYY-MM')
    setMonth(m)
    try {
      window.sessionStorage.setItem(PLAN_PAGE_MONTH_STORAGE_KEY, m)
    } catch {
      // 存储不可用时仅当次会话生效
    }
  }

  const columns: ColumnsType<ProductionPlan> = [
    { title: '车间', dataIndex: 'workshop', width: 130, render: (v: string | null) => v || '-' },
    { title: '产品', dataIndex: 'product_name', width: 140, render: (v: string) => v || '-' },
    { title: '日期', dataIndex: 'plan_date', width: 100, render: (v: string | null) => v || '-' },
    { title: '单位', dataIndex: 'unit', width: 60, render: (v: string | null) => v || '-' },
    {
      title: '计划产量',
      dataIndex: 'planned_yield',
      width: 100,
      render: (v: number | null) => (v != null ? v.toLocaleString('zh-CN') : '-'),
    },
    {
      title: '实际完成',
      dataIndex: 'actual_completion',
      width: 100,
      render: (v: number | null) => (v != null ? v.toLocaleString('zh-CN') : '-'),
    },
    {
      title: '完成率',
      dataIndex: 'completion_rate',
      width: 140,
      render: (v: number | null) => {
        if (v == null) return '-'
        const pct = Math.round(v * 1000) / 10
        return (
          <div className="flex items-center gap-2">
            <Progress
              percent={Math.min(100, pct)}
              size="small"
              showInfo={false}
              style={{ width: 72, margin: 0 }}
            />
            <span style={{ fontSize: 12 }}>{pct}%</span>
          </div>
        )
      },
    },
    { title: '安环情况', dataIndex: 'safety_status', width: 90, render: (v: string | null) => v || '-' },
    { title: '质量情况', dataIndex: 'quality_status', width: 90, render: (v: string | null) => v || '-' },
    { title: '备注', dataIndex: 'remarks', width: 150, ellipsis: true, render: (v: string | null) => v || '-' },
  ]

  const fmtNum = (v: number | null) =>
    v != null ? v.toLocaleString('zh-CN') : '-'

  const salesColumns: ColumnsType<SalesPlanDetail> = [
    // 数据月份：全部月份视图下区分每行归属月份（同步时按源数据表名写入）
    { title: '数据月份', dataIndex: 'data_month', width: 90, render: (v: string | null) => v || '-' },
    { title: '产品', dataIndex: 'product_name', width: 140, render: (v: string) => v || '-' },
    { title: '单位', dataIndex: 'unit', width: 60, render: (v: string | null) => v || '-' },
    { title: '上月已发货未开票', dataIndex: 'last_month_delivered_uninvoiced', width: 130, render: fmtNum },
    { title: '2025年当月发货量', dataIndex: 'current_year_delivered', width: 130, render: fmtNum },
    { title: '本月计划发货量', dataIndex: 'month_planned_delivery', width: 120, render: fmtNum },
    { title: '本月已发货量', dataIndex: 'month_delivered_qty', width: 110, render: fmtNum },
    { title: '未发货量', dataIndex: 'undelivered_qty', width: 100, render: fmtNum },
    { title: '本月预计开票量', dataIndex: 'month_planned_invoice', width: 120, render: fmtNum },
    { title: '已开票量', dataIndex: 'invoiced_qty', width: 100, render: fmtNum },
    { title: '本月发货完成率', dataIndex: 'delivery_completion_rate', width: 110, render: fmtNum },
    { title: '上月底库存', dataIndex: 'last_month_end_inventory', width: 100, render: fmtNum },
    { title: '本月预计产能', dataIndex: 'month_planned_capacity', width: 110, render: fmtNum },
    { title: '本月底库存', dataIndex: 'month_end_inventory', width: 100, render: fmtNum },
    { title: '备注', dataIndex: 'remarks', width: 140, ellipsis: true, render: (v: string | null) => v || '-' },
  ]

  return (
    <div className="p-6">
      <div className="mb-4">
        <Title level={4} style={{ margin: 0 }}>
          <BarChartOutlined className="mr-2" />
          产销计划
        </Title>
        <Text type="secondary">生产计划管理与飞书数据同步</Text>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        items={[
          {
            key: 'plan',
            label: '生产计划',
            children: (
              <>
                <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
                  {SUMMARY_PLACEHOLDERS.map((c) => (
                    <Col xs={24} md={8} key={c.key}>
                      <Card
                        variant="borderless"
                        className="shadow-sm h-full"
                        styles={{ body: { padding: '10px 14px' } }}
                      >
                        <Statistic
                          title={<span style={{ fontSize: 12 }}>{c.title}</span>}
                          value={dash}
                          styles={{ content: { fontSize: 24, fontWeight: 600 } }}
                        />
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          数据源待接入
                        </Text>
                      </Card>
                    </Col>
                  ))}
                </Row>

                <Card
                  variant="borderless"
                  className="shadow-sm"
                  styles={{ body: { padding: '12px 16px' } }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: 12,
                      flexWrap: 'wrap',
                      gap: 8,
                    }}
                  >
                    <DatePicker
                      size="small"
                      picker="month"
                      allowClear={false}
                      style={{ width: 96 }}
                      value={dayjs(`${month}-01`)}
                      onChange={changeMonth}
                    />
                    <SyncSettingsButton productName="生产计划" syncTarget="production_plan" pageKey={PRODUCTION_PAGE_KEYS.salesPlan} />
                  </div>
                  <Table
                    columns={columns}
                    dataSource={plans}
                    rowKey="id"
                    loading={loading}
                    size="small"
                    scroll={{ x: 1100 }}
                    pagination={{
                      current: page,
                      pageSize: 20,
                      total,
                      showSizeChanger: false,
                      showTotal: t => `共 ${t} 条`,
                      onChange: p => setPage(p),
                    }}
                  />
                </Card>
              </>
            ),
          },
          {
            key: 'sales',
            label: '销售计划',
            children: (
              <Card variant="borderless" className="shadow-sm">
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 12,
                    flexWrap: 'wrap',
                    gap: 8,
                  }}
                >
                  <Text type="secondary">
                    {salesSourceTableLabel} · 飞书同步数据
                    <Tooltip
                      title={SALES_SYNC_LOGIC_TIP}
                      trigger={['hover', 'click']}
                    >
                      <ExclamationCircleOutlined
                        data-testid="sales-sync-logic-tip"
                        className="ml-1 cursor-pointer"
                        style={{ color: 'var(--color-muted)' }}
                      />
                    </Tooltip>
                  </Text>
                  <div className="flex items-center gap-2">
                    <DatePicker
                      picker="month"
                      allowClear
                      placeholder="全部月份"
                      style={{ width: 110 }}
                      value={salesMonth ? dayjs(`${salesMonth}-01`) : null}
                      onChange={changeSalesMonth}
                    />
                    <SyncSettingsButton
                      productName="销售计划"
                      syncTarget="sales_plan"
                      pageKey={PRODUCTION_PAGE_KEYS.salesPlan}
                      tableIdOptional
                    />
                  </div>
                </div>
                <Table
                  columns={salesColumns}
                  dataSource={salesPlans}
                  rowKey="id"
                  loading={salesLoading}
                  size="small"
                  scroll={{ x: 1800 }}
                  pagination={{
                    current: salesPage,
                    pageSize: 20,
                    total: salesTotal,
                    showSizeChanger: false,
                    showTotal: t => `共 ${t} 条`,
                    onChange: p => setSalesPage(p),
                  }}
                  locale={{
                    emptyText: '暂无销售计划数据，请先完成飞书同步设置并同步',
                  }}
                />
              </Card>
            ),
          },
        ]}
      />
    </div>
  )
}
