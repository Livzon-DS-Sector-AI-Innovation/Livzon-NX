'use client'

import { useEffect, useState, useCallback } from 'react'
import {
  Table, Button, Space, Input, Modal, Form, InputNumber, AutoComplete,
  Card, Typography, DatePicker, App, Descriptions, Row, Col, Divider,
  Tabs, Switch, Empty,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  PlusOutlined, SearchOutlined, EditOutlined, DeleteOutlined,
  ExperimentOutlined, ControlOutlined,
} from '@ant-design/icons'
import {
  getSeedCultures, createSeedCulture,
  updateSeedCulture, deleteSeedCulture,
} from '@/actions/seed-culture'
import type { SeedCultureRecord, SeedCultureCreate } from '@/types/seed-culture'
import SyncSettingsButton from '@/components/production/SyncSettingsButton'
import dayjs from 'dayjs'

const { Text, Title } = Typography
const { TextArea } = Input

const PRODUCTS = [
  { key: 'doramectin', label: '多拉菌素', productName: '多拉菌素' },
  { key: 'lincomycin', label: '盐酸林可霉素', productName: '盐酸林可霉素' },
  { key: 'phenylalanine', label: '苯丙氨酸', productName: '苯丙氨酸' },
  { key: 'lovastatin', label: '洛伐他汀', productName: '洛伐他汀' },
  { key: 'mevastatin', label: '美伐他汀', productName: '美伐他汀' },
]

const LINE_STORAGE_KEY = 'workshop_1011_active_products'

export default function SeedCulturePage() {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [records, setRecords] = useState<SeedCultureRecord[]>([])
  const [modalVisible, setModalVisible] = useState(false)
  const [editing, setEditing] = useState<SeedCultureRecord | null>(null)
  const [searchText, setSearchText] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [detailVisible, setDetailVisible] = useState(false)
  const [detailRecord, setDetailRecord] = useState<SeedCultureRecord | null>(null)

  // ─── 产线配置 ───
  const [activeProducts, setActiveProducts] = useState<Set<string>>(() => {
    if (typeof window === 'undefined') return new Set(PRODUCTS.map(p => p.key))
    const saved = localStorage.getItem(LINE_STORAGE_KEY)
    if (!saved) return new Set(PRODUCTS.map(p => p.key))
    try { return new Set(JSON.parse(saved)) } catch { return new Set(PRODUCTS.map(p => p.key)) }
  })
  const [lineConfigVisible, setLineConfigVisible] = useState(false)
  const [tempActive, setTempActive] = useState<Set<string>>(new Set())
  const visibleProducts = PRODUCTS.filter(p => activeProducts.has(p.key))

  const [activeKey, setActiveKey] = useState(() => {
    const first = PRODUCTS.find(p => activeProducts.has(p.key))
    return first ? first.key : PRODUCTS[0].key
  })
  const currentProduct = PRODUCTS.find(p => p.key === activeKey) || PRODUCTS[0]

  useEffect(() => {
    if (!activeProducts.has(activeKey)) {
      const first = PRODUCTS.find(p => activeProducts.has(p.key))
      if (first) setActiveKey(first.key) // eslint-disable-line react-hooks/set-state-in-effect
    }
  }, [activeProducts]) // eslint-disable-line react-hooks/exhaustive-deps

  // ─── 输入历史 ───
  const [fieldHistory, setFieldHistory] = useState<Record<string, string[]>>(() => {
    if (typeof window === 'undefined') return {}
    try { return JSON.parse(localStorage.getItem('seed_culture_history') || '{}') } catch { return {} }
  })
  const saveHistory = (values: Record<string, unknown>) => {
    const next = { ...fieldHistory }
    for (const [k, v] of Object.entries(values)) {
      if (!v || typeof v !== 'string' || !v.trim()) continue
      if (!next[k]) next[k] = []
      if (!next[k].includes(v)) next[k] = [v, ...next[k]].slice(0, 20)
    }
    setFieldHistory(next)
    localStorage.setItem('seed_culture_history', JSON.stringify(next))
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getSeedCultures({ page: 1, page_size: 200, product_name: currentProduct.productName, batch_no: searchText || undefined })
      if (res.code === 200) setRecords(res.data)
      else message.error('加载失败')
    } catch { message.error('加载失败') }
    finally { setLoading(false) }
  }, [currentProduct.productName, searchText, message])

  useEffect(() => { load() }, [load]) // eslint-disable-line react-hooks/set-state-in-effect

  const handleTabChange = (key: string) => {
    setActiveKey(key); setSearchText(''); setPage(1)
  }

  const paginated = records.slice((page - 1) * pageSize, page * pageSize)

  const openForm = (r?: SeedCultureRecord) => {
    if (r) {
      setEditing(r)
      editForm.setFieldsValue({
        ...r, product_name: r.product_name || currentProduct.productName,
        prepare_date: r.prepare_date ? dayjs(r.prepare_date) : null,
        shaker_start_date: r.shaker_start_date ? dayjs(r.shaker_start_date) : null,
        merge_time: r.merge_time ? dayjs(r.merge_time) : null,
      })
    } else {
      setEditing(null); form.resetFields()
    }
    setModalVisible(true)
  }

  const handleDelete = (id: string) => {
    modal.confirm({
      title: '确认删除', onOk: async () => {
        const res = await deleteSeedCulture(id)
        if (res.code === 200) { message.success('已删除'); load() }
        else message.error(res.message || '删除失败')
      },
    })
  }

  const handleSubmit = async () => {
    try {
      const values = editing ? await editForm.validateFields() : await form.validateFields()
      const data: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(values)) {
        if (v instanceof dayjs) { data[k] = (v as dayjs.Dayjs).format('YYYY-MM-DD HH:mm:ss'); continue }
        if ((v as dayjs.Dayjs)?.toISOString) { data[k] = (v as dayjs.Dayjs).toISOString(); continue }
        data[k] = v || null
      }
      if (!data.product_name) data.product_name = currentProduct.productName
      if (editing) {
        const res = await updateSeedCulture(editing.id, data)
        if (res.code === 200) { message.success('已更新'); setModalVisible(false); load() }
        else message.error(res.message || '更新失败')
      } else {
        const res = await createSeedCulture(data as unknown as SeedCultureCreate)
        if (res.code === 200) { message.success('已创建'); saveHistory(data); setModalVisible(false); form.resetFields(); load() }
        else message.error(res.message || '创建失败')
      }
    } catch { message.error('请检查表单填写') }
  }

  const handleLineConfigOpen = () => { setTempActive(new Set(activeProducts)); setLineConfigVisible(true) }
  const handleLineConfigSave = () => {
    setActiveProducts(tempActive)
    localStorage.setItem(LINE_STORAGE_KEY, JSON.stringify([...tempActive]))
    setLineConfigVisible(false)
    if (!tempActive.has(activeKey)) {
      const first = PRODUCTS.find(p => tempActive.has(p.key))
      if (first) handleTabChange(first.key)
    }
  }

  const columns: ColumnsType<SeedCultureRecord> = [
    { title: '摇瓶批号', dataIndex: 'batch_no', width: 100, fixed: 'left' },
    { title: '配制日期', dataIndex: 'prepare_date', width: 100 },
    { title: '物料A/批号', dataIndex: 'glucose_batch', width: 110, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '物料B/批号', dataIndex: 'corn_starch_batch', width: 110, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '物料C/批号', dataIndex: 'corn_syrup_batch', width: 110, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '物料D/批号', dataIndex: 'ammonium_sulfate_batch', width: 110, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '物料E/批号', dataIndex: 'soybean_meal_batch', width: 110, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '物料F/批号', dataIndex: 'calcium_carbonate_batch', width: 110, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '配制操作人', dataIndex: 'prepare_operator', width: 110, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '种子消毒人员', dataIndex: 'sterilization_operator', width: 110, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '调前PH', dataIndex: 'ph_before_adjust', width: 80, render: (v: number|null) => v ?? '-' },
    { title: '调后PH', dataIndex: 'ph_after_adjust', width: 80, render: (v: number|null) => v ?? '-' },
    { title: '消后PH', dataIndex: 'ph_after_sterilization', width: 80, render: (v: number|null) => v ?? '-' },
    { title: '还原糖', dataIndex: 'reducing_sugar', width: 80, render: (v: number|null) => v ?? '-' },
    { title: '总糖', dataIndex: 'total_sugar', width: 80, render: (v: number|null) => v ?? '-' },
    { title: '氨基氮', dataIndex: 'amino_nitrogen', width: 80, render: (v: number|null) => v ?? '-' },
    { title: '冻管菌号', dataIndex: 'strain_tube_no', width: 100, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '上摇床人员', dataIndex: 'shaker_setup_operator', width: 110, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '摇床编号', dataIndex: 'shaker_no', width: 90, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '上摇床日期', dataIndex: 'shaker_start_date', width: 100 },
    { title: '接种人员', dataIndex: 'inoculation_operator', width: 110, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '用具编号', dataIndex: 'tool_no', width: 90, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '并瓶时间', dataIndex: 'merge_time', width: 140, render: (v: string|null) => v ? dayjs(v).format('MM-DD HH:mm') : '-' },
    { title: '并瓶数量', dataIndex: 'merge_count', width: 80, render: (v: number|null) => v ?? '-' },
    { title: '并瓶周期', dataIndex: 'merge_cycle', width: 80, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '并瓶PH', dataIndex: 'merge_ph', width: 80, render: (v: number|null) => v ?? '-' },
    { title: '并瓶菌浓', dataIndex: 'merge_bacteria_density', width: 80, render: (v: number|null) => v ?? '-' },
    { title: '并瓶总糖', dataIndex: 'merge_total_sugar', width: 80, render: (v: number|null) => v ?? '-' },
    { title: '并瓶还原糖', dataIndex: 'merge_reducing_sugar', width: 90, render: (v: number|null) => v ?? '-' },
    { title: '并瓶氨基氮', dataIndex: 'merge_amino_nitrogen', width: 90, render: (v: number|null) => v ?? '-' },
    { title: '进罐人员', dataIndex: 'tank_setup_operator', width: 100, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '钢瓶编号', dataIndex: 'cylinder_no', width: 90, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '并瓶操作人', dataIndex: 'merge_operator', width: 110, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '车间接种人员', dataIndex: 'workshop_inoculation_operator', width: 110, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '备注（罐号）', dataIndex: 'tank_remarks', width: 100, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '罐产', dataIndex: 'tank_yield', width: 80, render: (v: number|null) => v ?? '-' },
    { title: '备注', dataIndex: 'remarks', width: 140, ellipsis: true, render: (v: string|null) => v || '-' },
    { title: '操作', key: 'action', width: 160, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => { setDetailRecord(r); setDetailVisible(true) }}>详情</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openForm(r)}>编辑</Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r.id)}>删除</Button>
        </Space>
      ),
    },
  ]

  const field = (name: string, label: string, placeholder?: string, type: 'text'|'number'|'date'='text', span=8) => (
    <Col span={span} key={name}>
      <Form.Item name={name} label={label}>
        {type === 'number' ? <InputNumber style={{ width: '100%' }} placeholder={placeholder} /> :
         type === 'date' ? <DatePicker style={{ width: '100%' }} /> :
         <AutoComplete options={(fieldHistory[name] || []).map(v => ({ value: v }))} placeholder={placeholder}>
           <Input />
         </AutoComplete>}
      </Form.Item>
    </Col>
  )

  const formContent = (
    <>
      <Divider plain style={{ fontSize: 13, margin: '8px 0' }}>基本信息</Divider>
      <Row gutter={16}>
        {field('batch_no', '摇瓶批号', '请输入', 'text', 8)}
        {field('prepare_date', '配制日期', undefined, 'date', 8)}
        {field('strain_tube_no', '冻管菌号', '请输入', 'text', 8)}
      </Row>
      <Divider plain style={{ fontSize: 13, margin: '8px 0' }}>原料批号</Divider>
      <Row gutter={16}>
        {field('glucose_batch', '物料A/批号', '', 'text', 8)}
        {field('corn_starch_batch', '物料B/批号', '', 'text', 8)}
        {field('corn_syrup_batch', '物料C/批号', '', 'text', 8)}
        {field('ammonium_sulfate_batch', '物料D/批号', '', 'text', 8)}
        {field('soybean_meal_batch', '物料E/批号', '', 'text', 8)}
        {field('calcium_carbonate_batch', '物料F/批号', '', 'text', 8)}
      </Row>
      <Divider plain style={{ fontSize: 13, margin: '8px 0' }}>配制与接种</Divider>
      <Row gutter={16}>
        {field('prepare_operator', '配制操作人/复核人', '', 'text', 8)}
        {field('sterilization_operator', '种子消毒人员', '', 'text', 8)}
        {field('ph_before_adjust', '调前PH', '', 'number', 6)}
        {field('ph_after_adjust', '调后PH', '', 'number', 6)}
        {field('ph_after_sterilization', '消后PH', '', 'number', 6)}
        {field('reducing_sugar', '还原糖', '', 'number', 6)}
        {field('total_sugar', '总糖', '', 'number', 6)}
        {field('amino_nitrogen', '氨基氮', '', 'number', 6)}
        {field('shaker_setup_operator', '上摇床摆东西人员', '', 'text', 8)}
        {field('shaker_no', '摇床编号', '', 'text', 8)}
        {field('shaker_start_date', '上摇床日期', '', 'date', 8)}
        {field('inoculation_operator', '接种人员/复核人', '', 'text', 8)}
        {field('tool_no', '用具编号', '', 'text', 8)}
      </Row>
      <Divider plain style={{ fontSize: 13, margin: '8px 0' }}>并瓶数据</Divider>
      <Row gutter={16}>
        {field('merge_time', '并瓶时间', '', 'date', 8)}
        {field('merge_count', '并瓶数量(瓶)', '', 'number', 6)}
        {field('merge_cycle', '并瓶周期', '', 'text', 6)}
        {field('merge_ph', '并瓶PH', '', 'number', 6)}
        {field('merge_bacteria_density', '并瓶菌浓', '', 'number', 6)}
        {field('merge_total_sugar', '并瓶总糖', '', 'number', 6)}
        {field('merge_reducing_sugar', '并瓶还原糖', '', 'number', 6)}
        {field('merge_amino_nitrogen', '并瓶氨基氮', '', 'number', 6)}
        {field('merge_operator', '并瓶操作人/复核人', '', 'text', 8)}
        {field('tank_setup_operator', '进罐摆东西人员', '', 'text', 8)}
        {field('cylinder_no', '钢瓶编号', '', 'text', 8)}
        {field('workshop_inoculation_operator', '车间接种人员', '', 'text', 8)}
        {field('tank_yield', '罐产', '', 'number', 6)}
        {field('tank_remarks', '备注（罐号）', '', 'text', 8)}
      </Row>
      <Form.Item name="remarks" label="备注"><TextArea rows={2} /></Form.Item>
    </>
  )

  return (
    <div className="p-6">
      {visibleProducts.length > 1 && (
        <Tabs activeKey={activeKey} onChange={handleTabChange}
          items={visibleProducts.map(p => ({ key: p.key, label: p.label }))}
          tabBarStyle={{ marginBottom: 16 }} />
      )}
      {visibleProducts.length === 0 ? (
        <Card><Empty description="暂无在生产产品，请配置产线" />
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <Button type="primary" icon={<ControlOutlined />} onClick={handleLineConfigOpen}>产线配置</Button></div>
        </Card>
      ) : (
        <>
          <div className="mb-6">
            <Title level={4}><ExperimentOutlined className="mr-2" />{currentProduct.productName} — 摇瓶种子制备记录</Title>
            <Text type="secondary">菌种制备全流程跟踪</Text>
            <div style={{ marginTop: 8 }}>
              <SyncSettingsButton productName={currentProduct.productName} />
              <Button size="small" icon={<ControlOutlined />} onClick={handleLineConfigOpen}>产线配置</Button>
            </div>
          </div>
          <Card extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openForm()}>新建记录</Button>}>
            <Row gutter={16} className="mb-4">
              <Col span={6}><Input placeholder="搜索摇瓶批号" prefix={<SearchOutlined />} value={searchText}
                onChange={e => setSearchText(e.target.value)} allowClear /></Col>
              <Col><Button type="primary" icon={<SearchOutlined />} onClick={() => { setPage(1); load() }}>查询</Button></Col>
            </Row>
            <Table columns={columns} dataSource={paginated} rowKey="id" loading={loading} scroll={{ x: 3600 }}
              pagination={{ current: page, pageSize, total: records.length, showSizeChanger: true,
                showTotal: t => `共 ${t} 条`, onChange: (p, ps) => { setPage(p); setPageSize(ps) } }} />
          </Card>
        </>
      )}

      <Modal title={editing ? '编辑记录' : '新建记录'} open={modalVisible} onOk={handleSubmit}
        onCancel={() => setModalVisible(false)} width={960} okText="确认" cancelText="取消" destroyOnHidden style={{ top: 20 }}>
        <Form form={editing ? editForm : form} layout="vertical"
          initialValues={{ product_name: currentProduct.productName }}
          style={{ maxHeight: '70vh', overflow: 'auto', paddingRight: 8 }}>
          <Form.Item name="product_name" hidden><Input /></Form.Item>
          {formContent}
        </Form>
      </Modal>

      <Modal title="记录详情" open={detailVisible} onCancel={() => setDetailVisible(false)} footer={null} width={800}>
        {detailRecord && (
          <Descriptions column={3} bordered size="small">
            <Descriptions.Item label="产品">{detailRecord.product_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="摇瓶批号">{detailRecord.batch_no}</Descriptions.Item>
            <Descriptions.Item label="配制日期">{detailRecord.prepare_date || '-'}</Descriptions.Item>
            <Descriptions.Item label="物料A/批号">{detailRecord.glucose_batch || '-'}</Descriptions.Item>
            <Descriptions.Item label="物料B/批号">{detailRecord.corn_starch_batch || '-'}</Descriptions.Item>
            <Descriptions.Item label="物料C/批号">{detailRecord.corn_syrup_batch || '-'}</Descriptions.Item>
            <Descriptions.Item label="物料D/批号">{detailRecord.ammonium_sulfate_batch || '-'}</Descriptions.Item>
            <Descriptions.Item label="物料E/批号">{detailRecord.soybean_meal_batch || '-'}</Descriptions.Item>
            <Descriptions.Item label="物料F/批号">{detailRecord.calcium_carbonate_batch || '-'}</Descriptions.Item>
            <Descriptions.Item label="配制操作人">{detailRecord.prepare_operator || '-'}</Descriptions.Item>
            <Descriptions.Item label="种子消毒人员">{detailRecord.sterilization_operator || '-'}</Descriptions.Item>
            <Descriptions.Item label="冻管菌号">{detailRecord.strain_tube_no || '-'}</Descriptions.Item>
            <Descriptions.Item label="调前PH">{detailRecord.ph_before_adjust ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="调后PH">{detailRecord.ph_after_adjust ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="消后PH">{detailRecord.ph_after_sterilization ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="还原糖">{detailRecord.reducing_sugar ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="总糖">{detailRecord.total_sugar ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="氨基氮">{detailRecord.amino_nitrogen ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="上摇床人员">{detailRecord.shaker_setup_operator || '-'}</Descriptions.Item>
            <Descriptions.Item label="摇床编号">{detailRecord.shaker_no || '-'}</Descriptions.Item>
            <Descriptions.Item label="上摇床日期">{detailRecord.shaker_start_date || '-'}</Descriptions.Item>
            <Descriptions.Item label="接种人员">{detailRecord.inoculation_operator || '-'}</Descriptions.Item>
            <Descriptions.Item label="用具编号">{detailRecord.tool_no || '-'}</Descriptions.Item>
            <Descriptions.Item label="并瓶时间">{detailRecord.merge_time ? dayjs(detailRecord.merge_time).format('YYYY-MM-DD HH:mm') : '-'}</Descriptions.Item>
            <Descriptions.Item label="并瓶数量">{detailRecord.merge_count ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="并瓶周期">{detailRecord.merge_cycle || '-'}</Descriptions.Item>
            <Descriptions.Item label="并瓶PH">{detailRecord.merge_ph ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="并瓶菌浓">{detailRecord.merge_bacteria_density ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="并瓶总糖">{detailRecord.merge_total_sugar ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="并瓶还原糖">{detailRecord.merge_reducing_sugar ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="并瓶氨基氮">{detailRecord.merge_amino_nitrogen ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="进罐人员">{detailRecord.tank_setup_operator || '-'}</Descriptions.Item>
            <Descriptions.Item label="钢瓶编号">{detailRecord.cylinder_no || '-'}</Descriptions.Item>
            <Descriptions.Item label="并瓶操作人">{detailRecord.merge_operator || '-'}</Descriptions.Item>
            <Descriptions.Item label="车间接种人员">{detailRecord.workshop_inoculation_operator || '-'}</Descriptions.Item>
            <Descriptions.Item label="罐产">{detailRecord.tank_yield ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="备注（罐号）">{detailRecord.tank_remarks || '-'}</Descriptions.Item>
            <Descriptions.Item label="备注">{detailRecord.remarks || '-'}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{dayjs(detailRecord.created_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
            <Descriptions.Item label="更新时间">{dayjs(detailRecord.updated_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>

      <Modal title="产线配置" open={lineConfigVisible} onOk={handleLineConfigSave}
        onCancel={() => setLineConfigVisible(false)} width={360} okText="保存" cancelText="取消">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {PRODUCTS.map(p => (
            <div key={p.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>{p.label}</span>
              <Switch checked={tempActive.has(p.key)} onChange={checked => {
                const next = new Set(tempActive); if (checked) { next.add(p.key) } else { next.delete(p.key) }; setTempActive(next)
              }} checkedChildren="生产中" unCheckedChildren="停产" />
            </div>
          ))}
        </div>
      </Modal>
    </div>
  )
}
