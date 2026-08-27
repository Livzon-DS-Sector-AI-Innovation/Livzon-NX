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
import { useEffect, useMemo, useState, useTransition } from 'react'

import {
  approveQualityProductRecord,
  closeQualityComplaint,
  completeQualityProductRecord,
  completeQualityReturnRecall,
  createQualityComplaint,
  createQualityProductRecord,
  createQualityProductStandardItem,
  createQualityReturnRecall,
  createQualitySupplier,
  createQualitySupplierQualification,
  respondQualityComplaint,
  startQualityComplaintInvestigation,
  startQualityReturnRecallAssessment,
  startQualityReturnRecallProcessing,
  syncExternalQualityRecordToFeishu,
} from '@/actions/quality'
import {
  fetchComplaints,
  fetchProductQualityRecords,
  fetchProductQualityStandardItems,
  fetchReturnRecalls,
  fetchSupplierQualifications,
  fetchSuppliers,
  type Complaint,
  type ProductQualityRecord,
  type ProductQualityStandardItem,
  type ReturnRecall,
  type Supplier,
  type SupplierQualification,
} from '@/lib/api/quality-external'
import type { components } from '@/types/generated/schema'

type ExternalQualityTab = 'suppliers' | 'complaints' | 'return-recalls' | 'product-quality'
type SupplierCreateInput = components['schemas']['CreateSupplierRequest']
type SupplierQualificationCreateInput =
  components['schemas']['app__modules__quality__schemas__external_quality__CreateSupplierQualificationRequest']
type ComplaintCreateInput = components['schemas']['CreateComplaintRequest']
type ComplaintResponseInput = components['schemas']['RespondComplaintRequest']
type ReturnRecallCreateInput = components['schemas']['CreateReturnRecallRequest']
type ReturnRecallCompleteInput = components['schemas']['CompleteReturnRecallRequest']
type ProductQualityCreateInput = Record<string, unknown>
type ProductQualityCompleteInput = components['schemas']['CompleteProductQualityRecordRequest']
type ProductQualityStandardItemCreateInput = components['schemas']['CreateProductQualityStandardItemRequest']

type Notice = { type: 'success' | 'error' | 'info'; text: string } | null

const TAB_LABELS: Record<ExternalQualityTab, string> = {
  suppliers: '供应商与资质',
  complaints: '客户投诉',
  'return-recalls': '退货与召回',
  'product-quality': '产品质量标准',
}

function statusTag(status: string) {
  const mapping: Record<string, { color: string; label: string }> = {
    active: { color: 'success', label: '启用' },
    suspended: { color: 'warning', label: '暂停' },
    blacklisted: { color: 'error', label: '黑名单' },
    pending: { color: 'default', label: '待处理' },
    valid: { color: 'success', label: '有效' },
    expiring: { color: 'warning', label: '即将到期' },
    expired: { color: 'error', label: '已到期' },
    invalid: { color: 'error', label: '失效' },
    investigating: { color: 'processing', label: '调查中' },
    responded: { color: 'cyan', label: '已回复' },
    closed: { color: 'success', label: '已关闭' },
    assessing: { color: 'processing', label: '评估中' },
    processing: { color: 'warning', label: '处置中' },
    completed: { color: 'success', label: '已完成' },
    draft: { color: 'default', label: '草稿' },
    approved: { color: 'success', label: '已批准' },
  }
  const item = mapping[status] ?? { color: 'default', label: status }
  return <Tag color={item.color}>{item.label}</Tag>
}

function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString('zh-CN') : '-'
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export function ExternalQualityManagementPage({ initialTab }: { initialTab: ExternalQualityTab }) {
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<Notice>(null)
  const [supplierDrawerOpen, setSupplierDrawerOpen] = useState(false)
  const [qualificationDrawerOpen, setQualificationDrawerOpen] = useState(false)
  const [complaintDrawerOpen, setComplaintDrawerOpen] = useState(false)
  const [returnRecallDrawerOpen, setReturnRecallDrawerOpen] = useState(false)
  const [productQualityDrawerOpen, setProductQualityDrawerOpen] = useState(false)
  const [standardItemDrawerOpen, setStandardItemDrawerOpen] = useState(false)
  const [respondingComplaint, setRespondingComplaint] = useState<Complaint | null>(null)
  const [completingReturnRecall, setCompletingReturnRecall] = useState<ReturnRecall | null>(null)
  const [completingProductQuality, setCompletingProductQuality] = useState<ProductQualityRecord | null>(null)
  const [selectedSupplierId, setSelectedSupplierId] = useState<string>()
  const [selectedProductQualityId, setSelectedProductQualityId] = useState<string>()
  const [isPending, startTransition] = useTransition()
  const [supplierForm] = Form.useForm<SupplierCreateInput>()
  const [qualificationForm] = Form.useForm<SupplierQualificationCreateInput>()
  const [complaintForm] = Form.useForm<ComplaintCreateInput>()
  const [complaintResponseForm] = Form.useForm<ComplaintResponseInput>()
  const [returnRecallForm] = Form.useForm<ReturnRecallCreateInput>()
  const [returnRecallCompleteForm] = Form.useForm<ReturnRecallCompleteInput>()
  const [productQualityForm] = Form.useForm<ProductQualityCreateInput>()
  const [productQualityCompleteForm] = Form.useForm<ProductQualityCompleteInput>()
  const [standardItemForm] = Form.useForm<ProductQualityStandardItemCreateInput>()

  const suppliersQuery = useQuery({ queryKey: ['quality-external-suppliers'], queryFn: fetchSuppliers })
  const qualificationsQuery = useQuery({
    queryKey: ['quality-external-supplier-qualifications', selectedSupplierId],
    queryFn: () => fetchSupplierQualifications(selectedSupplierId!),
    enabled: Boolean(selectedSupplierId),
  })
  const complaintsQuery = useQuery({ queryKey: ['quality-external-complaints'], queryFn: fetchComplaints })
  const returnRecallsQuery = useQuery({ queryKey: ['quality-external-return-recalls'], queryFn: fetchReturnRecalls })
  const productQualityQuery = useQuery({
    queryKey: ['quality-external-product-quality'],
    queryFn: fetchProductQualityRecords,
  })
  const standardItemsQuery = useQuery({
    queryKey: ['quality-external-product-quality-standard-items', selectedProductQualityId],
    queryFn: () => fetchProductQualityStandardItems(selectedProductQualityId!),
    enabled: Boolean(selectedProductQualityId),
  })

  useEffect(() => {
    if (!selectedSupplierId && suppliersQuery.data?.data[0]) setSelectedSupplierId(suppliersQuery.data.data[0].id)
  }, [selectedSupplierId, suppliersQuery.data])

  useEffect(() => {
    if (!selectedProductQualityId && productQualityQuery.data?.data[0]) {
      setSelectedProductQualityId(productQualityQuery.data.data[0].id)
    }
  }, [productQualityQuery.data, selectedProductQualityId])

  const refreshSuppliers = () => queryClient.invalidateQueries({ queryKey: ['quality-external-suppliers'] })
  const refreshQualifications = () => queryClient.invalidateQueries({ queryKey: ['quality-external-supplier-qualifications'] })
  const refreshComplaints = () => queryClient.invalidateQueries({ queryKey: ['quality-external-complaints'] })
  const refreshReturnRecalls = () => queryClient.invalidateQueries({ queryKey: ['quality-external-return-recalls'] })
  const refreshProductQuality = () => queryClient.invalidateQueries({ queryKey: ['quality-external-product-quality'] })
  const refreshStandardItems = () => queryClient.invalidateQueries({ queryKey: ['quality-external-product-quality-standard-items'] })

  const suppliers = suppliersQuery.data?.data ?? []
  const qualifications = qualificationsQuery.data?.data ?? []
  const complaints = complaintsQuery.data?.data ?? []
  const returnRecalls = returnRecallsQuery.data?.data ?? []
  const productQualityRecords = productQualityQuery.data?.data ?? []
  const standardItems = standardItemsQuery.data?.data ?? []

  const syncRecord = (resourcePath: string, recordId: string, displayCode: string) => {
    startTransition(async () => {
      try {
        const result = await syncExternalQualityRecordToFeishu(resourcePath, recordId)
        setNotice({ type: 'success', text: `已将 ${displayCode} 推送至飞书表 ${result.table_id}` })
      } catch (error) {
        setNotice({ type: 'error', text: errorText(error, '推送飞书失败') })
      }
    })
  }

  const supplierColumns = useMemo<TableColumnsType<Supplier>>(
    () => [
      { title: '供应商编号', dataIndex: 'supplier_code', key: 'supplier_code', width: 150 },
      { title: '供应商名称', dataIndex: 'name', key: 'name', width: 190 },
      { title: '类别', dataIndex: 'category', key: 'category', render: (value) => value || '-' },
      {
        title: '资质状态',
        dataIndex: 'qualification_status',
        key: 'qualification_status',
        filters: ['pending', 'valid', 'expiring', 'expired', 'invalid'].map((value) => ({ value, text: statusTag(value) })),
        onFilter: (value, record) => record.qualification_status === String(value),
        render: statusTag,
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        filters: ['active', 'suspended', 'blacklisted'].map((value) => ({ value, text: statusTag(value) })),
        onFilter: (value, record) => record.status === String(value),
        render: statusTag,
      },
      {
        title: '操作',
        key: 'actions',
        width: 130,
        render: (_, record) => (
          <Button size="small" icon={<CloudUploadOutlined />} loading={isPending} onClick={() => syncRecord('suppliers', record.id, record.supplier_code)}>
            推送飞书
          </Button>
        ),
      },
    ],
    [isPending],
  )

  const qualificationColumns: TableColumnsType<SupplierQualification> = [
    { title: '资质编号', dataIndex: 'qualification_code', key: 'qualification_code' },
    { title: '资质名称', dataIndex: 'qualification_name', key: 'qualification_name' },
    { title: '到期日期', dataIndex: 'expiry_date', key: 'expiry_date', render: formatDate },
    { title: '状态', dataIndex: 'status', key: 'status', render: statusTag },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => (
        <Button size="small" icon={<CloudUploadOutlined />} loading={isPending} onClick={() => syncRecord('supplier-qualifications', record.id, record.qualification_code)}>
          推送
        </Button>
      ),
    },
  ]

  const complaintColumns = useMemo<TableColumnsType<Complaint>>(
    () => [
      { title: '投诉编号', dataIndex: 'complaint_code', key: 'complaint_code', width: 150 },
      {
        title: '投诉事项',
        key: 'subject',
        render: (_, record) => (
          <Space direction="vertical" size={0}>
            <Typography.Text strong>{record.title}</Typography.Text>
            <Typography.Text type="secondary">{[record.customer_name, record.product_name, record.batch_number].filter(Boolean).join(' / ') || '-'}</Typography.Text>
          </Space>
        ),
      },
      { title: '日期', dataIndex: 'complaint_date', key: 'complaint_date', render: formatDate },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        filters: ['pending', 'investigating', 'responded', 'closed'].map((value) => ({ value, text: statusTag(value) })),
        onFilter: (value, record) => record.status === String(value),
        render: statusTag,
      },
      {
        title: '操作',
        key: 'actions',
        width: 280,
        render: (_, record) => (
          <Space wrap>
            {record.status === 'pending' ? <Button size="small" icon={<FileSearchOutlined />} onClick={() => startTransition(async () => { try { await startQualityComplaintInvestigation(record.id); message.success('已启动投诉调查'); await refreshComplaints() } catch (error) { message.error(errorText(error, '启动调查失败')) } })}>启动调查</Button> : null}
            {record.status === 'investigating' ? <Button size="small" type="primary" onClick={() => setRespondingComplaint(record)}>提交回复</Button> : null}
            {record.status === 'responded' ? <Button size="small" type="primary" danger onClick={() => startTransition(async () => { try { await closeQualityComplaint(record.id); message.success('投诉已关闭'); await refreshComplaints() } catch (error) { message.error(errorText(error, '关闭投诉失败')) } })}>关闭</Button> : null}
            <Button size="small" icon={<CloudUploadOutlined />} loading={isPending} onClick={() => syncRecord('complaints', record.id, record.complaint_code)}>推送</Button>
          </Space>
        ),
      },
    ],
    [isPending],
  )

  const returnRecallColumns = useMemo<TableColumnsType<ReturnRecall>>(
    () => [
      {
        title: '类型 / 编号',
        key: 'code',
        render: (_, record) => <Space direction="vertical" size={0}><Tag color={record.record_type === 'recall' ? 'error' : 'warning'}>{record.record_type === 'recall' ? '召回' : '退货'}</Tag><Typography.Text strong>{record.record_code}</Typography.Text></Space>,
      },
      { title: '事项', dataIndex: 'title', key: 'title' },
      { title: '产品 / 批号', key: 'product', render: (_, record) => [record.product_name, record.batch_number].filter(Boolean).join(' / ') || '-' },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        filters: ['pending', 'assessing', 'processing', 'completed'].map((value) => ({ value, text: statusTag(value) })),
        onFilter: (value, record) => record.status === String(value),
        render: statusTag,
      },
      {
        title: '操作',
        key: 'actions',
        width: 320,
        render: (_, record) => (
          <Space wrap>
            {record.status === 'pending' ? <Button size="small" icon={<FileSearchOutlined />} onClick={() => startTransition(async () => { try { await startQualityReturnRecallAssessment(record.id); message.success('已启动评估'); await refreshReturnRecalls() } catch (error) { message.error(errorText(error, '启动评估失败')) } })}>启动评估</Button> : null}
            {record.status === 'assessing' ? <Button size="small" onClick={() => startTransition(async () => { try { await startQualityReturnRecallProcessing(record.id, {}); message.success('已进入处置'); await refreshReturnRecalls() } catch (error) { message.error(errorText(error, '启动处置失败')) } })}>进入处置</Button> : null}
            {record.status === 'processing' ? <Button size="small" type="primary" onClick={() => setCompletingReturnRecall(record)}>完成</Button> : null}
            <Button size="small" icon={<CloudUploadOutlined />} loading={isPending} onClick={() => syncRecord('return-recalls', record.id, record.record_code)}>推送</Button>
          </Space>
        ),
      },
    ],
    [isPending],
  )

  const productQualityColumns = useMemo<TableColumnsType<ProductQualityRecord>>(
    () => [
      { title: '质量记录编号', dataIndex: 'record_code', key: 'record_code', width: 160 },
      {
        title: '类型',
        dataIndex: 'record_type',
        key: 'record_type',
        filters: [{ value: 'annual_review', text: '年度回顾' }, { value: 'customer_standard', text: '客户标准' }],
        onFilter: (value, record) => record.record_type === String(value),
        render: (value) => <Tag>{value === 'annual_review' ? '年度回顾' : '客户标准'}</Tag>,
      },
      { title: '标题 / 产品', key: 'subject', render: (_, record) => <Space direction="vertical" size={0}><Typography.Text strong>{record.title}</Typography.Text><Typography.Text type="secondary">{record.product_name}</Typography.Text></Space> },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        filters: ['draft', 'completed', 'approved'].map((value) => ({ value, text: statusTag(value) })),
        onFilter: (value, record) => record.status === String(value),
        render: statusTag,
      },
      {
        title: '操作',
        key: 'actions',
        width: 290,
        render: (_, record) => (
          <Space wrap>
            {record.status === 'draft' ? <Button size="small" type="primary" onClick={() => setCompletingProductQuality(record)}>完成评审</Button> : null}
            {record.status === 'completed' ? <Button size="small" icon={<SafetyCertificateOutlined />} onClick={() => startTransition(async () => { try { await approveQualityProductRecord(record.id); message.success('质量记录已批准'); await refreshProductQuality() } catch (error) { message.error(errorText(error, '批准失败')) } })}>批准</Button> : null}
            <Button size="small" icon={<CloudUploadOutlined />} loading={isPending} onClick={() => syncRecord('product-quality', record.id, record.record_code)}>推送</Button>
          </Space>
        ),
      },
    ],
    [isPending],
  )

  const standardItemColumns: TableColumnsType<ProductQualityStandardItem> = [
    { title: '顺序', dataIndex: 'display_order', key: 'display_order', width: 70 },
    { title: '分类', dataIndex: 'category', key: 'category', render: (value) => value || '-' },
    { title: '要求项目', dataIndex: 'item_name', key: 'item_name' },
    { title: '要求内容', dataIndex: 'requirement', key: 'requirement', ellipsis: true },
    { title: '关键', dataIndex: 'is_critical', key: 'is_critical', render: (value) => value ? <Tag color="error">关键</Tag> : '-' },
    { title: '操作', key: 'actions', render: (_, record) => <Button size="small" icon={<CloudUploadOutlined />} loading={isPending} onClick={() => syncRecord('product-quality-standard-items', record.id, record.item_name)}>推送</Button> },
  ]

  const loading = suppliersQuery.isLoading || complaintsQuery.isLoading || returnRecallsQuery.isLoading || productQualityQuery.isLoading
  const fatalError = suppliersQuery.error || complaintsQuery.error || returnRecallsQuery.error || productQualityQuery.error

  if (loading) return <Spin size="large" />
  if (fatalError) {
    return <Alert type="error" showIcon title="外部质量工作台加载失败" description={fatalError.message} action={<Button onClick={() => void Promise.all([refreshSuppliers(), refreshComplaints(), refreshReturnRecalls(), refreshProductQuality()])}>重试</Button>} />
  }

  return (
    <Space direction="vertical" size={16} style={{ display: 'flex' }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>外部质量管理</Typography.Title>
        <Typography.Text type="secondary">平台主数据与受控流程为唯一事实来源；飞书同步仅支持管理员按单条记录手动推送。</Typography.Text>
      </div>

      {notice ? <Alert closable showIcon type={notice.type} title={notice.text} onClose={() => setNotice(null)} /> : null}

      <Tabs defaultActiveKey={initialTab} items={[
        {
          key: 'suppliers', label: TAB_LABELS.suppliers, children: (
            <Space direction="vertical" size={16} style={{ display: 'flex' }}>
              <Row gutter={[16, 16]}><Col xs={24} sm={8}><Card size="small"><Statistic title="供应商" value={suppliers.length} suffix="家" /></Card></Col><Col xs={24} sm={8}><Card size="small"><Statistic title="有效资质" value={qualifications.filter((item) => item.status === 'valid').length} suffix="项" /></Card></Col><Col xs={24} sm={8}><Card size="small"><Statistic title="待处理资质" value={qualifications.filter((item) => item.status === 'pending').length} suffix="项" /></Card></Col></Row>
              <Row gutter={[16, 16]}>
                <Col xs={24} xl={14}><Card title="供应商台账" extra={<Space><Button icon={<ReloadOutlined />} onClick={() => void refreshSuppliers()}>刷新</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setSupplierDrawerOpen(true)}>新增供应商</Button></Space>}><Table<Supplier> rowKey="id" columns={supplierColumns} dataSource={suppliers} scroll={{ x: 900 }} onRow={(record) => ({ onClick: () => setSelectedSupplierId(record.id), style: { cursor: 'pointer', background: selectedSupplierId === record.id ? '#f6f0ff' : undefined } })} locale={{ emptyText: <Empty description="暂无供应商记录" /> }} /></Card></Col>
                <Col xs={24} xl={10}><Card title="供应商资质" extra={<Space><Select value={selectedSupplierId} style={{ minWidth: 180 }} placeholder="选择供应商" options={suppliers.map((supplier) => ({ value: supplier.id, label: `${supplier.supplier_code} · ${supplier.name}` }))} onChange={setSelectedSupplierId} /><Button type="primary" disabled={!selectedSupplierId} icon={<PlusOutlined />} onClick={() => setQualificationDrawerOpen(true)}>新增资质</Button></Space>}><Table<SupplierQualification> rowKey="id" columns={qualificationColumns} dataSource={qualifications} loading={qualificationsQuery.isLoading} size="small" scroll={{ x: 650 }} locale={{ emptyText: <Empty description="选择供应商后维护资质" /> }} /></Card></Col>
              </Row>
            </Space>
          ),
        },
        {
          key: 'complaints', label: TAB_LABELS.complaints, children: (
            <Card title="客户投诉受控台账" extra={<Space><Button icon={<ReloadOutlined />} onClick={() => void refreshComplaints()}>刷新</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setComplaintDrawerOpen(true)}>新增投诉</Button></Space>}><Table<Complaint> rowKey="id" columns={complaintColumns} dataSource={complaints} scroll={{ x: 1100 }} locale={{ emptyText: <Empty description="暂无投诉记录" /> }} /></Card>
          ),
        },
        {
          key: 'return-recalls', label: TAB_LABELS['return-recalls'], children: (
            <Card title="退货与召回受控台账" extra={<Space><Button icon={<ReloadOutlined />} onClick={() => void refreshReturnRecalls()}>刷新</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setReturnRecallDrawerOpen(true)}>新增记录</Button></Space>}><Table<ReturnRecall> rowKey="id" columns={returnRecallColumns} dataSource={returnRecalls} scroll={{ x: 1100 }} locale={{ emptyText: <Empty description="暂无退货或召回记录" /> }} /></Card>
          ),
        },
        {
          key: 'product-quality', label: TAB_LABELS['product-quality'], children: (
            <Row gutter={[16, 16]}>
              <Col xs={24} xl={14}><Card title="产品质量记录" extra={<Space><Button icon={<ReloadOutlined />} onClick={() => void refreshProductQuality()}>刷新</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setProductQualityDrawerOpen(true)}>新增记录</Button></Space>}><Table<ProductQualityRecord> rowKey="id" columns={productQualityColumns} dataSource={productQualityRecords} scroll={{ x: 1050 }} onRow={(record) => ({ onClick: () => setSelectedProductQualityId(record.id), style: { cursor: 'pointer', background: selectedProductQualityId === record.id ? '#f6f0ff' : undefined } })} locale={{ emptyText: <Empty description="暂无产品质量记录" /> }} /></Card></Col>
              <Col xs={24} xl={10}><Card title="客户质量标准明细" extra={<Space><Select value={selectedProductQualityId} style={{ minWidth: 180 }} placeholder="选择记录" options={productQualityRecords.filter((record) => record.record_type === 'customer_standard').map((record) => ({ value: record.id, label: `${record.record_code} · ${record.product_name}` }))} onChange={setSelectedProductQualityId} /><Button type="primary" disabled={!selectedProductQualityId || productQualityRecords.find((record) => record.id === selectedProductQualityId)?.record_type !== 'customer_standard'} icon={<PlusOutlined />} onClick={() => setStandardItemDrawerOpen(true)}>新增明细</Button></Space>}><Table<ProductQualityStandardItem> rowKey="id" columns={standardItemColumns} dataSource={standardItems} loading={standardItemsQuery.isLoading} size="small" scroll={{ x: 700 }} locale={{ emptyText: <Empty description="选择客户质量标准后维护明细" /> }} /></Card></Col>
            </Row>
          ),
        },
      ]} />

      <Drawer title="新增供应商" width={520} open={supplierDrawerOpen} onClose={() => setSupplierDrawerOpen(false)} destroyOnHidden>
        <Form<SupplierCreateInput> form={supplierForm} layout="vertical" initialValues={{ qualification_status: 'pending', status: 'active' }} onFinish={(values) => startTransition(async () => { try { const supplier = await createQualitySupplier(values); message.success('供应商已创建'); supplierForm.resetFields(); setSupplierDrawerOpen(false); setSelectedSupplierId(supplier.id); await refreshSuppliers() } catch (error) { message.error(errorText(error, '创建供应商失败')) } })}>
          <Row gutter={16}><Col span={12}><Form.Item name="supplier_code" label="供应商编号" rules={[{ required: true }]}><Input placeholder="例如 SUP-202607-001" /></Form.Item></Col><Col span={12}><Form.Item name="name" label="供应商名称" rules={[{ required: true }]}><Input /></Form.Item></Col></Row>
          <Row gutter={16}><Col span={12}><Form.Item name="category" label="供应商类别"><Input /></Form.Item></Col><Col span={12}><Form.Item name="contact_person" label="联系人"><Input /></Form.Item></Col></Row>
          <Form.Item name="contact_phone" label="联系电话"><Input /></Form.Item><Form.Item name="scope_of_supply" label="供应范围"><Input.TextArea rows={2} /></Form.Item><Form.Item name="remark" label="备注"><Input.TextArea rows={2} /></Form.Item><Button type="primary" htmlType="submit" loading={isPending}>创建供应商</Button>
        </Form>
      </Drawer>

      <Drawer title="新增供应商资质" width={480} open={qualificationDrawerOpen} onClose={() => setQualificationDrawerOpen(false)} destroyOnHidden>
        <Form<SupplierQualificationCreateInput> form={qualificationForm} layout="vertical" initialValues={{ status: 'pending' }} onFinish={(values) => { if (!selectedSupplierId) return; startTransition(async () => { try { await createQualitySupplierQualification(selectedSupplierId, values); message.success('供应商资质已创建'); qualificationForm.resetFields(); setQualificationDrawerOpen(false); await refreshQualifications() } catch (error) { message.error(errorText(error, '创建资质失败')) } }) }}>
          <Form.Item name="qualification_code" label="资质编号" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="qualification_name" label="资质名称" rules={[{ required: true }]}><Input /></Form.Item><Row gutter={16}><Col span={12}><Form.Item name="document_no" label="文件编号"><Input /></Form.Item></Col><Col span={12}><Form.Item name="expiry_date" label="到期日期"><Input type="date" /></Form.Item></Col></Row><Form.Item name="responsible_person" label="责任人"><Input /></Form.Item><Form.Item name="remark" label="备注"><Input.TextArea rows={2} /></Form.Item><Button type="primary" htmlType="submit" loading={isPending}>创建资质</Button>
        </Form>
      </Drawer>

      <Drawer title="新增客户投诉" width={560} open={complaintDrawerOpen} onClose={() => setComplaintDrawerOpen(false)} destroyOnHidden>
        <Form<ComplaintCreateInput> form={complaintForm} layout="vertical" onFinish={(values) => startTransition(async () => { try { await createQualityComplaint(values); message.success('投诉已创建'); complaintForm.resetFields(); setComplaintDrawerOpen(false); await refreshComplaints() } catch (error) { message.error(errorText(error, '创建投诉失败')) } })}>
          <Row gutter={16}><Col span={12}><Form.Item name="complaint_code" label="投诉编号" rules={[{ required: true }]}><Input placeholder="例如 CMP-202607-001" /></Form.Item></Col><Col span={12}><Form.Item name="complaint_date" label="投诉日期"><Input type="date" /></Form.Item></Col></Row><Form.Item name="title" label="投诉标题" rules={[{ required: true }]}><Input /></Form.Item><Row gutter={16}><Col span={12}><Form.Item name="customer_name" label="客户名称"><Input /></Form.Item></Col><Col span={12}><Form.Item name="product_name" label="涉及产品"><Input /></Form.Item></Col></Row><Row gutter={16}><Col span={12}><Form.Item name="batch_number" label="批号"><Input /></Form.Item></Col><Col span={12}><Form.Item name="complaint_category" label="投诉类别"><Input /></Form.Item></Col></Row><Form.Item name="description" label="投诉描述"><Input.TextArea rows={3} /></Form.Item><Form.Item name="handler" label="处理人"><Input /></Form.Item><Button type="primary" htmlType="submit" loading={isPending}>创建投诉</Button>
        </Form>
      </Drawer>

      <Drawer title="新增退货或召回记录" width={560} open={returnRecallDrawerOpen} onClose={() => setReturnRecallDrawerOpen(false)} destroyOnHidden>
        <Form<ReturnRecallCreateInput> form={returnRecallForm} layout="vertical" initialValues={{ record_type: 'return' }} onFinish={(values) => startTransition(async () => { try { await createQualityReturnRecall(values); message.success('退货/召回记录已创建'); returnRecallForm.resetFields(); setReturnRecallDrawerOpen(false); await refreshReturnRecalls() } catch (error) { message.error(errorText(error, '创建记录失败')) } })}>
          <Row gutter={16}><Col span={12}><Form.Item name="record_type" label="记录类型" rules={[{ required: true }]}><Select options={[{ value: 'return', label: '退货' }, { value: 'recall', label: '召回' }]} /></Form.Item></Col><Col span={12}><Form.Item name="record_code" label="记录编号" rules={[{ required: true }]}><Input placeholder="例如 RCL-202607-001" /></Form.Item></Col></Row><Form.Item name="title" label="事项标题" rules={[{ required: true }]}><Input /></Form.Item><Row gutter={16}><Col span={12}><Form.Item name="product_name" label="产品名称"><Input /></Form.Item></Col><Col span={12}><Form.Item name="batch_number" label="批号"><Input /></Form.Item></Col></Row><Row gutter={16}><Col span={12}><Form.Item name="customer_name" label="客户或退货方"><Input /></Form.Item></Col><Col span={12}><Form.Item name="handler" label="处理人"><Input /></Form.Item></Col></Row><Form.Item name="reason" label="原因"><Input.TextArea rows={3} /></Form.Item><Button type="primary" htmlType="submit" loading={isPending}>创建记录</Button>
        </Form>
      </Drawer>

      <Drawer title="新增产品质量记录" width={560} open={productQualityDrawerOpen} onClose={() => setProductQualityDrawerOpen(false)} destroyOnHidden>
        <Form<ProductQualityCreateInput> form={productQualityForm} layout="vertical" initialValues={{ record_type: 'annual_review' }} onFinish={(values) => startTransition(async () => { try { const record = await createQualityProductRecord(values); message.success('产品质量记录已创建'); productQualityForm.resetFields(); setProductQualityDrawerOpen(false); setSelectedProductQualityId(record.id); await refreshProductQuality() } catch (error) { message.error(errorText(error, '创建质量记录失败')) } })}>
          <Row gutter={16}><Col span={12}><Form.Item name="record_type" label="记录类型" rules={[{ required: true }]}><Select options={[{ value: 'annual_review', label: '年度质量回顾' }, { value: 'customer_standard', label: '客户质量标准' }]} /></Form.Item></Col><Col span={12}><Form.Item name="record_code" label="质量记录编号" rules={[{ required: true }]}><Input placeholder="例如 PQR-202607-001" /></Form.Item></Col></Row><Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item><Row gutter={16}><Col span={12}><Form.Item name="product_name" label="产品名称" rules={[{ required: true }]}><Input /></Form.Item></Col><Col span={12}><Form.Item name="customer_name" label="客户名称"><Input /></Form.Item></Col></Row><Row gutter={16}><Col span={12}><Form.Item name="document_no" label="标准文件编号"><Input /></Form.Item></Col><Col span={12}><Form.Item name="document_version" label="文件版本"><Input /></Form.Item></Col></Row><Form.Item name="quality_standard" label="质量标准"><Input.TextArea rows={2} /></Form.Item><Form.Item name="special_requirements" label="特殊要求"><Input.TextArea rows={2} /></Form.Item><Button type="primary" htmlType="submit" loading={isPending}>创建质量记录</Button>
        </Form>
      </Drawer>

      <Drawer title="新增客户质量标准明细" width={520} open={standardItemDrawerOpen} onClose={() => setStandardItemDrawerOpen(false)} destroyOnHidden>
        <Form<ProductQualityStandardItemCreateInput> form={standardItemForm} layout="vertical" initialValues={{ display_order: (standardItems.at(-1)?.display_order ?? 0) + 1, is_critical: false }} onFinish={(values) => { if (!selectedProductQualityId) return; startTransition(async () => { try { await createQualityProductStandardItem(selectedProductQualityId, values); message.success('质量标准明细已创建'); standardItemForm.resetFields(); setStandardItemDrawerOpen(false); await refreshStandardItems() } catch (error) { message.error(errorText(error, '创建标准明细失败')) } }) }}>
          <Row gutter={16}><Col span={12}><Form.Item name="display_order" label="显示顺序" rules={[{ required: true }]}><Input type="number" /></Form.Item></Col><Col span={12}><Form.Item name="category" label="要求分类"><Input /></Form.Item></Col></Row><Form.Item name="item_name" label="要求项目" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="requirement" label="要求内容" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item><Form.Item name="is_critical" label="关键要求" rules={[{ required: true }]}><Select options={[{ value: false, label: '否' }, { value: true, label: '是' }]} /></Form.Item><Form.Item name="remark" label="备注"><Input.TextArea rows={2} /></Form.Item><Button type="primary" htmlType="submit" loading={isPending}>创建明细</Button>
        </Form>
      </Drawer>

      <Modal title={`提交投诉回复 · ${respondingComplaint?.complaint_code ?? ''}`} open={Boolean(respondingComplaint)} onCancel={() => setRespondingComplaint(null)} footer={null} destroyOnHidden>
        <Form<ComplaintResponseInput> form={complaintResponseForm} layout="vertical" onFinish={(values) => { if (!respondingComplaint) return; startTransition(async () => { try { await respondQualityComplaint(respondingComplaint.id, values); message.success('投诉回复已提交'); complaintResponseForm.resetFields(); setRespondingComplaint(null); await refreshComplaints() } catch (error) { message.error(errorText(error, '提交投诉回复失败')) } }) }}>
          <Form.Item name="investigation_result" label="调查结论" rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item><Form.Item name="response_content" label="回复内容" rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item><Form.Item name="response_date" label="回复日期"><Input type="date" /></Form.Item><Button type="primary" htmlType="submit" loading={isPending}>提交回复</Button>
        </Form>
      </Modal>

      <Modal title={`完成退货/召回 · ${completingReturnRecall?.record_code ?? ''}`} open={Boolean(completingReturnRecall)} onCancel={() => setCompletingReturnRecall(null)} footer={null} destroyOnHidden>
        <Form<ReturnRecallCompleteInput> form={returnRecallCompleteForm} layout="vertical" onFinish={(values) => { if (!completingReturnRecall) return; startTransition(async () => { try { await completeQualityReturnRecall(completingReturnRecall.id, values); message.success('退货/召回记录已完成'); returnRecallCompleteForm.resetFields(); setCompletingReturnRecall(null); await refreshReturnRecalls() } catch (error) { message.error(errorText(error, '完成记录失败')) } }) }}>
          <Form.Item name="disposition" label="处置方式" rules={[{ required: true }]}><Input placeholder="例如：退货、销毁、返工" /></Form.Item><Form.Item name="completion_date" label="完成日期"><Input type="date" /></Form.Item><Button type="primary" htmlType="submit" loading={isPending}>确认完成</Button>
        </Form>
      </Modal>

      <Modal title={`完成产品质量评审 · ${completingProductQuality?.record_code ?? ''}`} open={Boolean(completingProductQuality)} onCancel={() => setCompletingProductQuality(null)} footer={null} destroyOnHidden>
        <Form<ProductQualityCompleteInput> form={productQualityCompleteForm} layout="vertical" onFinish={(values) => { if (!completingProductQuality) return; startTransition(async () => { try { await completeQualityProductRecord(completingProductQuality.id, values); message.success('产品质量评审已完成'); productQualityCompleteForm.resetFields(); setCompletingProductQuality(null); await refreshProductQuality() } catch (error) { message.error(errorText(error, '完成质量评审失败')) } }) }}>
          <Form.Item name="conclusion" label="评审结论" rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item><Form.Item name="reviewer" label="评审人" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="review_date" label="评审日期"><Input type="date" /></Form.Item><Button type="primary" htmlType="submit" loading={isPending}>完成评审</Button>
        </Form>
      </Modal>
    </Space>
  )
}
