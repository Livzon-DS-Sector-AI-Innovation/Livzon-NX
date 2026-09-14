'use client'

import { useState } from 'react'
import { App, Button, Card, Col, Row, Space, Statistic, Table, Tag, Typography } from 'antd'
import { SendOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { useQuery } from '@tanstack/react-query'
import { fetchItemsDashboard } from '@/lib/api/client/quality'
import { pushItemsLowStock } from '@/actions/quality-inspection'
import type { ColumnsType } from 'antd/es/table'
import type { ItemsStockAlertItemRow } from '@/types/quality'

const { Title } = Typography

function buildMonthlyOption(monthly: { month: number; inbound: number; outbound: number }[]): EChartsOption {
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['入库量', '出库量'] },
    grid: { left: 48, right: 24, top: 40, bottom: 32 },
    xAxis: { type: 'category', data: monthly.map((m) => `${m.month}月`) },
    yAxis: { type: 'value' },
    series: [
      { name: '入库量', type: 'bar', data: monthly.map((m) => m.inbound), itemStyle: { color: '#52c41a' } },
      { name: '出库量', type: 'bar', data: monthly.map((m) => m.outbound), itemStyle: { color: '#fa8c16' } },
    ],
  }
}

const alertColumns: ColumnsType<ItemsStockAlertItemRow> = [
  { title: '物资名称', dataIndex: 'name', key: 'name' },
  { title: '规格型号', dataIndex: 'specification', key: 'specification' },
  { title: '存放位置', dataIndex: 'location', key: 'location' },
  { title: '当前库存', dataIndex: 'current_stock', key: 'current_stock' },
  { title: '警戒库存', dataIndex: 'warning_stock', key: 'warning_stock' },
]

export function ItemsDashboard() {
  const { message } = App.useApp()
  const [pushing, setPushing] = useState(false)
  const { data } = useQuery({
    queryKey: ['quality-items', 'dashboard'],
    queryFn: fetchItemsDashboard,
  })

  const handlePush = async () => {
    setPushing(true)
    try {
      const result = await pushItemsLowStock()
      if (result.status === 'no_data') message.info('当前没有库存不足的物料')
      else if (result.status === 'unmapped') message.warning(result.message || '未配置有效接收人，请到通知设置配置')
      else message.success(`已推送 ${result.sent} 位接收人，共 ${result.item_count} 种物料`)
    } catch {
      message.error('推送失败，请检查飞书设置')
    } finally {
      setPushing(false)
    }
  }

  const year = data?.year ?? new Date().getFullYear()
  const monthly = data?.monthly ?? Array.from({ length: 12 }, (_, i) => ({ month: i + 1, inbound: 0, outbound: 0 }))

  return (
    <div style={{ padding: 24 }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Row gutter={16}>
          <Col span={6}><Card><Statistic title="物资总数" value={data?.total_items ?? 0} /></Card></Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="库存不足"
                value={data?.alert_count ?? 0}
                valueStyle={{ color: (data?.alert_count ?? 0) > 0 ? '#cf1322' : undefined }}
                suffix={<Tag color="red">预警</Tag>}
              />
            </Card>
          </Col>
          <Col span={12}>
            <Card>
              <Space direction="vertical">
                <Button type="primary" icon={<SendOutlined />} loading={pushing} onClick={handlePush}>
                  推送库存不足物料
                </Button>
                <Typography.Text type="secondary">
                  推送到通知设置中配置的接收人；判定口径：
                  {data?.warning_source === 'local_threshold' ? '当前库存≤警戒库存' : '飞书库存报警字段'}
                </Typography.Text>
              </Space>
            </Card>
          </Col>
        </Row>

        <Card title={<Title level={5} style={{ margin: 0 }}>{year} 年月度出入库量</Title>}>
          <ReactECharts option={buildMonthlyOption(monthly)} style={{ height: 320 }} notMerge lazyUpdate />
        </Card>

        {data && data.alert_count > 0 && (
          <Card title="库存不足物料">
            <Table
              rowKey="record_id"
              size="small"
              columns={alertColumns}
              dataSource={data.low_stock_items}
              pagination={false}
            />
          </Card>
        )}
      </Space>
    </div>
  )
}
