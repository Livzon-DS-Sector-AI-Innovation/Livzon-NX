'use client'

import { useState } from 'react'
import { App, Button, Card, Col, Descriptions, Modal, Row, Space, Statistic, Table, Tag, Typography } from 'antd'
import { SendOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { useQuery } from '@tanstack/react-query'
import { fetchItemsDashboard } from '@/lib/api/client/quality'
import { pushItemsLowStock } from '@/actions/quality-inspection'
import type { ColumnsType } from 'antd/es/table'
import type { ItemsStockAlertItemRow } from '@/types/quality'
import { renderFeishuValue } from './renderFeishuValue'

const { Title } = Typography

const ENTITY = 'qc_items_inventory'

function buildMonthlyOption(monthly: { month: number; inbound: number; outbound: number }[]): EChartsOption {
  return {
    tooltip: { trigger: 'axis' },
    // 图例固定在图表上方，避免默认位置压住 X 轴月份刻度
    legend: { data: ['入库量', '出库量'], top: 0, left: 'center' },
    grid: { left: 48, right: 24, top: 40, bottom: 28 },
    xAxis: { type: 'category', data: monthly.map((m) => `${m.month}月`) },
    yAxis: { type: 'value' },
    series: [
      { name: '入库量', type: 'bar', data: monthly.map((m) => m.inbound), itemStyle: { color: '#52c41a' } },
      { name: '出库量', type: 'bar', data: monthly.map((m) => m.outbound), itemStyle: { color: '#fa8c16' } },
    ],
  }
}

export function ItemsDashboard() {
  const { message } = App.useApp()
  const [pushing, setPushing] = useState(false)
  const [detailItem, setDetailItem] = useState<ItemsStockAlertItemRow | null>(null)
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

  const alertColumns: ColumnsType<ItemsStockAlertItemRow> = [
    {
      title: '物资名称',
      dataIndex: 'name',
      key: 'name',
      render: (value: string, record) => (
        <Button type="link" style={{ padding: 0 }} onClick={() => setDetailItem(record)}>
          {value || '未命名'}
        </Button>
      ),
    },
    { title: '规格型号', dataIndex: 'specification', key: 'specification' },
    { title: '存放位置', dataIndex: 'location', key: 'location' },
    { title: '当前库存', dataIndex: 'current_stock', key: 'current_stock' },
    { title: '警戒库存', dataIndex: 'warning_stock', key: 'warning_stock' },
  ]

  const year = data?.year ?? new Date().getFullYear()
  const monthly = data?.monthly ?? Array.from({ length: 12 }, (_, i) => ({ month: i + 1, inbound: 0, outbound: 0 }))

  const detailEntries: [string, unknown][] = detailItem
    ? detailItem.fields && Object.keys(detailItem.fields).length > 0
      ? Object.entries(detailItem.fields)
      : [
          ['物资名称', detailItem.name],
          ['规格型号', detailItem.specification],
          ['存放位置', detailItem.location],
          ['当前库存', detailItem.current_stock],
          ['警戒库存', detailItem.warning_stock],
          ['单位', detailItem.unit],
        ]
    : []

  return (
    <div style={{ padding: 24 }}>
      <Title level={4} style={{ marginTop: 0 }}>物品管理</Title>
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
              onRow={(record) => ({
                onClick: () => setDetailItem(record),
                style: { cursor: 'pointer' },
              })}
            />
          </Card>
        )}
      </Space>

      <Modal
        open={!!detailItem}
        title={`物料详情${detailItem?.name ? `：${detailItem.name}` : ''}`}
        footer={<Button onClick={() => setDetailItem(null)}>关闭</Button>}
        onCancel={() => setDetailItem(null)}
        width={680}
      >
        <Descriptions bordered size="small" column={1} styles={{ label: { width: 180 } }}>
          {detailEntries.map(([field, value]) => (
            <Descriptions.Item key={field} label={field}>
              {renderFeishuValue(
                value,
                (detailItem?.fields ?? {}) as Record<string, unknown>,
                ENTITY,
                message,
                { fieldName: field }
              )}
            </Descriptions.Item>
          ))}
        </Descriptions>
      </Modal>
    </div>
  )
}

