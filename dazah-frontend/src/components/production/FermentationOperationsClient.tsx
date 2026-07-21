'use client'

import { useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import { App, Button, Card, DatePicker, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'

import { createFermentation, createSeedCulture, deleteFermentation, deleteSeedCulture, getFermentations, getSeedCultures, updateFermentation, updateSeedCulture } from '@/actions/production'
import type { components } from '@/types/generated/schema'

type Fermentation = components['schemas']['FermentationResponse']
type FermentationCreate = components['schemas']['FermentationCreate']
type FermentationUpdate = components['schemas']['FermentationUpdate']
type SeedCulture = components['schemas']['SeedCultureResponse']
type SeedCultureCreate = components['schemas']['SeedCultureCreate']
type SeedCultureUpdate = components['schemas']['SeedCultureUpdate']

interface Props { initialFermentations: Fermentation[]; initialSeedCultures: SeedCulture[] }
interface FormValues {
  batch_no: string; product_name: string; fermenter?: string; record_date?: Dayjs
  tank_yield?: number; status: string; remarks?: string
  cycle_1?: number; cycle_2?: number; cycle_3?: number; cycle_4?: number; cycle_5?: number; cycle_6?: number
  glucose_batch?: string; corn_starch_batch?: string; corn_syrup_batch?: string
  ammonium_sulfate_batch?: string; soybean_meal_batch?: string; calcium_carbonate_batch?: string
}

const statusColor: Record<string, string> = { in_progress: 'processing', completed: 'success', abnormal: 'error' }

export function FermentationOperationsClient({ initialFermentations, initialSeedCultures }: Props) {
  const { message } = App.useApp()
  const [fermentations, setFermentations] = useState(initialFermentations)
  const [seedCultures, setSeedCultures] = useState(initialSeedCultures)
  const [kind, setKind] = useState<'fermentation' | 'seed' | null>(null)
  const [editing, setEditing] = useState<Fermentation | SeedCulture | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<FormValues>()

  const reload = async () => {
    const [fermentationResult, seedResult] = await Promise.all([getFermentations(), getSeedCultures()])
    if (fermentationResult.code === 200) setFermentations(fermentationResult.data || [])
    if (seedResult.code === 200) setSeedCultures(seedResult.data || [])
  }

  const open = (nextKind: 'fermentation' | 'seed') => {
    setEditing(null)
    setKind(nextKind)
    form.resetFields()
    form.setFieldsValue({ product_name: 'L-苯丙氨酸', status: 'in_progress', record_date: dayjs() })
  }

  const openEdit = (nextKind: 'fermentation' | 'seed', row: Fermentation | SeedCulture) => {
    setKind(nextKind)
    setEditing(row)
    const details = nextKind === 'fermentation' ? (row as Fermentation).cycle_data : (row as SeedCulture).materials
    form.setFieldsValue({
      batch_no: row.batch_no, product_name: row.product_name,
      fermenter: nextKind === 'fermentation' ? (row as Fermentation).fermenter : undefined,
      record_date: dayjs(nextKind === 'fermentation' ? (row as Fermentation).entry_date : (row as SeedCulture).prepare_date),
      tank_yield: row.tank_yield || undefined, status: row.status, remarks: row.remarks || undefined,
      ...details,
    })
  }

  const submit = async () => {
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      const cycleData = Object.fromEntries([1, 2, 3, 4, 5, 6].map(index => [`cycle_${index}`, values[`cycle_${index}` as keyof FormValues]]).filter(([, value]) => value !== undefined))
      const materials = Object.fromEntries(['glucose_batch', 'corn_starch_batch', 'corn_syrup_batch', 'ammonium_sulfate_batch', 'soybean_meal_batch', 'calcium_carbonate_batch'].map(key => [key, values[key as keyof FormValues]]).filter(([, value]) => value))
      const response = kind === 'fermentation'
        ? editing ? await updateFermentation(editing.id, {
            batch_no: values.batch_no, product_name: values.product_name,
            fermenter: values.fermenter || '', entry_date: values.record_date!.format('YYYY-MM-DD'),
            cycle_data: cycleData, tank_yield: values.tank_yield, status: values.status,
            remarks: values.remarks,
          } satisfies FermentationUpdate) : await createFermentation({
            batch_no: values.batch_no, product_name: values.product_name,
            fermenter: values.fermenter || '', entry_date: values.record_date!.format('YYYY-MM-DD'),
            cycle_data: cycleData, tank_yield: values.tank_yield, status: values.status,
            remarks: values.remarks, source: 'manual',
          } satisfies FermentationCreate)
        : editing ? await updateSeedCulture(editing.id, {
            batch_no: values.batch_no, product_name: values.product_name,
            prepare_date: values.record_date?.format('YYYY-MM-DD'), materials,
            tank_yield: values.tank_yield, status: values.status, remarks: values.remarks,
          } satisfies SeedCultureUpdate) : await createSeedCulture({
            batch_no: values.batch_no, product_name: values.product_name,
            prepare_date: values.record_date?.format('YYYY-MM-DD'), materials,
            quality_data: {}, operation_data: {}, tank_yield: values.tank_yield,
            status: values.status, remarks: values.remarks, source: 'manual',
          } satisfies SeedCultureCreate)
      if (response.code !== 200) throw new Error(response.message)
      message.success('记录已保存')
      setKind(null)
      setEditing(null)
      form.resetFields()
      await reload()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败')
    } finally { setSubmitting(false) }
  }

  const remove = async (recordKind: 'fermentation' | 'seed', id: string) => {
    const response = recordKind === 'fermentation' ? await deleteFermentation(id) : await deleteSeedCulture(id)
    if (response.code === 200) { message.success('已删除'); await reload() } else message.error(response.message)
  }

  const fermentationColumns: ColumnsType<Fermentation> = [
    { title: '批号', dataIndex: 'batch_no' }, { title: '产品', dataIndex: 'product_name' },
    { title: '发酵罐', dataIndex: 'fermenter' }, { title: '进罐', dataIndex: 'entry_date' },
    { title: '放罐', dataIndex: 'discharge_date', render: value => value || '-' },
    { title: '罐产', dataIndex: 'tank_yield', render: value => value ?? '-' },
    { title: '状态', dataIndex: 'status', render: value => <Tag color={statusColor[value]}>{value}</Tag> },
    { title: '操作', key: 'action', render: (_, row) => <Space><Button type="text" icon={<EditOutlined />} onClick={() => openEdit('fermentation', row)} /><Popconfirm title="确认删除？" onConfirm={() => remove('fermentation', row.id)}><Button type="text" danger icon={<DeleteOutlined />} /></Popconfirm></Space> },
  ]
  const seedColumns: ColumnsType<SeedCulture> = [
    { title: '摇瓶批号', dataIndex: 'batch_no' }, { title: '产品', dataIndex: 'product_name' },
    { title: '配制日期', dataIndex: 'prepare_date', render: value => value || '-' },
    { title: '罐产', dataIndex: 'tank_yield', render: value => value ?? '-' },
    { title: '物料批次', dataIndex: 'materials', render: value => Object.keys(value || {}).length ? `${Object.keys(value).length} 项` : '-' },
    { title: '状态', dataIndex: 'status', render: value => <Tag color={statusColor[value]}>{value}</Tag> },
    { title: '操作', key: 'action', render: (_, row) => <Space><Button type="text" icon={<EditOutlined />} onClick={() => openEdit('seed', row)} /><Popconfirm title="确认删除？" onConfirm={() => remove('seed', row.id)}><Button type="text" danger icon={<DeleteOutlined />} /></Popconfirm></Space> },
  ]

  return <Space orientation="vertical" size={16} style={{ width: '100%' }}>
    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
      <div><Typography.Title level={3} style={{ margin: 0 }}>发酵与种子培养</Typography.Title><Typography.Text type="secondary">覆盖摇瓶制备、进罐周期、放罐和罐产记录</Typography.Text></div>
      <Button icon={<ReloadOutlined />} onClick={reload}>刷新</Button>
    </Space>
    <Card>
      <Tabs items={[
        { key: 'fermentation', label: `发酵记录 (${fermentations.length})`, children: <><Button type="primary" icon={<PlusOutlined />} onClick={() => open('fermentation')} style={{ marginBottom: 16 }}>新增发酵记录</Button><Table rowKey="id" columns={fermentationColumns} dataSource={fermentations} scroll={{ x: 900 }} /></> },
        { key: 'seed', label: `种子培养 (${seedCultures.length})`, children: <><Button type="primary" icon={<PlusOutlined />} onClick={() => open('seed')} style={{ marginBottom: 16 }}>新增种子记录</Button><Table rowKey="id" columns={seedColumns} dataSource={seedCultures} scroll={{ x: 800 }} /></> },
      ]} />
    </Card>
    <Modal title={`${editing ? '编辑' : '新增'}${kind === 'fermentation' ? '发酵记录' : '种子培养记录'}`} open={kind !== null} onCancel={() => { setKind(null); setEditing(null) }} onOk={submit} confirmLoading={submitting} width={760} destroyOnHidden>
      <Form form={form} layout="vertical">
        <Space.Compact block><Form.Item name="batch_no" label="批号" rules={[{ required: true }]} style={{ width: '50%' }}><Input /></Form.Item><Form.Item name="product_name" label="产品" rules={[{ required: true }]} style={{ width: '50%' }}><Input /></Form.Item></Space.Compact>
        {kind === 'fermentation' && <Form.Item name="fermenter" label="发酵罐" rules={[{ required: true }]}><Input /></Form.Item>}
        <Space.Compact block><Form.Item name="record_date" label={kind === 'fermentation' ? '进罐日期' : '配制日期'} rules={[{ required: kind === 'fermentation' }]} style={{ width: '50%' }}><DatePicker style={{ width: '100%' }} /></Form.Item><Form.Item name="tank_yield" label="罐产" style={{ width: '50%' }}><InputNumber style={{ width: '100%' }} /></Form.Item></Space.Compact>
        <Form.Item name="status" label="状态"><Select options={[{ value: 'in_progress', label: '进行中' }, { value: 'completed', label: '已完成' }, { value: 'abnormal', label: '异常' }]} /></Form.Item>
        {kind === 'fermentation' ? <><Typography.Text strong>发酵周期</Typography.Text><div className="mt-2 grid grid-cols-2 gap-x-4 md:grid-cols-3">{[1, 2, 3, 4, 5, 6].map(index => <Form.Item key={index} name={`cycle_${index}`} label={`周期 ${index}`}><InputNumber style={{ width: '100%' }} /></Form.Item>)}</div></> : <><Typography.Text strong>物料批次</Typography.Text><div className="mt-2 grid grid-cols-1 gap-x-4 md:grid-cols-2"><Form.Item name="glucose_batch" label="葡萄糖批次"><Input /></Form.Item><Form.Item name="corn_starch_batch" label="玉米淀粉批次"><Input /></Form.Item><Form.Item name="corn_syrup_batch" label="玉米浆批次"><Input /></Form.Item><Form.Item name="ammonium_sulfate_batch" label="硫酸铵批次"><Input /></Form.Item><Form.Item name="soybean_meal_batch" label="豆粕批次"><Input /></Form.Item><Form.Item name="calcium_carbonate_batch" label="碳酸钙批次"><Input /></Form.Item></div></>}
        <Form.Item name="remarks" label="备注"><Input.TextArea rows={2} /></Form.Item>
      </Form>
    </Modal>
  </Space>
}
