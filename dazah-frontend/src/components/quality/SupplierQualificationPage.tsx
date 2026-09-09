'use client'

import { qualityTokens } from './themeTokens'
import { useCallback, useEffect, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import { App, Avatar, Button, Card, DatePicker, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { pullSupplierQualifications, createSupplierQualification, updateSupplierQualification, deleteSupplierQualification } from '@/actions/quality'
import { fetchSupplierQualifications, type SupplierExpiryBucket } from '@/lib/api/client/quality'
import FeishuPersonSelect, { type FeishuPersonValue } from '@/components/shared/FeishuPersonSelect'
import type { SupplierQualificationItem } from '@/types/quality'

const AV = ['#5645d4', '#7b3ff2', '#dd5b00', '#0075de', '#1aae39', '#2a9d99']

function avColor(name: string) {
  let h = 0
  for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h)
  return AV[Math.abs(h) % AV.length]
}

const MATERIAL_TYPE_OPTIONS = [
  { label: '固体', value: '固体' },
  { label: '液体', value: '液体' },
  { label: '包材', value: '包材' },
]

const QUALIFICATION_NAME_OPTIONS = [
  { label: '营业执照', value: '营业执照' },
  { label: '生产许可证', value: '生产许可证' },
  { label: '安全生产许可证', value: '安全生产许可证' },
  { label: '危险化学品登记证', value: '危险化学品登记证' },
  { label: '生产备案证明', value: '生产备案证明' },
  { label: '经营许可证', value: '经营许可证' },
  { label: '经销商营业执照', value: '经销商营业执照' },
  { label: 'ISO（9001）', value: 'ISO（9001）' },
  { label: '质量证书ISO（9001）', value: '质量证书ISO（9001）' },
  { label: 'ISO（14001）', value: 'ISO（14001）' },
  { label: 'ISO（22000）', value: 'ISO（22000）' },
  { label: 'ISO（45001）', value: 'ISO（45001）' },
  { label: 'COA可靠性确认', value: 'COA可靠性确认' },
  { label: '质量协议', value: '质量协议' },
  { label: '调查问卷', value: '调查问卷' },
  { label: '三方检测报告', value: '三方检测报告' },
  { label: 'KOSHER证书', value: 'KOSHER证书' },
  { label: 'HALAL', value: 'HALAL' },
  { label: 'IP证书', value: 'IP证书' },
  { label: 'HACCP证书', value: 'HACCP证书' },
  { label: '注册证', value: '注册证' },
  { label: '其他证书', value: '其他证书' },
]

// 到期分桶选项（与后端统计/仪表盘同一口径）
const EXPIRY_BUCKET_OPTIONS: { label: string; value: SupplierExpiryBucket }[] = [
  { label: '已延期', value: 'expired' },
  { label: '30天内到期', value: 'due_30' },
  { label: '60天内到期', value: 'due_60' },
  { label: '90天内到期', value: 'due_90' },
]

interface FormValues {
  supplier_name: string
  material_name: string
  material_type: string
  qualification_name: string
  qualification_file: string
  is_completed: boolean
  deadline: Dayjs | null
  remark: string
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD') : value
}

function toDateValue(value: string | null | undefined): Dayjs | null {
  if (!value) return null
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed : null
}

interface SupplierQualificationPageProps {
  initialItems?: SupplierQualificationItem[]
}

export default function SupplierQualificationPage({ initialItems = [] }: SupplierQualificationPageProps) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [materialTypeFilter, setMaterialTypeFilter] = useState<string | undefined>()
  const [qualificationNameFilter, setQualificationNameFilter] = useState<string | undefined>()
  const [isCompletedFilter, setIsCompletedFilter] = useState<boolean | undefined>()
  const [expiryBucketFilter, setExpiryBucketFilter] = useState<SupplierExpiryBucket | undefined>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRecord, setEditingRecord] = useState<SupplierQualificationItem | null>(null)
  const [form] = Form.useForm<FormValues>()
  // 负责人：多选飞书人员，数据源与验证模块一致（人事管理-飞书联系人）
  const [responsiblePersons, setResponsiblePersons] = useState<FeishuPersonValue[]>([])

  // 任意筛选条件变化都回到第一页，避免停在越界页码
  const resetPage = () => setPage(1)

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-supplier', 'list', {
      keyword: keyword.trim(),
      materialTypeFilter: materialTypeFilter ?? '',
      qualificationNameFilter: qualificationNameFilter ?? '',
      isCompletedFilter: isCompletedFilter === undefined ? '' : String(isCompletedFilter),
      expiryBucketFilter: expiryBucketFilter ?? '',
      page,
      pageSize,
    }],
    queryFn: () =>
      fetchSupplierQualifications({
        keyword: keyword.trim() || undefined,
        page,
        page_size: pageSize,
        material_type: materialTypeFilter || undefined,
        qualification_name: qualificationNameFilter || undefined,
        is_completed: isCompletedFilter,
        expiry_bucket: expiryBucketFilter,
      }),
    placeholderData: keepPreviousData,
    initialData: initialItems.length && !keyword && page === 1 && pageSize === 20
      ? { items: initialItems, total: initialItems.length }
      : undefined,
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载供应商资质失败'))
    }
  }, [error, message])

  const items = data?.items ?? []

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result = await pullSupplierQualifications()
      message.success(`从飞书拉取完成：成功 ${result?.synced ?? 0} 条`)
      queryClient.invalidateQueries({ queryKey: ['quality-supplier', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '从飞书拉取失败'))
    } finally {
      setPulling(false)
    }
  }, [queryClient, message])

  const openCreate = useCallback(() => {
    setEditingRecord(null)
    form.resetFields()
    form.setFieldsValue({ is_completed: false })
    setResponsiblePersons([])
    setModalVisible(true)
  }, [form])

  const openEdit = useCallback((record: SupplierQualificationItem) => {
    setEditingRecord(record)
    form.setFieldsValue({
      supplier_name: record.supplier_name ?? '',
      material_name: record.material_name ?? '',
      material_type: record.material_type ?? '',
      qualification_name: record.qualification_name ?? '',
      qualification_file: record.qualification_file ?? '',
      is_completed: record.is_completed ?? false,
      deadline: toDateValue(record.deadline),
      remark: record.remark ?? '',
    })
    // 编辑回显：镜像里的负责人 id 对目标 Base 有效（resolved）
    const users = record.responsible_users ?? []
    setResponsiblePersons(
      users
        .filter((user) => user.id)
        .map((user) => ({
          id: user.id,
          name: user.name,
          email: user.email ?? undefined,
          resolved: true,
        })),
    )
    setModalVisible(true)
  }, [form])

  const closeModal = useCallback(() => {
    setModalVisible(false)
    setEditingRecord(null)
    form.resetFields()
    setResponsiblePersons([])
  }, [form])

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields()
    try {
      setSaving(true)
      const payload = {
        supplier_name: values.supplier_name?.trim() || '',
        material_name: values.material_name?.trim() || null,
        material_type: values.material_type?.trim() || null,
        qualification_name: values.qualification_name?.trim() || '',
        qualification_file: values.qualification_file?.trim() || null,
        is_completed: values.is_completed ?? false,
        deadline: values.deadline ? values.deadline.format('YYYY-MM-DD') : null,
                responsible_users: responsiblePersons.map((person) => ({
          id: person.id,
          name: person.name,
          ...(person.email ? { email: person.email } : {}),
          ...(person.mobile ? { mobile: person.mobile } : {}),
        })),
        remark: values.remark?.trim() || null,
      }
      if (editingRecord) {
        await updateSupplierQualification(editingRecord.record_id, payload)
        message.success('供应商资质记录已更新')
      } else {
        await createSupplierQualification(payload)
        message.success('供应商资质记录已创建')
      }
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['quality-supplier', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存供应商资质记录失败'))
    } finally {
      setSaving(false)
    }
  }, [closeModal, editingRecord, form, queryClient, message, responsiblePersons])

  const handleDelete = useCallback(async (recordId: string) => {
    try {
      await deleteSupplierQualification(recordId)
      message.success('供应商资质记录已删除')
      queryClient.invalidateQueries({ queryKey: ['quality-supplier', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除供应商资质记录失败'))
    }
  }, [queryClient, message])

  const columns: ColumnsType<SupplierQualificationItem> = [
    {
      title: '供应商名称',
      dataIndex: 'supplier_name',
      key: 'supplier_name',
      width: 180,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '物料名称',
      dataIndex: 'material_name',
      key: 'material_name',
      width: 140,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '物料类型',
      dataIndex: 'material_type',
      key: 'material_type',
      width: 90,
      render: (value: string | null) => {
        const colorMap: Record<string, string> = { '固体': 'orange', '液体': 'blue', '包材': 'purple' }
        return value ? <span style={{ color: colorMap[value] ?? 'default' }}>{value}</span> : '-'
      },
    },
    {
      title: '资质名称',
      dataIndex: 'qualification_name',
      key: 'qualification_name',
      width: 160,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '资质文件',
      dataIndex: 'qualification_file',
      key: 'qualification_file',
      width: 150,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '是否完成',
      dataIndex: 'is_completed',
      key: 'is_completed',
      width: 90,
      render: (value: boolean) => (
        <span style={{ color: value ? qualityTokens.success : qualityTokens.orangeText }}>{value ? '已完成' : '未完成'}</span>
      ),
    },
    {
      title: '截止日期',
      dataIndex: 'deadline',
      key: 'deadline',
      width: 120,
      render: (value: string | null) => {
        if (!value) return '-'
        const d = dayjs(value)
        if (!d.isValid()) return '-'
        const isExpired = d.isBefore(dayjs(), 'day') && !d.isSame(dayjs(), 'day')
        return <span style={{ color: isExpired ? '#e03131' : undefined }}>{d.format('YYYY-MM-DD')}</span>
      },
    },
    {
      title: '到期状态',
      dataIndex: 'expiry_status',
      key: 'expiry_status',
      width: 140,
      render: (value: string | null) => {
        if (!value) return '-'
        const isOverdue = value.includes('已延期')
        return <span style={{ color: isOverdue ? '#e03131' : '#0075de' }}>{value}</span>
      },
    },
    {
      title: '负责人',
      dataIndex: 'responsible_person',
      key: 'responsible_person',
      width: 160,
      render: (_: unknown, record: SupplierQualificationItem) => {
        const users = record.responsible_users ?? []
        if (!users.length) {
          return record.responsible_person || '-'
        }
        return (
          <Space size={4} wrap>
            {users.map((user) => (
              <span key={user.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <Avatar
                  size={22}
                  src={user.avatar_url || undefined}
                  style={{ backgroundColor: avColor(user.name || '?'), flexShrink: 0, fontSize: 11, fontWeight: 700 }}
                >
                  {!user.avatar_url ? (user.name || '?').charAt(0) : undefined}
                </Avatar>
                {user.name}
              </span>
            ))}
          </Space>
        )
      },
    },
    {
      title: '群组',
      dataIndex: 'groups',
      key: 'groups',
      width: 160,
      render: (value: SupplierQualificationItem['groups']) => {
        if (!value?.length) return '-'
        return (
          <Space size={4} wrap>
            {value.map((group) => (
              <span key={group.id || group.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <Avatar
                  size={22}
                  src={group.avatar_url || undefined}
                  icon={!group.avatar_url ? undefined : undefined}
                  style={{ backgroundColor: group.avatar_url ? 'transparent' : avColor(group.name || '?'), flexShrink: 0, fontSize: 11, fontWeight: 700 }}
                >
                  {!group.avatar_url ? (group.name || '?').charAt(0) : undefined}
                </Avatar>
                {group.name}
              </span>
            ))}
          </Space>
        )
      },
    },
    {
      title: '备注',
      dataIndex: 'remark',
      key: 'remark',
      width: 150,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button type="link" onClick={() => openEdit(record)}>修改</Button>
          <Popconfirm
            title="确认删除这条供应商资质记录？"
            okText="删除"
            cancelText="取消"
            onConfirm={() => void handleDelete(record.record_id)}
          >
            <Button type="link" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 供应商管理 / 供应商资质</p>
        <Typography.Title level={3} style={{ margin: 0 }}>供应商资质</Typography.Title>
      </div>

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
          <Space wrap>
            <Input.Search
              placeholder="搜索供应商名称、物料、资质..."
              allowClear
              style={{ width: 300 }}
              value={searchInput}
              onChange={(e) => {
                setSearchInput(e.target.value)
                if (e.target.value === '') {
                  setKeyword('')
                  resetPage()
                }
              }}
              onSearch={(value) => {
                setKeyword(value)
                resetPage()
              }}
            />
            <Select
              placeholder="物料类型"
              allowClear
              style={{ width: 120 }}
              value={materialTypeFilter}
              onChange={(val) => {
                setMaterialTypeFilter(val)
                resetPage()
              }}
              options={MATERIAL_TYPE_OPTIONS}
            />
            <Select
              placeholder="资质名称"
              allowClear
              style={{ width: 180 }}
              value={qualificationNameFilter}
              onChange={(val) => {
                setQualificationNameFilter(val)
                resetPage()
              }}
              options={QUALIFICATION_NAME_OPTIONS}
            />
            <Select
              placeholder="完成状态"
              allowClear
              style={{ width: 120 }}
              value={isCompletedFilter}
              onChange={(val) => {
                setIsCompletedFilter(val)
                resetPage()
              }}
              options={[
                { label: '已完成', value: true },
                { label: '未完成', value: false },
              ]}
            />
            <Select
              placeholder="到期状态"
              allowClear
              style={{ width: 140 }}
              value={expiryBucketFilter}
              onChange={(val) => {
                setExpiryBucketFilter(val)
                resetPage()
              }}
              options={EXPIRY_BUCKET_OPTIONS}
            />
          </Space>
          <Space>
            <Button type="primary" onClick={openCreate}>新增</Button>
            <Button loading={pulling} onClick={() => void handlePullFromFeishu()}>从飞书拉取</Button>
          </Space>
        </div>

        <Table<SupplierQualificationItem>
          rowKey="record_id"
          loading={loading}
          columns={columns}
          dataSource={items}
          scroll={{ x: 1400 }}
          pagination={{
            current: page,
            pageSize,
            total: data?.total ?? 0,
            showSizeChanger: true,
            pageSizeOptions: [10, 20, 50, 100],
            showTotal: (total) => `共 ${total} 条`,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage)
              setPageSize(nextPageSize)
            },
          }}
        />
      </Card>

      <Modal
        title={editingRecord ? '修改供应商资质记录' : '新增供应商资质记录'}
        open={modalVisible}
        onOk={() => void handleSubmit()}
        onCancel={closeModal}
        confirmLoading={saving}
        destroyOnHidden
        width={800}
      >
        <Form form={form} layout="vertical">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16 }}>
            <Form.Item
              name="supplier_name"
              label="供应商名称"
              rules={[{ required: true, message: '请输入供应商名称' }]}
            >
              <Input placeholder="请输入供应商名称" />
            </Form.Item>
            <Form.Item name="material_name" label="物料名称">
              <Input placeholder="请输入物料名称" />
            </Form.Item>
            <Form.Item name="material_type" label="物料类型">
              <Select placeholder="请选择物料类型" allowClear options={MATERIAL_TYPE_OPTIONS} />
            </Form.Item>
            <Form.Item
              name="qualification_name"
              label="资质名称"
              rules={[{ required: true, message: '请选择资质名称' }]}
            >
              <Select placeholder="请选择资质名称" allowClear options={QUALIFICATION_NAME_OPTIONS} />
            </Form.Item>
            <Form.Item name="qualification_file" label="资质文件">
              <Input placeholder="请输入资质文件" />
            </Form.Item>
            <Form.Item name="deadline" label="截止日期">
              <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
            </Form.Item>
            <Form.Item name="is_completed" label="是否完成" valuePropName="checked">
              <Switch />
            </Form.Item>
          </div>

          <Form.Item label="负责人" extra="与验证模块一致：人事管理-飞书联系人选人，支持中文/全拼/首字母搜索，可多选">
            <FeishuPersonSelect
              multiple
              placeholder="输入姓名或拼音搜索人员"
              value={responsiblePersons}
              onChange={(value) => {
                const next = Array.isArray(value) ? value : value ? [value] : []
                setResponsiblePersons(next.map((p) => ({ id: p.id, name: p.name, resolved: p.resolved })))
              }}
            />
          </Form.Item>

          <Form.Item name="remark" label="备注">
            <Input.TextArea placeholder="请输入备注" rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
