'use client'

import { useMemo, useState, useTransition } from 'react'
import { App, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { useRouter, useSearchParams } from 'next/navigation'
import { createFeeEntry, deleteFeeEntry, updateFeeEntry } from '@/actions/registration'
import type { FeeEntry, FeeEntryCreate, FeeEntryUpdate } from '@/types/registration'

interface FeeLedgerPageProps {
  entries: FeeEntry[]
  defaultYearFrom?: number
}

const FEE_TYPES = ['外检', '注册', '体系认证', '培训', '差旅费', '接待费', '维护费', '翻译服务费', '证书办理', '其他']
const PAYMENT_STATUSES = ['待支付', '已支付', '已开票']
const CURRENCIES = ['CNY', 'USD', 'EUR']

type FormMode = 'create' | 'edit'

export default function FeeLedgerPage({ entries, defaultYearFrom = 2023 }: FeeLedgerPageProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { message } = App.useApp()
  const [form] = Form.useForm<FeeEntryCreate>()
  const [keyword, setKeyword] = useState('')
  const [feeTypeFilter, setFeeTypeFilter] = useState<string>()
  const [paymentStatusFilter, setPaymentStatusFilter] = useState<string>()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editingEntry, setEditingEntry] = useState<FeeEntry | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [mode, setMode] = useState<FormMode>('create')
  const [pending, startTransition] = useTransition()
  const [yearFrom, setYearFrom] = useState(String(searchParams?.get('year_from') || defaultYearFrom))

  const filteredEntries = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    return entries.filter(entry => {
      if (feeTypeFilter && entry.fee_type !== feeTypeFilter) return false
      if (paymentStatusFilter && entry.payment_status !== paymentStatusFilter) return false
      if (!kw) return true
      return entry.agency_name?.toLowerCase().includes(kw) || entry.expense_content?.toLowerCase().includes(kw) || entry.handler?.toLowerCase().includes(kw) || entry.fee_type.toLowerCase().includes(kw)
    })
  }, [entries, keyword, feeTypeFilter, paymentStatusFilter])

  const selected = useMemo(() => filteredEntries.find(e => e.id === selectedId) || null, [filteredEntries, selectedId])

  const columns: ColumnsType<FeeEntry> = [
    { title: '付款方', dataIndex: 'agency_name', width: 150 },
    { title: '时间', dataIndex: 'payment_date', width: 100, align: 'center' as const },
    { title: '类别', dataIndex: 'fee_type', width: 80, align: 'center' as const },
    { title: '开支内容', dataIndex: 'expense_content', width: 260 },
    { title: '金额', dataIndex: 'amount', width: 110, align: 'right' as const, render: (v: string, r: FeeEntry) => <span style={{ fontWeight: 500, whiteSpace: 'nowrap' }}>{r.currency === 'CNY' ? '¥' : r.currency === 'USD' ? '$' : 'EUR '}{Number(v).toLocaleString()}</span> },
    { title: '状态', dataIndex: 'payment_status', width: 80, align: 'center' as const, render: (v: string) => <Tag color={v === '已支付' ? 'green' : v === '已开票' ? 'blue' : 'orange'}>{v}</Tag> },
    { title: '经办人', dataIndex: 'handler', width: 75, align: 'center' as const },
    { title: '联系人', dataIndex: 'contact', width: 80 },
    { title: '电话', dataIndex: 'phone', width: 130 },
    { title: '合同', dataIndex: 'contract_received', width: 55, align: 'center' as const, render: (v: boolean) => v ? '是' : '否' },
    { title: '发票', dataIndex: 'invoice_settled', width: 55, align: 'center' as const, render: (v: boolean) => v ? '是' : '否' },
    { title: '地址', dataIndex: 'address', width: 180 },
    { title: '备注', dataIndex: 'remarks', width: 100 },
  ]

  function openCreate() { setMode('create'); setEditingEntry(null); form.resetFields(); form.setFieldsValue({ currency: 'CNY', payment_status: '待支付' }); setModalOpen(true) }

  function openEdit() {
    if (!selected) { message.warning('请先选择一条记录'); return }
    setMode('edit'); setEditingEntry(selected)
    form.setFieldsValue({ fee_type: selected.fee_type, amount: Number(selected.amount), currency: selected.currency, payment_status: selected.payment_status, payment_date: selected.payment_date || undefined, agency_name: selected.agency_name || undefined, expense_content: selected.expense_content || undefined, handler: selected.handler || undefined, contract_received: selected.contract_received, invoice_settled: selected.invoice_settled, contact: selected.contact || undefined, phone: selected.phone || undefined, address: selected.address || undefined, invoice_number: selected.invoice_number || undefined, remarks: selected.remarks || undefined })
    setModalOpen(true)
  }

  function handleDelete() { if (!selected) { message.warning('请先选择一条记录'); return }; startTransition(async () => { try { await deleteFeeEntry(selected.id); message.success('已删除'); setSelectedId(null); router.refresh() } catch (e) { message.error(e instanceof Error ? e.message : '删除失败') } }) }

  async function handleSubmit(values: FeeEntryCreate) { startTransition(async () => { try { if (mode === 'edit' && editingEntry) { await updateFeeEntry(editingEntry.id, values as FeeEntryUpdate); message.success('已更新') } else { await createFeeEntry(values); message.success('已新增') }; setModalOpen(false); form.resetFields(); router.refresh() } catch (e) { message.error(e instanceof Error ? e.message : '保存失败') } }) }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={3} style={{ marginBottom: 0 }}>费用台账</Typography.Title>
      <Card size="small" extra={<Space><Button icon={<PlusOutlined />} type="primary" onClick={openCreate}>新增</Button><Button icon={<EditOutlined />} disabled={!selected} onClick={openEdit}>编辑</Button><Popconfirm title="确认删除？" onConfirm={handleDelete} disabled={!selected}><Button danger icon={<DeleteOutlined />} disabled={!selected}>删除</Button></Popconfirm></Space>}>
        <Space wrap size={12} style={{ marginBottom: 16 }}>
          <InputNumber value={Number(yearFrom) || 2023} min={2000} max={2099} style={{ width: 110 }}
            onChange={(v) => { const y = String(v || 2023); setYearFrom(y); router.push(`/registration/fees/ledger?year_from=${y}`) }} />
          <Select allowClear placeholder="费用类型" value={feeTypeFilter} onChange={setFeeTypeFilter} options={FEE_TYPES.map(t => ({ label: t, value: t }))} style={{ width: 140 }} />
          <Select allowClear placeholder="支付状态" value={paymentStatusFilter} onChange={setPaymentStatusFilter} options={PAYMENT_STATUSES.map(s => ({ label: s, value: s }))} style={{ width: 140 }} />
          <Input allowClear placeholder="搜索付款方/内容/经办人" value={keyword} onChange={e => setKeyword(e.target.value)} style={{ width: 260 }} />
        </Space>
        <Table rowKey="id" size="middle" columns={columns} dataSource={filteredEntries} pagination={{ pageSize: 20, showSizeChanger: true }}
          rowSelection={{ type: 'radio', selectedRowKeys: selectedId ? [selectedId] : [], onChange: keys => setSelectedId((keys[0] as string) || null) }} />
      </Card>
      <Modal destroyOnHidden confirmLoading={pending} open={modalOpen} width={700} title={mode === 'create' ? '新增费用' : '编辑费用'} okText="保存" cancelText="取消" onCancel={() => setModalOpen(false)} onOk={() => form.submit()}>
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="fee_type" label="费用类型" rules={[{ required: true }]} style={{ flex: 1, marginBottom: 0 }}><Select options={FEE_TYPES.map(t => ({ label: t, value: t }))} style={{ width: '100%' }} /></Form.Item>
            <Form.Item name="payment_status" label="支付状态" rules={[{ required: true }]} style={{ flex: 1, marginBottom: 0 }}><Select options={PAYMENT_STATUSES.map(s => ({ label: s, value: s }))} style={{ width: '100%' }} /></Form.Item>
          </div>
          <div style={{ display: 'flex', gap: 16, marginTop: 16 }}>
            <Form.Item name="amount" label="金额" rules={[{ required: true }]} style={{ flex: 1, marginBottom: 0 }}><InputNumber min={0} precision={2} style={{ width: '100%' }} /></Form.Item>
            <Form.Item name="currency" label="币种" style={{ flex: 1, marginBottom: 0 }}><Select options={CURRENCIES.map(c => ({ label: c, value: c }))} style={{ width: '100%' }} /></Form.Item>
          </div>
          <Form.Item name="payment_date" label="申请时间"><Input placeholder="2018.04.17" /></Form.Item>
          <Form.Item name="agency_name" label="付款方"><Input /></Form.Item>
          <Form.Item name="expense_content" label="开支内容"><Input.TextArea rows={2} /></Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="handler" label="经办人" style={{ flex: 1, marginBottom: 0 }}><Input /></Form.Item>
            <Form.Item name="contact" label="联系人" style={{ flex: 1, marginBottom: 0 }}><Input /></Form.Item>
          </div>
          <Form.Item name="phone" label="联系电话"><Input /></Form.Item>
          <Form.Item name="address" label="地址"><Input /></Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="contract_received" label="合同" valuePropName="checked" style={{ flex: 1, marginBottom: 0 }}><Switch /></Form.Item>
            <Form.Item name="invoice_settled" label="发票" valuePropName="checked" style={{ flex: 1, marginBottom: 0 }}><Switch /></Form.Item>
          </div>
          <Form.Item name="invoice_number" label="发票号"><Input /></Form.Item>
          <Form.Item name="remarks" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
