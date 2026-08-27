'use client'

import {
  CloudUploadOutlined,
  FileSearchOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
  type TableColumnsType,
} from 'antd'
import { useCallback, useMemo, useState, useTransition } from 'react'

import {
  closeOosOotRecord,
  createOosOotRecord,
  createOotLimitItem,
  createOotLimitProduct,
  startOosOotInvestigation,
  syncOosOotRecordToFeishu,
  syncOotLimitProductToFeishu,
} from '@/actions/quality'
import {
  fetchOosOotRecords,
  fetchOotLimitItems,
  fetchOotLimitProducts,
  type OosOotRecord,
  type OotLimitItem,
  type OotLimitProduct,
} from '@/lib/api/quality-oos-oot'
import type { components } from '@/types/generated/schema'
import type { CreateOosOotRecordRequest, CloseOosOotRecordRequest } from '@/types/quality'

type RecordCreateInput = CreateOosOotRecordRequest
type ProductCreateInput = components['schemas']['CreateOotLimitProductRequest']
type ItemCreateInput = components['schemas']['CreateOotLimitItemRequest']
type RecordCloseInput = CloseOosOotRecordRequest

type Notice = { type: 'success' | 'error' | 'info'; text: string } | null
type RecordStatus = 'open' | 'investigating' | 'closed'

function statusTag(status: OosOotRecord['status']) {
  const tags: Record<OosOotRecord['status'], { color: string; label: string }> = {
    open: { color: 'default', label: '待调查' },
    investigating: { color: 'processing', label: '调查中' },
    closed: { color: 'success', label: '已关闭' },
  }
  return <Tag color={tags[status].color}>{tags[status].label}</Tag>
}

function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString('zh-CN') : '-'
}

export function OosOotManagementPage() {
  const queryClient = useQueryClient()
  const [recordType, setRecordType] = useState<'OOS' | 'OOT' | undefined>()
  const [recordStatus, setRecordStatus] = useState<RecordStatus | undefined>()
  const [notice, setNotice] = useState<Notice>(null)
  const [recordDrawerOpen, setRecordDrawerOpen] = useState(false)
  const [productDrawerOpen, setProductDrawerOpen] = useState(false)
  const [itemDrawerOpen, setItemDrawerOpen] = useState(false)
  const [closingRecord, setClosingRecord] = useState<OosOotRecord | null>(null)
  const [selectedProductId, setSelectedProductId] = useState<string | undefined>()
  const [isPending, startTransition] = useTransition()
  const [recordForm] = Form.useForm<RecordCreateInput>()
  const [productForm] = Form.useForm<ProductCreateInput>()
  const [itemForm] = Form.useForm<ItemCreateInput>()
  const [closeForm] = Form.useForm<RecordCloseInput>()

  const recordsQuery = useQuery({
    queryKey: ['quality-oos-oot-records', recordType, recordStatus],
    queryFn: () =>
      fetchOosOotRecords({ recordType, status: recordStatus, page: 1, pageSize: 50 }),
  })
  const productsQuery = useQuery({
    queryKey: ['quality-oot-limit-products'],
    queryFn: fetchOotLimitProducts,
  })
  const currentProductId = selectedProductId ?? productsQuery.data?.data[0]?.id
  const itemsQuery = useQuery({
    queryKey: ['quality-oot-limit-items', currentProductId],
    queryFn: () => fetchOotLimitItems(currentProductId!),
    enabled: Boolean(currentProductId),
  })

  const refreshRecords = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ['quality-oos-oot-records'] }),
    [queryClient],
  )
  const refreshProducts = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ['quality-oot-limit-products'] }),
    [queryClient],
  )
  const refreshItems = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ['quality-oot-limit-items'] }),
    [queryClient],
  )

  const recordColumns = useMemo<TableColumnsType<OosOotRecord>>(
    () => [
      {
        title: '类型 / 编号',
        key: 'code',
        render: (_, record) => (
          <Space direction="vertical" size={0}>
            <Tag color={record.record_type === 'OOS' ? 'error' : 'warning'}>{record.record_type}</Tag>
            <Typography.Text strong>{record.record_code}</Typography.Text>
          </Space>
        ),
      },
      {
        title: '事件与批次',
        key: 'subject',
        render: (_, record) => (
          <Space direction="vertical" size={0}>
            <Typography.Text>{record.title}</Typography.Text>
            <Typography.Text type="secondary">
              {[record.product_name, record.batch_number].filter(Boolean).join(' / ') || '-'}
            </Typography.Text>
          </Space>
        ),
      },
      { title: '检验项目', dataIndex: 'test_item', key: 'test_item', render: (value) => value || '-' },
      { title: '发现日期', dataIndex: 'discovery_date', key: 'discovery_date', render: formatDate },
      { title: '状态', dataIndex: 'status', key: 'status', render: statusTag },
      {
        title: '操作',
        key: 'actions',
        width: 290,
        render: (_, record) => (
          <Space wrap>
            {record.status === 'open' ? (
              <Button
                size="small"
                icon={<FileSearchOutlined />}
                onClick={() => {
                  startTransition(async () => {
                    try {
                      await startOosOotInvestigation(record.id)
                      setNotice({ type: 'success', text: `已启动 ${record.record_code} 的调查` })
                      await refreshRecords()
                    } catch (error) {
                      setNotice({ type: 'error', text: error instanceof Error ? error.message : '启动调查失败' })
                    }
                  })
                }}
              >
                启动调查
              </Button>
            ) : null}
            {record.status === 'investigating' ? (
              <Button size="small" type="primary" onClick={() => setClosingRecord(record)}>
                关闭
              </Button>
            ) : null}
            <Button
              size="small"
              icon={<CloudUploadOutlined />}
              loading={isPending}
              onClick={() => {
                startTransition(async () => {
                  try {
                    const result = await syncOosOotRecordToFeishu(record.id)
                    setNotice({ type: 'success', text: `已推送 ${record.record_code} 至飞书表 ${result.table_id}` })
                  } catch (error) {
                    setNotice({ type: 'error', text: error instanceof Error ? error.message : '推送飞书失败' })
                  }
                })
              }}
            >
              推送飞书
            </Button>
          </Space>
        ),
      },
    ],
    [isPending, refreshRecords, startTransition],
  )

  const productColumns = useMemo<TableColumnsType<OotLimitProduct>>(
    () => [
      { title: '产品编码', dataIndex: 'product_code', key: 'product_code' },
      { title: '产品名称', dataIndex: 'product_name', key: 'product_name' },
      { title: '标准文件', key: 'document', render: (_, record) => [record.document_title, record.version_label].filter(Boolean).join(' / ') || '-' },
      { title: '状态', dataIndex: 'is_active', key: 'is_active', render: (value) => value ? <Tag color="success">启用</Tag> : <Tag>停用</Tag> },
      {
        title: '操作',
        key: 'actions',
        render: (_, record) => (
          <Button
            size="small"
            icon={<CloudUploadOutlined />}
            onClick={() => {
              startTransition(async () => {
                try {
                  const result = await syncOotLimitProductToFeishu(record.id)
                  setNotice({ type: 'success', text: `已推送 ${record.product_code} 至飞书表 ${result.table_id}` })
                } catch (error) {
                  setNotice({ type: 'error', text: error instanceof Error ? error.message : '推送飞书失败' })
                }
              })
            }}
          >
            推送飞书
          </Button>
        ),
      },
    ],
    [startTransition],
  )

  const itemColumns: TableColumnsType<OotLimitItem> = [
    { title: '顺序', dataIndex: 'display_order', key: 'display_order', width: 70 },
    { title: '分组', dataIndex: 'item_group', key: 'item_group', render: (value) => value || '-' },
    { title: '项目名称', dataIndex: 'item_name', key: 'item_name' },
    { title: '标准规定', dataIndex: 'specification', key: 'specification', render: (value) => value || '-' },
    { title: 'OOT 限度', dataIndex: 'oot_limit', key: 'oot_limit' },
  ]

  const records = recordsQuery.data?.data ?? []
  const products = productsQuery.data?.data ?? []
  const items = itemsQuery.data?.data ?? []
  const closedCount = records.filter((record) => record.status === 'closed').length

  if (recordsQuery.isLoading || productsQuery.isLoading) return <Spin size="large" />

  if (recordsQuery.error || productsQuery.error) {
    const error = recordsQuery.error || productsQuery.error
    return (
      <Alert
        type="error"
        showIcon
        title="OOS/OOT 工作台加载失败"
        description={(error instanceof Error ? error.message : '') ?? '请稍后重试'}
        action={<Button onClick={() => void refreshRecords()}>重试</Button>}
      />
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ display: 'flex' }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          OOS/OOT 管理
        </Typography.Title>
        <Typography.Text type="secondary">
          平台台账承载受控状态流转；关闭前必须完成调查结论，飞书仅按人工操作单条推送。
        </Typography.Text>
      </div>

      {notice ? <Alert closable showIcon type={notice.type} title={notice.text} onClose={() => setNotice(null)} /> : null}

      <Tabs
        items={[
          {
            key: 'ledger',
            label: 'OOS/OOT 台账',
            children: (
              <Space direction="vertical" size={16} style={{ display: 'flex' }}>
                <Row gutter={[16, 16]}>
                  <Col xs={24} sm={8}><Card size="small"><Statistic title="当前记录" value={records.length} suffix="条" /></Card></Col>
                  <Col xs={24} sm={8}><Card size="small"><Statistic title="调查中" value={records.filter((record) => record.status === 'investigating').length} suffix="条" /></Card></Col>
                  <Col xs={24} sm={8}><Card size="small"><Statistic title="已关闭" value={closedCount} suffix="条" /></Card></Col>
                </Row>
                <Card
                  title="OOS/OOT 受控台账"
                  extra={<Space wrap><Select allowClear placeholder="类型" style={{ width: 110 }} options={[{ value: 'OOS', label: 'OOS' }, { value: 'OOT', label: 'OOT' }]} onChange={setRecordType} /><Select allowClear placeholder="状态" style={{ width: 120 }} options={[{ value: 'open', label: '待调查' }, { value: 'investigating', label: '调查中' }, { value: 'closed', label: '已关闭' }]} onChange={setRecordStatus} /><Button icon={<ReloadOutlined />} onClick={() => void refreshRecords()}>刷新</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setRecordDrawerOpen(true)}>新增记录</Button></Space>}
                >
                  <Table<OosOotRecord> rowKey="id" columns={recordColumns} dataSource={records} scroll={{ x: 1100 }} pagination={false} locale={{ emptyText: <Empty description="暂无 OOS/OOT 记录" /> }} />
                </Card>
              </Space>
            ),
          },
          {
            key: 'limits',
            label: 'OOT 限度',
            children: (
              <Row gutter={[16, 16]}>
                <Col xs={24} xl={13}>
                  <Card title="产品限度主数据" extra={<Space><Button icon={<ReloadOutlined />} onClick={() => void refreshProducts()}>刷新</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setProductDrawerOpen(true)}>新增产品</Button></Space>}>
                    <Table<OotLimitProduct> rowKey="id" columns={productColumns} dataSource={products} pagination={false} size="small" onRow={(record) => ({ onClick: () => setSelectedProductId(record.id), style: { cursor: 'pointer', background: currentProductId === record.id ? '#f6f0ff' : undefined } })} />
                  </Card>
                </Col>
                <Col xs={24} xl={11}>
                  <Card title="限度项目" extra={<Space><Select value={currentProductId} placeholder="选择产品" style={{ minWidth: 180 }} options={products.map((product) => ({ value: product.id, label: `${product.product_code} · ${product.product_name}` }))} onChange={setSelectedProductId} /><Button type="primary" disabled={!currentProductId} icon={<PlusOutlined />} onClick={() => setItemDrawerOpen(true)}>新增项目</Button></Space>}>
                    <Table<OotLimitItem> rowKey="id" columns={itemColumns} dataSource={items} loading={itemsQuery.isLoading} pagination={false} size="small" locale={{ emptyText: <Empty description="选择产品后维护 OOT 限度项目" /> }} />
                  </Card>
                </Col>
              </Row>
            ),
          },
        ]}
      />

      <Drawer title="新增 OOS/OOT 记录" width={560} open={recordDrawerOpen} onClose={() => setRecordDrawerOpen(false)} destroyOnHidden>
        <Form<RecordCreateInput> form={recordForm} layout="vertical" initialValues={{ record_type: 'OOS' }} onFinish={(values) => { startTransition(async () => { try { await createOosOotRecord(values); message.success('OOS/OOT 记录已创建'); recordForm.resetFields(); setRecordDrawerOpen(false); await refreshRecords() } catch (error) { message.error(error instanceof Error ? error.message : '创建失败') } }) }}>
          <Row gutter={16}><Col span={12}><Form.Item name="record_type" label="记录类型" rules={[{ required: true }]}><Select options={[{ value: 'OOS', label: 'OOS（超标）' }, { value: 'OOT', label: 'OOT（超趋势）' }]} /></Form.Item></Col><Col span={12}><Form.Item name="record_code" label="记录编号" rules={[{ required: true }]}><Input placeholder="例如 OOS-202607-001" /></Form.Item></Col></Row>
          <Form.Item name="title" label="事件标题" rules={[{ required: true }]}><Input /></Form.Item>
          <Row gutter={16}><Col span={12}><Form.Item name="product_name" label="产品名称"><Input /></Form.Item></Col><Col span={12}><Form.Item name="batch_number" label="批号"><Input /></Form.Item></Col></Row>
          <Row gutter={16}><Col span={12}><Form.Item name="test_item" label="检验项目"><Input /></Form.Item></Col><Col span={12}><Form.Item name="discovery_date" label="发现日期"><Input type="date" /></Form.Item></Col></Row>
          <Form.Item name="specification" label="标准规定"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="test_result" label="检验结果"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="description" label="事件描述"><Input.TextArea rows={3} /></Form.Item>
          <Button type="primary" htmlType="submit" loading={isPending}>创建记录</Button>
        </Form>
      </Drawer>

      <Drawer title="新增 OOT 限度产品" width={480} open={productDrawerOpen} onClose={() => setProductDrawerOpen(false)} destroyOnHidden>
        <Form<ProductCreateInput> form={productForm} layout="vertical" initialValues={{ is_active: true }} onFinish={(values) => { startTransition(async () => { try { const product = await createOotLimitProduct(values); message.success('OOT 限度产品已创建'); productForm.resetFields(); setProductDrawerOpen(false); setSelectedProductId(product.id); await refreshProducts() } catch (error) { message.error(error instanceof Error ? error.message : '创建失败') } }) }}>
          <Form.Item name="product_code" label="产品编码" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="product_name" label="产品名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="document_title" label="标准文件标题" rules={[{ required: true }]}><Input /></Form.Item><Row gutter={16}><Col span={12}><Form.Item name="document_year" label="年份"><Input type="number" /></Form.Item></Col><Col span={12}><Form.Item name="version_label" label="版本"><Input /></Form.Item></Col></Row><Form.Item name="remark" label="备注"><Input.TextArea rows={2} /></Form.Item><Button type="primary" htmlType="submit" loading={isPending}>创建产品</Button>
        </Form>
      </Drawer>

      <Drawer title="新增 OOT 限度项目" width={480} open={itemDrawerOpen} onClose={() => setItemDrawerOpen(false)} destroyOnHidden>
        <Form<ItemCreateInput> form={itemForm} layout="vertical" initialValues={{ display_order: (items.at(-1)?.display_order ?? 0) + 1 }} onFinish={(values) => { if (!currentProductId) return; startTransition(async () => { try { await createOotLimitItem(currentProductId, values); message.success('OOT 限度项目已创建'); itemForm.resetFields(); setItemDrawerOpen(false); await refreshItems() } catch (error) { message.error(error instanceof Error ? error.message : '创建失败') } }) }}>
          <Row gutter={16}><Col span={12}><Form.Item name="display_order" label="显示顺序" rules={[{ required: true }]}><Input type="number" /></Form.Item></Col><Col span={12}><Form.Item name="item_group" label="项目分组"><Input /></Form.Item></Col></Row><Form.Item name="item_name" label="项目名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="specification" label="标准规定"><Input.TextArea rows={2} /></Form.Item><Form.Item name="oot_limit" label="OOT 限度" rules={[{ required: true }]}><Input.TextArea rows={2} /></Form.Item><Form.Item name="remark" label="备注"><Input.TextArea rows={2} /></Form.Item><Button type="primary" htmlType="submit" loading={isPending}>创建项目</Button>
        </Form>
      </Drawer>

      <Modal title={`关闭 ${closingRecord?.record_code ?? ''}`} open={Boolean(closingRecord)} onCancel={() => setClosingRecord(null)} footer={null} destroyOnHidden>
        <Typography.Paragraph type="secondary">关闭是受控业务动作，必须记录调查结论。</Typography.Paragraph>
        <Form<RecordCloseInput> form={closeForm} layout="vertical" onFinish={(values) => { if (!closingRecord) return; startTransition(async () => { try { await closeOosOotRecord(closingRecord.id, values); message.success('记录已关闭'); closeForm.resetFields(); setClosingRecord(null); await refreshRecords() } catch (error) { message.error(error instanceof Error ? error.message : '关闭失败') } }) }}>
          <Form.Item name="investigation_result" label="调查结论" rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item><Form.Item name="corrective_actions" label="纠正预防措施"><Input.TextArea rows={3} /></Form.Item><Button type="primary" danger htmlType="submit" loading={isPending} icon={<SafetyCertificateOutlined />}>确认关闭</Button>
        </Form>
      </Modal>
    </Space>
  )
}
