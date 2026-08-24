'use client'

import { useEffect, useState } from 'react'
import { App, Button, Form, Input, InputNumber, Modal, Popconfirm, Select, Spin, Table, DatePicker } from 'antd'
import { EditOutlined, DeleteOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { HR_DISPLAY_DATE_FORMAT } from '@/lib/dayjs-config'
import type { EsgTrainingRecord } from '@/types/hr'
import { fetchEsgRecordsByDept } from '@/lib/api/hr'
import { updateEsgTrainingRecord, deleteEsgTrainingRecord } from '@/actions/hr'

interface Props {
  department: string
  dateFrom: string
  dateTo: string
  periodLabel: string
  printRequest: number
}

// 与后端导出 Excel 一致的列（17 列，对齐 ESG 培训报表模板；IS_INSIDE 系统无数据，打印留空）
const PRINT_HEADERS = [
  '培训日期', '培训名称', '培训方式', '口径', '培训类型', '姓名',
  '员工账号', '身份所属地', '部门', '层级', '性别', '年龄',
  '培训时长(h)', '是否通过本次培训成功实现晋升', '备注', '单位名称', '单位编码',
]
const PRINT_FIELDS: (keyof EsgTrainingRecord | null)[] = [
  'training_date', 'training_name', 'training_method', 'caliber',
  'training_type', 'employee_name', 'employee_account', 'location_address',
  'department', 'employee_level', 'gender', 'age', 'duration',
  null, // IS_INSIDE（是否通过本次培训成功实现晋升）系统无数据，打印留空
  'remarks', 'apply_company', 'apply_company_no',
]
// 模板培训类型下拉 9 项（与后端导出 _ESG_TRAINING_TYPES 一致）
const TRAINING_TYPE_OPTIONS = [
  'EHS类', '质量类', '商业道德反贪腐', '负责任营销', '数据安全、隐私保护',
  '领导力', '管理类', '多元化', '女性领导力发展计划',
]

export default function EsgTrainingReportClient({ department, dateFrom, dateTo, periodLabel, printRequest }: Props) {
  const { message } = App.useApp()
  const [records, setRecords] = useState<EsgTrainingRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [editingRecord, setEditingRecord] = useState<EsgTrainingRecord | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  const loadData = async () => {
    setLoading(true)
    try {
      const res = await fetchEsgRecordsByDept(department, 1, 500)
      setRecords(res.data || [])
    } catch (e) {
      message.error('加载失败: ' + ((e instanceof Error ? e.message : '') || '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [department])

  // 客户端按筛选范围过滤（与导出一致）
  const filteredRecords = (dateFrom && dateTo)
    ? records.filter((r) => {
        if (!r.training_date) return false
        return r.training_date >= dateFrom && r.training_date <= dateTo
      })
    : records

  // 按导出内容打印：新窗口渲染与导出 Excel 一致的表格后调起打印
  const doPrint = () => {
    if (filteredRecords.length === 0) {
      message.warning('当前筛选范围内没有数据')
      return
    }
    const title = `${department} ESG培训报表${periodLabel ? `（${periodLabel}）` : ''}`
    const esc = (v: unknown) =>
      String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const headerHtml = PRINT_HEADERS.map((h) => `<th>${esc(h)}</th>`).join('')
    const bodyHtml = filteredRecords
      .map((r) => `<tr>${PRINT_FIELDS.map((f) => `<td>${esc(f ? r[f] ?? '' : '')}</td>`).join('')}</tr>`)
      .join('')
    const w = window.open('', '_blank')
    if (!w) {
      message.error('浏览器拦截了弹出窗口，请允许后重试')
      return
    }
    w.document.write(`<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>${esc(title)}</title>
<style>
  @page { size: A4 landscape; margin: 10mm; }
  body { font-family: "Microsoft YaHei", sans-serif; font-size: 11px; }
  h2 { text-align: center; font-size: 16px; margin: 0 0 10px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { border: 1px solid #000; padding: 4px 5px; text-align: center; word-break: break-all; }
  th { background: #f0f0f0; font-weight: bold; }
</style></head><body>
<h2>${esc(title)}</h2>
<table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>
</body></html>`)
    w.document.close()
    w.focus()
    w.print()
  }

  useEffect(() => {
    if (printRequest > 0) queueMicrotask(doPrint)
  }, [printRequest])

  const handleEdit = (record: EsgTrainingRecord) => {
    setEditingRecord(record)
    form.setFieldsValue({ ...record, training_date: record.training_date ? dayjs(record.training_date) : null })
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const payload = {
        ...editingRecord,
        ...values,
        training_date: values.training_date ? values.training_date.format('YYYY-MM-DD') : undefined,
      }
      await updateEsgTrainingRecord(editingRecord!.id, payload)
      message.success('更新成功')
      setEditingRecord(null)
      loadData()
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteEsgTrainingRecord(id)
      message.success('删除成功')
      loadData()
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '删除失败')
    }
  }

  const columns = [
    { title: '培训日期', dataIndex: 'training_date', width: 110, render: (v: string) => v ? dayjs(v).format(HR_DISPLAY_DATE_FORMAT) : '-' },
    { title: '培训名称', dataIndex: 'training_name', width: 220, ellipsis: true },
    { title: '培训方式', dataIndex: 'training_method', width: 90 },
    { title: '口径', dataIndex: 'caliber', width: 80 },
    { title: '培训类型', dataIndex: 'training_type', width: 90 },
    { title: '姓名', dataIndex: 'employee_name', width: 80 },
    { title: '员工账号', dataIndex: 'employee_account', width: 100 },
    { title: '身份所属地', dataIndex: 'location_address', width: 100 },
    { title: '部门', dataIndex: 'department', width: 120 },
    { title: '层级', dataIndex: 'employee_level', width: 80 },
    { title: '性别', dataIndex: 'gender', width: 60 },
    { title: '年龄', dataIndex: 'age', width: 60 },
    { title: '培训时长(h)', dataIndex: 'duration', width: 80 },
    { title: '是否通过本次培训成功实现晋升', dataIndex: 'is_inside', width: 140, render: () => '-' },
    { title: '备注', dataIndex: 'remarks', width: 150, ellipsis: true },
    { title: '单位名称', dataIndex: 'apply_company', width: 120, ellipsis: true },
    { title: '单位编码', dataIndex: 'apply_company_no', width: 100 },
    {
      title: '操作', width: 140, fixed: 'right' as const,
      render: (_: any, record: EsgTrainingRecord) => (
        <div className="no-print flex gap-2">
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          <Popconfirm title="删除?" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </div>
      ),
    },
  ]

  if (loading) return <div className="flex justify-center py-20"><Spin size="large" /></div>

  return (
    <>
      <Table rowKey="id" dataSource={filteredRecords} columns={columns} scroll={{ x: 2000 }} size="small" pagination={{ pageSize: 50, showSizeChanger: false }} />

      <Modal title="编辑ESG培训记录" open={!!editingRecord} onCancel={() => setEditingRecord(null)} onOk={handleSave} confirmLoading={saving} width={640}>
        <Form form={form} layout="vertical">
          <Form.Item name="training_name" label="培训名称" rules={[{ required: true }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="training_date" label="培训日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="training_method" label="培训方式">
            <Select options={[
              { value: '线上', label: '线上' }, { value: '线下', label: '线下' },
            ]} />
          </Form.Item>
          <Form.Item name="caliber" label="口径">
            <Select options={[
              { value: '公司组织', label: '公司组织' }, { value: '部门组织', label: '部门组织' },
            ]} />
          </Form.Item>
          <Form.Item name="training_type" label="培训类型">
            <Select options={TRAINING_TYPE_OPTIONS.map((v) => ({ value: v, label: v }))} />
          </Form.Item>
          <Form.Item name="employee_name" label="姓名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="employee_account" label="员工账号"><Input /></Form.Item>
          <Form.Item name="location_address" label="身份所属地"><Input /></Form.Item>
          <Form.Item name="department" label="部门"><Input /></Form.Item>
          <Form.Item name="employee_level" label="层级"><Input /></Form.Item>
          <Form.Item name="gender" label="性别">
            <Select options={[{ value: '男', label: '男' }, { value: '女', label: '女' }]} />
          </Form.Item>
          <Form.Item name="age" label="年龄"><InputNumber min={0} max={200} /></Form.Item>
          <Form.Item name="duration" label="培训时长"><InputNumber min={0} step={0.5} /></Form.Item>
          <Form.Item name="remarks" label="备注"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="apply_company" label="单位名称"><Input /></Form.Item>
          <Form.Item name="apply_company_no" label="单位编码"><Input /></Form.Item>
        </Form>
      </Modal>
    </>
  )
}
