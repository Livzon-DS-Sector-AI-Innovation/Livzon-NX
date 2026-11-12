'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Avatar, Table, Button, Space, Input, Modal, Form, InputNumber,
  Card, Typography, DatePicker, App, Descriptions, Row, Col, Divider,
  Tabs, Tooltip, Segmented,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  PlusOutlined, SearchOutlined, EditOutlined, DeleteOutlined,
  ExperimentOutlined,
} from '@ant-design/icons'
import {
  getSeedCultures, createSeedCulture,
  updateSeedCulture, deleteSeedCulture, getPersonMonthly,
} from '@/actions/seed-culture'
import type { PersonMonthlyRow, SeedCulturePerson, SeedCultureRecord } from '@/types/seed-culture'
import SyncSettingsButton from '@/components/production/SyncSettingsButton'
import { PRODUCTION_PAGE_KEYS, useProductionPermissions } from '@/components/production/useProductionPermissions'
import dayjs from 'dayjs'

const { Text, Title } = Typography
const { TextArea } = Input

// 101一车间（菌种）：五个固定产品 Tab。字段配置以林可（盐酸林可霉素）
// 飞书位表为源（37 列，列名/顺序照搬）；其余产品待各自表格配置后重建。
const PRODUCTS = [
  { key: 'doramectin', label: '多拉菌素' },
  { key: 'lincomycin', label: '盐酸林可霉素', productName: '盐酸林可霉素', active: true },
  { key: 'phenylalanine', label: '苯丙氨酸' },
  { key: 'lovastatin', label: '洛伐他汀' },
  { key: 'mevastatin', label: '美伐他汀' },
]

// 飞书位表列定义（顺序照搬源表；kind 决定渲染与表单控件）
type FieldKind = 'text' | 'number' | 'date' | 'datetime' | 'person'
const LINCOMYCIN_FIELDS: { dataIndex: string; title: string; kind: FieldKind; width: number }[] = [
  { dataIndex: 'batch_no', title: '摇瓶批号', kind: 'text', width: 110 },
  { dataIndex: 'prepare_date', title: '配置日期', kind: 'date', width: 100 },
  { dataIndex: 'glucose_batch', title: '葡萄糖/批号', kind: 'text', width: 110 },
  { dataIndex: 'corn_starch_batch', title: '玉米淀粉/批号', kind: 'text', width: 120 },
  { dataIndex: 'corn_syrup_batch', title: '玉米浆/批号', kind: 'text', width: 110 },
  { dataIndex: 'ammonium_sulfate_batch', title: '硫酸铵/批号', kind: 'text', width: 110 },
  { dataIndex: 'soybean_meal_batch', title: '黄豆饼粉/批号', kind: 'text', width: 120 },
  { dataIndex: 'calcium_carbonate_batch', title: '碳酸钙/批号', kind: 'text', width: 110 },
  { dataIndex: 'prepare_operator', title: '配制操作人/复核人', kind: 'person', width: 150 },
  { dataIndex: 'sterilization_operator', title: '种子消毒人员', kind: 'person', width: 140 },
  { dataIndex: 'ph_before_adjust', title: '调前PH', kind: 'number', width: 80 },
  { dataIndex: 'ph_after_adjust', title: '调后PH', kind: 'number', width: 80 },
  { dataIndex: 'ph_after_sterilization', title: '消后PH', kind: 'number', width: 80 },
  { dataIndex: 'reducing_sugar', title: '还原糖', kind: 'number', width: 80 },
  { dataIndex: 'total_sugar', title: '总糖', kind: 'number', width: 80 },
  { dataIndex: 'amino_nitrogen', title: '氨基氮', kind: 'number', width: 80 },
  { dataIndex: 'strain_tube_no', title: '冻管菌号', kind: 'text', width: 130 },
  { dataIndex: 'shaker_setup_operator', title: '上摇床摆东西人员', kind: 'person', width: 160 },
  { dataIndex: 'shaker_no', title: '摇床编号', kind: 'text', width: 90 },
  { dataIndex: 'shaker_start_date', title: '上摇床日期', kind: 'date', width: 100 },
  { dataIndex: 'inoculation_operator', title: '接种人员/复核人', kind: 'person', width: 150 },
  { dataIndex: 'tool_no', title: '用具编号', kind: 'text', width: 90 },
  { dataIndex: 'merge_time', title: '并瓶时间', kind: 'datetime', width: 130 },
  { dataIndex: 'merge_count', title: '并瓶数量(瓶）', kind: 'number', width: 110 },
  { dataIndex: 'merge_cycle', title: '并瓶周期', kind: 'text', width: 90 },
  { dataIndex: 'merge_ph', title: '并瓶PH', kind: 'number', width: 80 },
  { dataIndex: 'merge_bacteria_density', title: '并瓶菌浓', kind: 'number', width: 90 },
  { dataIndex: 'merge_total_sugar', title: '并瓶总糖', kind: 'number', width: 90 },
  { dataIndex: 'merge_reducing_sugar', title: '并瓶还原糖', kind: 'number', width: 100 },
  { dataIndex: 'merge_amino_nitrogen', title: '并瓶氨基氮', kind: 'number', width: 100 },
  { dataIndex: 'tank_setup_operator', title: '进罐摆东西人员', kind: 'person', width: 150 },
  { dataIndex: 'cylinder_no', title: '钢瓶编号', kind: 'text', width: 90 },
  { dataIndex: 'merge_operator', title: '并瓶操作人/复核人', kind: 'person', width: 150 },
  { dataIndex: 'workshop_inoculation_operator', title: '车间接种人员', kind: 'person', width: 140 },
  { dataIndex: 'tank_remarks', title: '备注（罐号）', kind: 'text', width: 110 },
  { dataIndex: 'tank_yield', title: '罐产', kind: 'number', width: 80 },
  { dataIndex: 'remarks', title: '备注', kind: 'text', width: 140 },
]

// 绩效统计的环节列（与后端 ROLE_LABELS 一一对应）
const ROLE_LABELS = [
  { key: 'prepare_operator', label: '配制' },
  { key: 'sterilization_operator', label: '消毒' },
  { key: 'shaker_setup_operator', label: '摇床摆放' },
  { key: 'inoculation_operator', label: '接种' },
  { key: 'merge_operator', label: '并瓶' },
  { key: 'tank_setup_operator', label: '进罐' },
  { key: 'workshop_inoculation_operator', label: '车间接种' },
]

const PERSON_FIELDS = new Set(
  LINCOMYCIN_FIELDS.filter((f) => f.kind === 'person').map((f) => f.dataIndex),
)

/** 人员值归一：兼容历史文本（"张三,李四" / JSON 串）与数组 */
function normalizePeople(value: SeedCulturePerson[] | string | null | undefined): SeedCulturePerson[] {
  if (!value) return []
  if (Array.isArray(value)) return value
  if (typeof value === 'string') {
    const stripped = value.trim()
    if (!stripped) return []
    try {
      const parsed: unknown = JSON.parse(stripped)
      if (Array.isArray(parsed)) return parsed as SeedCulturePerson[]
    } catch { /* 纯文本 */ }
    return stripped
      .split(/[,，、]/)
      .map((name) => ({ name: name.trim() }))
      .filter((p) => p.name)
  }
  return []
}

function PersonChips({ value }: { value: unknown }) {
  const people = normalizePeople(value as SeedCulturePerson[] | string | null)
  if (!people.length) return <>-</>
  return (
    <Space size={4} wrap>
      {people.map((p, i) => (
        <Tooltip key={`${p.open_id ?? p.name}-${i}`} title={p.name || '未知成员'}>
          <span className="inline-flex items-center gap-1">
            {p.avatar_url ? (
              <Avatar size={20} src={p.avatar_url} />
            ) : (
              <Avatar size={20} style={{ background: '#8b93e8', fontSize: 12 }}>
                {(p.name || '?').slice(0, 1)}
              </Avatar>
            )}
            <span>{p.name || '未知成员'}</span>
          </span>
        </Tooltip>
      ))}
    </Space>
  )
}

function personNames(value: unknown): string {
  return normalizePeople(value as SeedCulturePerson[] | string | null)
    .map((p) => p.name)
    .filter(Boolean)
    .join(',')
}

function PersonMonthlyStats({ productName }: { productName: string }) {
  const { message } = App.useApp()
  const [month, setMonth] = useState<string>(dayjs().format('YYYY-MM'))
  const [rows, setRows] = useState<PersonMonthlyRow[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (m: string) => {
    setLoading(true)
    try {
      const res = await getPersonMonthly({ month: m, product_name: productName })
      if (res.code === 200) setRows(res.data)
      else message.error(res.message || '统计加载失败')
    } catch {
      message.error('统计加载失败')
    } finally {
      setLoading(false)
    }
  }, [productName, message])

  useEffect(() => { load(month) }, [load, month]) // eslint-disable-line react-hooks/set-state-in-effect

  const columns: ColumnsType<PersonMonthlyRow> = [
    {
      title: '人员', dataIndex: 'name', key: 'name', width: 170, fixed: 'left',
      render: (_: unknown, r: PersonMonthlyRow) => (
        <span className="inline-flex items-center gap-2">
          {r.avatar_url ? (
            <Avatar size={24} src={r.avatar_url} />
          ) : (
            <Avatar size={24} style={{ background: '#8b93e8', fontSize: 12 }}>
              {(r.name || '?').slice(0, 1)}
            </Avatar>
          )}
          <span>{r.name || '未知成员'}</span>
        </span>
      ),
    },
    { title: '参与批次', dataIndex: 'total_batches', key: 'total_batches', width: 90 },
    ...ROLE_LABELS.map((role) => ({
      title: role.label, key: role.key, width: 80,
      render: (_: unknown, r: PersonMonthlyRow) => r.role_counts?.[role.label] || 0,
    })),
  ]

  return (
    <Card
      extra={
        <Space size={8}>
          <DatePicker
            picker="month" allowClear={false} style={{ width: 120 }}
            value={dayjs(month)}
            onChange={(d) => { if (d) setMonth(d.format('YYYY-MM')) }}
          />
        </Space>
      }
    >
      <Table<PersonMonthlyRow>
        columns={columns} dataSource={rows} rowKey="key" loading={loading}
        scroll={{ x: 900 }}
        pagination={false}
        expandable={{
          expandedRowRender: (r: PersonMonthlyRow) => (
            <ul className="m-0 pl-6" style={{ listStyle: 'disc' }}>
              {r.details.map((d, i) => (
                <li key={`${d.batch_no}-${d.role}-${i}`}>
                  {d.date} · {d.batch_no} · {d.role}
                </li>
              ))}
            </ul>
          ),
        }}
      />
      <Text type="secondary" style={{ fontSize: 12 }}>
        按「配置日期」归属月份；同一人一批多环节计 1 批、各环节分别计数。
      </Text>
    </Card>
  )
}

function SeedCultureLedger({ productName, label }: { productName: string; label: string }) {
  const { message, modal } = App.useApp()
  const { canOperate, canDelete } = useProductionPermissions(PRODUCTION_PAGE_KEYS.workshop1011)
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
  // 表格吸顶/悬浮滚动条的滚动容器：应用布局在 <main> 内部滚动（非 window）
  const tableWrapRef = useRef<HTMLDivElement | null>(null)
  // 台账 / 人员统计 视图切换（人员统计=月度绩效依据）
  const [viewMode, setViewMode] = useState<'ledger' | 'stats'>('ledger')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getSeedCultures({ page: 1, page_size: 200, product_name: productName, batch_no: searchText || undefined })
      if (res.code === 200) setRecords(res.data)
      else message.error('加载失败')
    } catch { message.error('加载失败') }
    finally { setLoading(false) }
  }, [productName, searchText, message])

  useEffect(() => { load() }, [load]) // eslint-disable-line react-hooks/set-state-in-effect

  const paginated = records.slice((page - 1) * pageSize, page * pageSize)

  const openForm = (r?: SeedCultureRecord) => {
    if (!canOperate) return
    if (r) {
      setEditing(r)
      editForm.setFieldsValue({
        ...r, product_name: r.product_name || productName,
        prepare_date: r.prepare_date ? dayjs(r.prepare_date) : null,
        shaker_start_date: r.shaker_start_date ? dayjs(r.shaker_start_date) : null,
        merge_time: r.merge_time ? dayjs(r.merge_time) : null,
        ...Object.fromEntries(
          LINCOMYCIN_FIELDS.filter((f) => f.kind === 'person').map((f) => [
            f.dataIndex, personNames(r[f.dataIndex as keyof SeedCultureRecord]),
          ]),
        ),
      })
    } else {
      setEditing(null); form.resetFields()
    }
    setModalVisible(true)
  }

  const handleDelete = (id: string) => {
    if (!canDelete) return
    modal.confirm({
      title: '确认删除', onOk: async () => {
        const res = await deleteSeedCulture(id)
        if (res.code === 200) { message.success('已删除'); load() }
        else message.error(res.message || '删除失败')
      },
    })
  }

  const handleSubmit = async () => {
    if (!canOperate) return
    try {
      const values = editing ? await editForm.validateFields() : await form.validateFields()
      const data: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(values)) {
        if (PERSON_FIELDS.has(k)) {
          const names = String(v || '')
            .split(/[,，、]/)
            .map((n) => n.trim())
            .filter(Boolean)
          data[k] = names.length ? names.map((name) => ({ name })) : null
          continue
        }
        if (v instanceof dayjs) { data[k] = (v as dayjs.Dayjs).format('YYYY-MM-DD HH:mm:ss'); continue }
        if ((v as dayjs.Dayjs)?.toISOString) { data[k] = (v as dayjs.Dayjs).toISOString(); continue }
        data[k] = v || null
      }
      if (!data.product_name) data.product_name = productName
      if (editing) {
        const res = await updateSeedCulture(editing.id, data)
        if (res.code === 200) { message.success('已更新'); setModalVisible(false); load() }
        else message.error(res.message || '更新失败')
      } else {
        const res = await createSeedCulture(data as unknown as Parameters<typeof createSeedCulture>[0])
        if (res.code === 200) { message.success('已创建'); setModalVisible(false); form.resetFields(); load() }
        else message.error(res.message || '创建失败')
      }
    } catch { message.error('请检查表单填写') }
  }

  const columns: ColumnsType<SeedCultureRecord> = [
    ...LINCOMYCIN_FIELDS.map((f) => ({
      title: f.title,
      dataIndex: f.dataIndex,
      key: f.dataIndex,
      width: f.width,
      ellipsis: f.kind === 'person' ? false : { showTitle: true },
      fixed: f.dataIndex === 'batch_no' ? ('left' as const) : undefined,
      render: (v: unknown, record: SeedCultureRecord) => {
        if (f.kind === 'person') return <PersonChips value={record[f.dataIndex as keyof SeedCultureRecord]} />
        if (f.kind === 'datetime') return v ? dayjs(String(v)).format('MM-DD HH:mm') : '-'
        if (f.kind === 'date') return v ? String(v).slice(0, 10) : '-'
        if (f.kind === 'number') return v ?? '-'
        return (v as string | null) || '-'
      },
    })),
    {
      title: '操作', key: 'action', width: 160, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => { setDetailRecord(r); setDetailVisible(true) }}>详情</Button>
          {canOperate && <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openForm(r)}>编辑</Button>}
          {canDelete && <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r.id)}>删除</Button>}
        </Space>
      ),
    },
  ]

  const field = (name: string, label: string, placeholder?: string, type: 'text'|'number'|'date'|'person'='text', span=8) => (
    <Col span={span} key={name}>
      <Form.Item name={name} label={label}>
        {type === 'number' ? <InputNumber style={{ width: '100%' }} placeholder={placeholder} /> :
         type === 'date' ? <DatePicker style={{ width: '100%' }} /> :
         <Input placeholder={type === 'person' ? '多人用逗号分隔' : placeholder} />}
      </Form.Item>
    </Col>
  )

  const formContent = (
    <>
      <Divider plain style={{ fontSize: 13, margin: '8px 0' }}>基本信息</Divider>
      <Row gutter={16}>
        {field('batch_no', '摇瓶批号', '请输入', 'text', 8)}
        {field('prepare_date', '配置日期', undefined, 'date', 8)}
        {field('strain_tube_no', '冻管菌号', '', 'text', 8)}
      </Row>
      <Divider plain style={{ fontSize: 13, margin: '8px 0' }}>原料批号</Divider>
      <Row gutter={16}>
        {field('glucose_batch', '葡萄糖/批号')}
        {field('corn_starch_batch', '玉米淀粉/批号')}
        {field('corn_syrup_batch', '玉米浆/批号')}
        {field('ammonium_sulfate_batch', '硫酸铵/批号')}
        {field('soybean_meal_batch', '黄豆饼粉/批号')}
        {field('calcium_carbonate_batch', '碳酸钙/批号')}
      </Row>
      <Divider plain style={{ fontSize: 13, margin: '8px 0' }}>配制与接种</Divider>
      <Row gutter={16}>
        {field('prepare_operator', '配制操作人/复核人', '', 'person')}
        {field('sterilization_operator', '种子消毒人员', '', 'person')}
        {field('ph_before_adjust', '调前PH', '', 'number', 6)}
        {field('ph_after_adjust', '调后PH', '', 'number', 6)}
        {field('ph_after_sterilization', '消后PH', '', 'number', 6)}
        {field('reducing_sugar', '还原糖', '', 'number', 6)}
        {field('total_sugar', '总糖', '', 'number', 6)}
        {field('amino_nitrogen', '氨基氮', '', 'number', 6)}
        {field('shaker_setup_operator', '上摇床摆东西人员', '', 'person')}
        {field('shaker_no', '摇床编号')}
        {field('shaker_start_date', '上摇床日期', undefined, 'date', 8)}
        {field('inoculation_operator', '接种人员/复核人', '', 'person')}
        {field('tool_no', '用具编号')}
      </Row>
      <Divider plain style={{ fontSize: 13, margin: '8px 0' }}>并瓶数据</Divider>
      <Row gutter={16}>
        {field('merge_time', '并瓶时间', undefined, 'date', 8)}
        {field('merge_count', '并瓶数量(瓶）', '', 'number', 6)}
        {field('merge_cycle', '并瓶周期')}
        {field('merge_ph', '并瓶PH', '', 'number', 6)}
        {field('merge_bacteria_density', '并瓶菌浓', '', 'number', 6)}
        {field('merge_total_sugar', '并瓶总糖', '', 'number', 6)}
        {field('merge_reducing_sugar', '并瓶还原糖', '', 'number', 6)}
        {field('merge_amino_nitrogen', '并瓶氨基氮', '', 'number', 6)}
        {field('merge_operator', '并瓶操作人/复核人', '', 'person')}
        {field('tank_setup_operator', '进罐摆东西人员', '', 'person')}
        {field('cylinder_no', '钢瓶编号')}
        {field('workshop_inoculation_operator', '车间接种人员', '', 'person')}
        {field('tank_yield', '罐产', '', 'number', 6)}
        {field('tank_remarks', '备注（罐号）')}
      </Row>
      <Form.Item name="remarks" label="备注"><TextArea rows={2} /></Form.Item>
    </>
  )

  return (
    <>
      <div className="mb-4 flex items-baseline justify-between flex-wrap gap-2">
        <div className="flex items-baseline gap-3">
          <Text strong>{label} — 菌种台账</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>字段与飞书位表「数据表」一致</Text>
        </div>
        <Segmented
          value={viewMode}
          onChange={(v) => setViewMode(v as 'ledger' | 'stats')}
          options={[
            { label: '台账', value: 'ledger' },
            { label: '人员统计', value: 'stats' },
          ]}
        />
      </div>
      {viewMode === 'stats' ? (
        <PersonMonthlyStats productName={productName} />
      ) : (
      <>
      <Card
        extra={
          <Space size={8} wrap>
            <SyncSettingsButton
              productName={productName}
              pageKey={PRODUCTION_PAGE_KEYS.workshop1011}
              onSync={() => { void load(); }}
            />
            <Input
              placeholder="搜索摇瓶批号" prefix={<SearchOutlined />} value={searchText}
              onChange={e => setSearchText(e.target.value)} allowClear
              style={{ width: 220 }}
              onPressEnter={() => { setPage(1); load() }}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={() => { setPage(1); load() }}>查询</Button>
            {canOperate && <Button type="primary" icon={<PlusOutlined />} onClick={() => openForm()}>新建记录</Button>}
          </Space>
        }
      >
        <div ref={tableWrapRef}>
          <Table
            columns={columns} dataSource={paginated} rowKey="id" loading={loading}
            // 固定表高内部滚动：表头始终可见，横向滚动条贴在可见行下缘
            scroll={{ x: 3800, y: 'calc(100vh - 205px)' }}
            pagination={{ current: page, pageSize, total: records.length, showSizeChanger: true,
              showTotal: t => `共 ${t} 条`, onChange: (p, ps) => { setPage(p); setPageSize(ps) } }} />
        </div>
      </Card>

      <Modal title={editing ? '编辑记录' : '新建记录'} open={modalVisible && canOperate} onOk={canOperate ? handleSubmit : undefined}
        onCancel={() => setModalVisible(false)} width={960} okText="确认" cancelText="取消" destroyOnHidden style={{ top: 20 }}>
        <Form form={editing ? editForm : form} layout="vertical"
          initialValues={{ product_name: productName }}
          style={{ maxHeight: '70vh', overflow: 'auto', paddingRight: 8 }}>
          <Form.Item name="product_name" hidden><Input /></Form.Item>
          {formContent}
        </Form>
      </Modal>

      <Modal title="记录详情" open={detailVisible} onCancel={() => setDetailVisible(false)} footer={null} width={900}>
        {detailRecord && (
          <Descriptions column={3} bordered size="small">
            {LINCOMYCIN_FIELDS.map((f) => (
              <Descriptions.Item key={f.dataIndex} label={f.title}>
                {f.kind === 'person'
                  ? <PersonChips value={detailRecord[f.dataIndex as keyof SeedCultureRecord]} />
                  : f.kind === 'datetime'
                    ? (detailRecord[f.dataIndex as keyof SeedCultureRecord] ? dayjs(String(detailRecord[f.dataIndex as keyof SeedCultureRecord])).format('YYYY-MM-DD HH:mm') : '-')
                    : f.kind === 'date'
                      ? (detailRecord[f.dataIndex as keyof SeedCultureRecord] ? String(detailRecord[f.dataIndex as keyof SeedCultureRecord]).slice(0, 10) : '-')
                      : ((detailRecord[f.dataIndex as keyof SeedCultureRecord] as string | number | null) ?? '-')}
              </Descriptions.Item>
            ))}
            <Descriptions.Item label="创建时间">{dayjs(detailRecord.created_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
            <Descriptions.Item label="更新时间">{dayjs(detailRecord.updated_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
      </>
      )}
    </>
  )
}

export default function SeedCulturePage() {
  return (
    <div className="p-6">
      <Title level={4} style={{ marginTop: 0 }}>
        <ExperimentOutlined className="mr-2" />101一车间 — 菌种
      </Title>
      <Tabs
        items={PRODUCTS.map((p) => ({
          key: p.key,
          label: p.label,
          children: p.active ? (
            <SeedCultureLedger productName={p.productName!} label={p.label} />
          ) : (
            <Text type="secondary">{p.label} · 内容建设中（待产品表格配置）</Text>
          ),
        }))}
      />
    </div>
  )
}
