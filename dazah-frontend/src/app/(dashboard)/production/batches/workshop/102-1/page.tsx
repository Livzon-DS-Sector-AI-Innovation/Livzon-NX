'use client'

import { useEffect, useState } from 'react'
import {
  Table, Button, Space, Input, Select, Modal, Form, InputNumber,
  Tag, Card, Row, Col, Statistic, Typography, DatePicker, App,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  PlusOutlined, SearchOutlined, EditOutlined, DeleteOutlined,
  ExperimentOutlined, PieChartOutlined, BarChartOutlined,
  ClockCircleOutlined, CheckCircleOutlined, SettingOutlined,
  DownloadOutlined,
} from '@ant-design/icons'
import {
  getFermentationRecords, createFermentationRecord,
  updateFermentationRecord, deleteFermentationRecord,
} from '@/actions/fermentation'
import type { FermentationRecord, FermentationCreate } from '@/types/fermentation'
import { FERMENTATION_STATUS_OPTIONS } from '@/types/fermentation'
import dayjs from 'dayjs'
import * as XLSX from 'xlsx'
import SyncSettingsButton from '@/components/production/SyncSettingsButton'
import BatchProfileButton from '@/components/production/BatchProfileButton'
import BatchEventsButton from '@/components/production/BatchEventsButton'

const { Text, Title } = Typography

function getProductionPeriodLabel(): string {
  const now = new Date()
  const day = now.getDate()
  const year = now.getFullYear()
  const month = now.getMonth()
  let start: Date, end: Date
  if (day >= 27) {
    start = new Date(year, month, 27)
    end = new Date(year, month + 1, 26)
  } else {
    start = new Date(year, month - 1, 27)
    end = new Date(year, month, 26)
  }
  const fmt = (d: Date) => `${d.getMonth() + 1}月${d.getDate()}日`
  const prodMonth = end.getMonth() + 1
  return `${prodMonth}月生产批次数据查看与管理（${fmt(start)}-${fmt(end)}）`
}

const getStatusColor = (status: string) => {
  const o = FERMENTATION_STATUS_OPTIONS.find(x => x.value === status)
  return o?.color || 'default'
}
const getStatusLabel = (status: string) => {
  const o = FERMENTATION_STATUS_OPTIONS.find(x => x.value === status)
  return o?.label || status
}

const PRODUCT_NAME = '多拉菌素'

export default function DoramectinPage() {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [records, setRecords] = useState<FermentationRecord[]>([])
  const [modalVisible, setModalVisible] = useState(false)
  const [editing, setEditing] = useState<FermentationRecord | null>(null)
  const [searchText, setSearchText] = useState('')
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [fermenterFilter, setFermenterFilter] = useState<string | undefined>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [editingStatusId, setEditingStatusId] = useState<string | null>(null)

  // 月度计划值（页面手动设置，localStorage 持久化）
  const [planTotalBatches, setPlanTotalBatches] = useState<number>(() => {
    if (typeof window === 'undefined') return 0
    return Number(localStorage.getItem('doramectin_plan_batches') || 0)
  })
  const [planYield, setPlanYield] = useState<number>(() => {
    if (typeof window === 'undefined') return 0
    return Number(localStorage.getItem('doramectin_plan_yield') || 0)
  })
  const [planModalVisible, setPlanModalVisible] = useState(false)
  const [planForm] = Form.useForm()


  const inProgress = records.filter(r => r.status === 'in_progress').length
  const completed = records.filter(r => r.status === 'completed').length
  const totalYield = records.filter(r => r.status === 'completed').reduce((s, r) => s + (r.tank_yield || 0), 0)
  const completionRate = planYield > 0 ? Number(((totalYield / planYield) * 100).toFixed(2)) : 0

  const load = async () => {
    setLoading(true)
    try {
      const res = await getFermentationRecords({ page: 1, page_size: 200, product_name: PRODUCT_NAME })
      if (res.code === 200) setRecords(res.data)
      else message.error('加载失败')
    } catch { message.error('加载失败') }
    finally { setLoading(false) }
  }

   
   
   
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps

  // TODO: 替换为102一车间实际发酵罐编号
  const FERMENTER_OPTIONS: string[] = []
  // 正在运行中的发酵罐（不能被新记录选用）
  const busyFementers = new Set(records.filter(r => r.status === 'in_progress').map(r => r.fermenter))
  const filtered = records.filter(r => {
    if (statusFilter && r.status !== statusFilter) return false
    if (fermenterFilter && r.fermenter !== fermenterFilter) return false
    if (searchText && !r.batch_no.toLowerCase().includes(searchText.toLowerCase())) return false
    return true
  })
  const paginated = filtered.slice((page - 1) * pageSize, page * pageSize)

  const handleAdd = () => { setEditing(null); form.resetFields(); setModalVisible(true) }
  const handleEdit = (r: FermentationRecord) => { setEditing(r); editForm.setFieldsValue({ ...r, entry_date: r.entry_date ? dayjs(r.entry_date) : null, discharge_date: r.discharge_date ? dayjs(r.discharge_date) : null }); setModalVisible(true) }

  const handleDelete = (id: string) => {
    modal.confirm({
      title: '确认删除', content: '确定删除此发酵记录？',
      onOk: async () => {
        const res = await deleteFermentationRecord(id)
        if (res.code === 200) { message.success('已删除'); load() }
        else message.error(res.message || '删除失败')
      },
    })
  }

  const handleSubmit = async () => {
    try {
      const values = editing ? await editForm.validateFields() : await form.validateFields()
      // 只取表单字段，避免 ...values 把 id/created_at 等多余字段带进去
      const data = {
        batch_no: values.batch_no,
        fermenter: values.fermenter,
        entry_date: values.entry_date?.format?.('YYYY-MM-DD') || values.entry_date,
        discharge_date: values.discharge_date?.format?.('YYYY-MM-DD') || values.discharge_date || null,
        tank_yield: values.tank_yield ?? null,
        status: values.status || 'in_progress',
        remarks: values.remarks || null,
        attachment: values.attachment || null,
      }
      if (editing) {
        const res = await updateFermentationRecord(editing.id, data)
        if (res.code === 200) { message.success('已更新'); setModalVisible(false); setPage(1); setSearchText(''); setStatusFilter(undefined); setFermenterFilter(undefined); load() }
        else message.error(res.message || '更新失败')
      } else {
        const res = await createFermentationRecord({ ...data, product_name: PRODUCT_NAME } as FermentationCreate)
        if (res.code === 200) { message.success('已创建'); setModalVisible(false); form.resetFields(); setPage(1); setSearchText(''); setStatusFilter(undefined); setFermenterFilter(undefined); load() }
        else message.error(res.message || '创建失败')
      }
    } catch { message.error('请检查表单填写是否完整') }
  }

  const handleStatusChange = async (id: string, status: string) => {
    const res = await updateFermentationRecord(id, { status })
    if (res.code === 200) {
      setRecords(prev => prev.map(r => r.id === id ? { ...r, status } : r))
      message.success('状态已更新')
    } else message.error(res.message || '更新失败')
  }

  const handlePlanSave = async () => {
    try {
      const values = await planForm.validateFields()
      setPlanTotalBatches(values.batches || 0)
      setPlanYield(values.yield || 0)
      localStorage.setItem('doramectin_plan_batches', String(values.batches || 0))
      localStorage.setItem('doramectin_plan_yield', String(values.yield || 0))
      setPlanModalVisible(false)
      message.success('月度计划已保存')
    } catch { /* validation */ }
  }

  const columns: ColumnsType<FermentationRecord> = [
    { title: '批号', dataIndex: 'batch_no', key: 'batch_no', width: 80, fixed: 'left' },
    { title: '发酵罐', dataIndex: 'fermenter', key: 'fermenter', width: 60 },
    { title: '进罐日期', dataIndex: 'entry_date', key: 'entry_date', width: 90, render: (d: string) => d || '-' },
    { title: '放罐日期', dataIndex: 'discharge_date', key: 'discharge_date', width: 90, render: (d: string) => d || '-' },
    { title: '罐产', dataIndex: 'tank_yield', key: 'tank_yield', width: 55, render: (v: number|null) => v ? v : '-' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: (_: unknown, record: FermentationRecord) => (
      editingStatusId === record.id ? (
        <Select
          size="small" autoFocus defaultOpen
          value={record.status}
          style={{ width: '100%' }}
          options={FERMENTATION_STATUS_OPTIONS.map(o => ({ value: o.value, label: o.label }))}
          onChange={(val) => { handleStatusChange(record.id, val); setEditingStatusId(null) }}
          onBlur={() => setEditingStatusId(null)}
        />
      ) : (
        <Tag color={getStatusColor(record.status)} style={{ cursor: 'pointer' }}
          onClick={() => setEditingStatusId(record.id)}>
          {getStatusLabel(record.status)}
        </Tag>
      )
    ) },
    { title: '备注', dataIndex: 'remarks', key: 'remarks', width: 100, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '附件', dataIndex: 'attachment', key: 'attachment', width: 60, render: (v: string|null) => v ? <a href={v} target="_blank">查看</a> : '-' },
    {
      title: '操作', key: 'action', width: 105, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <BatchEventsButton batchId={r.id} batchLabel={`${r.fermenter}-${r.batch_no}`} status={r.status} /> 
          <BatchProfileButton batchNo={r.batch_no} />
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>编辑</Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r.id)}>删除</Button>
        </Space>
      ),
    },
  ]

  return (
    <div className="p-6">
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <Title level={4} style={{ margin: 0 }}><ExperimentOutlined className="mr-2" />{PRODUCT_NAME} - 发酵数据</Title>
          <Button size="small" icon={<SettingOutlined />} onClick={() => { planForm.setFieldsValue({ batches: planTotalBatches, yield: planYield }); setPlanModalVisible(true) }}>月度计划</Button>
        </div>
        <Text type="secondary">{getProductionPeriodLabel()}</Text>
      </div>

      <Row gutter={16} className="mb-6">
        <Col span={4}><Card size="small"><Statistic title="计划总批次（批）" value={planTotalBatches} prefix={<BarChartOutlined />} styles={{ content: { color: '#1677ff' } }} /></Card></Col>
        <Col span={5}><Card size="small"><Statistic title="计划产量（kg）" value={planYield} prefix={<PieChartOutlined />} styles={{ content: { color: '#13c2c2' } }} /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="发酵中（批）" value={inProgress} prefix={<ClockCircleOutlined />} styles={{ content: { color: '#faad14' } }} /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="已完成（批）" value={completed} prefix={<CheckCircleOutlined />} styles={{ content: { color: '#52c41a' } }} /></Card></Col>
        <Col span={5}><Card size="small"><Statistic title="罐产总计（kg）" value={totalYield} prefix={<CheckCircleOutlined />} styles={{ content: { color: '#722ed1' } }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="完成率" value={completionRate} prefix={<BarChartOutlined />} styles={{ content: { color: completed > 0 ? '#52c41a' : '#999' } }} suffix="%" /></Card></Col>
      </Row>

      <Card
        title="发酵记录列表"
        extra={<Space><Button icon={<DownloadOutlined />} onClick={() => {
          const headers = ['批号', '发酵罐', '进罐日期', '放罐日期', '罐产', '状态', '备注']
          const rows = filtered.map(r => [r.batch_no, r.fermenter, r.entry_date || '', r.discharge_date || '', r.tank_yield ?? '', getStatusLabel(r.status), r.remarks || ''])
          const sheet = XLSX.utils.aoa_to_sheet([headers, ...rows])
          const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, sheet, '发酵记录')
          XLSX.writeFile(wb, `多拉菌素_发酵记录_${new Date().toISOString().slice(0, 10)}.xlsx`)
          message.success('导出成功')
        }}>导出Excel</Button><Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新建发酵记录</Button></Space>}
      >
        <Row gutter={16} className="mb-4">
          <Col span={6}><Input placeholder="搜索批号" prefix={<SearchOutlined />} value={searchText} onChange={e => { setSearchText(e.target.value); setPage(1) }} allowClear /></Col>
          <Col span={4}><Select placeholder="状态" allowClear value={statusFilter} onChange={v => { setStatusFilter(v); setPage(1) }} style={{ width: '100%' }} options={FERMENTATION_STATUS_OPTIONS.map(o => ({ value: o.value, label: o.label }))} /></Col>
          <Col span={4}><Select placeholder="发酵罐" allowClear value={fermenterFilter} onChange={v => { setFermenterFilter(v); setPage(1) }} style={{ width: '100%' }} options={FERMENTER_OPTIONS.map(f => ({ value: f, label: f }))} /></Col>
        </Row>
        <Table columns={columns} dataSource={paginated} rowKey="id" loading={loading} scroll={{ x: 720 }}
          pagination={{ current: page, pageSize, total: filtered.length, showSizeChanger: true, showQuickJumper: true, showTotal: (t: number) => `共 ${t} 条`, onChange: (p, ps) => { setPage(p); setPageSize(ps) } }}
        />
      </Card>

      <Modal title={editing ? '编辑发酵记录' : '新建发酵记录'} open={modalVisible} onOk={handleSubmit} onCancel={() => setModalVisible(false)} width={720} okText="确认" cancelText="取消">
        <Form form={editing ? editForm : form} layout="vertical">
          <Row gutter={16}>
            <Col span={8}><Form.Item name="batch_no" label="批号" rules={[{ required: true }]}><Input placeholder="批号" /></Form.Item></Col>
            <Col span={8}><Form.Item name="fermenter" label="发酵罐" rules={[{ required: true, message: '请选择发酵罐' }]}><Select placeholder="选择发酵罐" options={FERMENTER_OPTIONS.map(f => ({ value: f, label: f, disabled: !editing && busyFementers.has(f) }))} /></Form.Item></Col>
            <Col span={8}><Form.Item name="status" label="状态" initialValue="in_progress"><Select options={FERMENTATION_STATUS_OPTIONS.map(o => ({ value: o.value, label: o.label }))} /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="entry_date" label="进罐日期" rules={[{ required: true }]}><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={12}><Form.Item name="discharge_date" label="放罐日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}><Form.Item name="tank_yield" label="罐产"><InputNumber style={{ width: '100%' }} placeholder="罐产" /></Form.Item></Col>
            <Col span={16}><Form.Item name="attachment" label="附件"><Input placeholder="附件链接" /></Form.Item></Col>
          </Row>
          <Form.Item name="remarks" label="备注"><Input.TextArea rows={2} placeholder="备注" /></Form.Item>
        </Form>
      </Modal>

      <Modal title="月度生产计划" open={planModalVisible} onOk={handlePlanSave} onCancel={() => setPlanModalVisible(false)} width={360} okText="保存" cancelText="取消">
        <Form form={planForm} layout="vertical">
          <Form.Item name="batches" label="计划总批次（批）" rules={[{ required: true, message: '请输入计划批次' }]}>
            <InputNumber style={{ width: '100%' }} min={0} placeholder="本月计划生产批次总数" />
          </Form.Item>
          <Form.Item name="yield" label="计划产量（kg）" rules={[{ required: true, message: '请输入计划产量' }]}>
            <InputNumber style={{ width: '100%' }} min={0} placeholder="本月计划总产量" />
          </Form.Item>
        </Form>
      </Modal>

    </div>
  )
}
