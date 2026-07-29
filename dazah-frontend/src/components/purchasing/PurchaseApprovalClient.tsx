'use client'

import { useState, useSyncExternalStore } from 'react'
import dayjs from 'dayjs'
import {
  App,
  Button,
  Descriptions,
  Form,
  Input,
  Modal,
  Segmented,
  Space,
  Table,
  Tag,
} from 'antd'
import type { TableProps } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  EyeOutlined,
} from '@ant-design/icons'
import {
  approvePurchaseRequest,
  rejectPurchaseRequest,
} from '@/actions/purchasing'
import { fetchPurchaseRequests } from '@/lib/api/purchasing'
import type {
  PurchaseApprovalRole,
  PurchaseApprovalView,
  PurchaseRequestCategory,
  PurchaseRequestResponse,
} from '@/types/purchasing'
import {
  approvalRoleLabels,
  approvalViewLabels,
  approvalViews,
  formatMoney,
  purchaseStatusColors,
  purchaseStatusLabels,
} from './purchaseRequestConstants'

type PurchaseApprovalClientProps = {
  category: PurchaseRequestCategory
  categoryLabel: string
  approvalRole: PurchaseApprovalRole
  initialRequests: PurchaseRequestResponse[]
  initialTotal: number
}

type ApprovalFormValues = {
  approver_name: string
  opinion: string
}

const DEFAULT_PAGE_SIZE = 20
const subscribeToHydration = () => () => {}
const getClientHydrationSnapshot = () => true
const getServerHydrationSnapshot = () => false

export function shouldDisableApprovalActions(isHydrated: boolean) {
  return !isHydrated
}

export function PurchaseApprovalClient({
  category,
  categoryLabel,
  approvalRole,
  initialRequests,
  initialTotal,
}: PurchaseApprovalClientProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<ApprovalFormValues>()
  const [records, setRecords] = useState(initialRequests)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [approvalView, setApprovalView] = useState<PurchaseApprovalView>('pending')
  const [loading, setLoading] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [detailRecord, setDetailRecord] = useState<PurchaseRequestResponse | null>(null)
  const [reviewRecord, setReviewRecord] = useState<PurchaseRequestResponse | null>(null)
  const [reviewResult, setReviewResult] = useState<'approved' | 'rejected'>('approved')
  const isHydrated = useSyncExternalStore(
    subscribeToHydration,
    getClientHydrationSnapshot,
    getServerHydrationSnapshot
  )

  const roleLabel = approvalRoleLabels[approvalRole]
  const isPendingView = approvalView === 'pending'

  const loadRecords = async (
    nextPage = page,
    nextView: PurchaseApprovalView = approvalView
  ) => {
    setLoading(true)
    try {
      const response = await fetchPurchaseRequests({
        category,
        approval_role: approvalRole,
        approval_view: nextView,
        page: nextPage,
        page_size: DEFAULT_PAGE_SIZE,
      })
      setRecords(response.data ?? [])
      setTotal(Number(response.meta?.total ?? response.data?.length ?? 0))
      setPage(nextPage)
    } catch {
      message.error(`${approvalViewLabels[nextView]}列表加载失败`)
    } finally {
      setLoading(false)
    }
  }

  const handleViewChange = (value: string | number) => {
    const nextView = value as PurchaseApprovalView
    setApprovalView(nextView)
    void loadRecords(1, nextView)
  }

  const openReview = (
    record: PurchaseRequestResponse,
    result: 'approved' | 'rejected'
  ) => {
    setReviewRecord(record)
    setReviewResult(result)
    form.resetFields()
    form.setFieldsValue({
      approver_name: roleLabel,
      opinion: result === 'approved' ? '同意' : '',
    })
  }

  const handleReview = async () => {
    if (!reviewRecord) return
    const values = await form.validateFields()
    setReviewing(true)
    try {
      const payload = {
        approval_role: approvalRole,
        approver_name: values.approver_name,
        opinion: values.opinion ?? '',
        result: reviewResult,
      }
      const response =
        reviewResult === 'approved'
          ? await approvePurchaseRequest(reviewRecord.id, payload)
          : await rejectPurchaseRequest(reviewRecord.id, payload)

      if (response.code !== 200) {
        message.error(response.message || '审批失败')
        return
      }
      message.success(reviewResult === 'approved' ? '审批已通过' : '审批已驳回')
      setReviewRecord(null)
      await loadRecords(page)
    } catch {
      message.error('审批失败，请稍后重试')
    } finally {
      setReviewing(false)
    }
  }

  const columns: TableProps<PurchaseRequestResponse>['columns'] = [
    {
      title: '申请日期',
      dataIndex: 'request_date',
      key: 'request_date',
      width: 130,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD'),
    },
    {
      title: '申购部门',
      dataIndex: 'request_department',
      key: 'request_department',
      width: 180,
      ellipsis: true,
    },
    {
      title: '合计',
      dataIndex: 'total_amount',
      key: 'total_amount',
      width: 120,
      render: (value: string | number) => formatMoney(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 180,
      render: (status: PurchaseRequestResponse['status']) => (
        <Tag color={purchaseStatusColors[status]}>{purchaseStatusLabels[status]}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: isPendingView ? 260 : 110,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => setDetailRecord(record)}
          >
            查看
          </Button>
          {isPendingView && (
            <>
              <Button
                type="link"
                size="small"
                disabled={shouldDisableApprovalActions(isHydrated)}
                icon={<CheckCircleOutlined />}
                onClick={() => openReview(record, 'approved')}
              >
                通过
              </Button>
              <Button
                danger
                type="link"
                size="small"
                disabled={shouldDisableApprovalActions(isHydrated)}
                icon={<CloseCircleOutlined />}
                onClick={() => openReview(record, 'rejected')}
              >
                驳回
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ]

  const detailItemColumns: TableProps<NonNullable<PurchaseRequestResponse['items']>[number]>['columns'] = [
    { title: '序号', dataIndex: 'sequence', key: 'sequence', width: 70 },
    { title: '商品名称', dataIndex: 'product_name', key: 'product_name', width: 160 },
    { title: '规格', dataIndex: 'specification', key: 'specification', width: 120 },
    { title: '用途', dataIndex: 'purpose', key: 'purpose', width: 160 },
    { title: '材质', dataIndex: 'material', key: 'material', width: 100 },
    { title: '品牌', dataIndex: 'brand', key: 'brand', width: 100 },
    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 90 },
    { title: '单位', dataIndex: 'unit', key: 'unit', width: 80 },
    {
      title: '单价（元）',
      dataIndex: 'unit_price',
      key: 'unit_price',
      width: 110,
      render: (value) => formatMoney(value),
    },
    {
      title: '总额（元）',
      dataIndex: 'total_amount',
      key: 'total_amount',
      width: 110,
      render: (value) => formatMoney(value),
    },
    { title: '备注', dataIndex: 'remarks', key: 'remarks', width: 180 },
  ]

  const approvalColumns: TableProps<NonNullable<PurchaseRequestResponse['approvals']>[number]>['columns'] = [
    {
      title: '审批角色',
      dataIndex: 'approval_role',
      key: 'approval_role',
      width: 140,
      render: (role: PurchaseApprovalRole) => approvalRoleLabels[role],
    },
    {
      title: '结果',
      dataIndex: 'result',
      key: 'result',
      width: 100,
      render: (result: string) => (
        <Tag color={result === 'approved' ? 'success' : 'error'}>
          {result === 'approved' ? '通过' : '驳回'}
        </Tag>
      ),
    },
    { title: '审批人', dataIndex: 'approver_name', key: 'approver_name', width: 120 },
    { title: '意见', dataIndex: 'opinion', key: 'opinion' },
    {
      title: '审批时间',
      dataIndex: 'approval_time',
      key: 'approval_time',
      width: 170,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-[13px] text-[var(--color-stone)]">采购管理 / 采购审批</p>
          <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">
            {categoryLabel} · {roleLabel}
          </h1>
          <Space size="small" wrap>
            <Tag color="processing">{roleLabel}</Tag>
            <Tag>{approvalViewLabels[approvalView]}</Tag>
          </Space>
        </div>
        <Button loading={loading} onClick={() => loadRecords(page)}>
          刷新
        </Button>
      </div>

      <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <Segmented
            value={approvalView}
            onChange={handleViewChange}
            options={approvalViews.map((view) => ({
              label: approvalViewLabels[view],
              value: view,
            }))}
          />
          <span className="text-[13px] text-[var(--color-stone)]">
            共 {total} 条
          </span>
        </div>
        <Table
          columns={columns}
          dataSource={records}
          rowKey="id"
          loading={loading}
          scroll={{ x: 900 }}
          pagination={{
            current: page,
            pageSize: DEFAULT_PAGE_SIZE,
            total,
            showSizeChanger: false,
            showTotal: (value) => `共 ${value} 条`,
            onChange: (nextPage) => loadRecords(nextPage),
          }}
          locale={{ emptyText: `暂无${approvalViewLabels[approvalView]}采购申请` }}
        />
      </section>

      <Modal
        title="采购申请详情"
        open={Boolean(detailRecord)}
        footer={null}
        width={1100}
        onCancel={() => setDetailRecord(null)}
      >
        {detailRecord && (
          <div className="space-y-4">
            <Descriptions bordered size="small" column={3}>
              <Descriptions.Item label="分类">{categoryLabel}</Descriptions.Item>
              <Descriptions.Item label="申购部门">
                {detailRecord.request_department}
              </Descriptions.Item>
              <Descriptions.Item label="申请日期">
                {dayjs(detailRecord.request_date).format('YYYY-MM-DD')}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={purchaseStatusColors[detailRecord.status]}>
                  {purchaseStatusLabels[detailRecord.status]}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="合计">
                {formatMoney(detailRecord.total_amount)}
              </Descriptions.Item>
            </Descriptions>
            <Table
              columns={detailItemColumns}
              dataSource={detailRecord.items ?? []}
              rowKey="id"
              pagination={false}
              bordered
              scroll={{ x: 1350 }}
            />
            <Table
              columns={approvalColumns}
              dataSource={detailRecord.approvals ?? []}
              rowKey="id"
              pagination={false}
              locale={{ emptyText: '暂无审批记录' }}
            />
          </div>
        )}
      </Modal>

      <Modal
        title={`${reviewResult === 'approved' ? '通过' : '驳回'}采购申请`}
        open={Boolean(reviewRecord)}
        okText={reviewResult === 'approved' ? '确认通过' : '确认驳回'}
        cancelText="取消"
        confirmLoading={reviewing}
        okButtonProps={{ danger: reviewResult === 'rejected' }}
        onOk={handleReview}
        onCancel={() => setReviewRecord(null)}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="approver_name"
            label="审批人姓名"
            rules={[{ required: true, message: '请输入审批人姓名' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="opinion"
            label="审批意见"
            rules={
              reviewResult === 'rejected'
                ? [{ required: true, message: '请填写驳回原因' }]
                : undefined
            }
          >
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
