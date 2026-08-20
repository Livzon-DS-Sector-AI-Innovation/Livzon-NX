'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import {
  Table, Button, Space, Input, Select, AutoComplete, Modal, Form,
  Tag, Card, Typography, DatePicker, App, Descriptions,
  Row, Col, Radio,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  PlusOutlined, SearchOutlined, EditOutlined, DeleteOutlined,
  CheckSquareOutlined, CheckOutlined,
} from '@ant-design/icons'
import {
  getShiftHandovers, createShiftHandover,
  updateShiftHandover, deleteShiftHandover, confirmShiftHandover,
  getDistinctPositions,
} from '@/actions/shift-handover'
import type { ShiftHandoverRecord, ShiftHandoverCreate, ScheduleMode } from '@/types/shift-handover'
import {
  DEFAULT_POSITIONS, WORKSHOP_OPTIONS, SCHEDULE_MODES, getShiftOptions, SHIFT_LABELS,
} from '@/types/shift-handover'
import dayjs from 'dayjs'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input
const { RangePicker } = DatePicker
const BACKEND = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
const API = (p: string) => `${BACKEND}/api/v1/production${p}`
async function authFetch(url: string, options?: RequestInit) {
  const res = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...options?.headers } })
  return res.json()
}

function getScheduleLSKey(workshop: string) { return `workshop_schedule_${workshop}` }

// ─── 交接班须知 ───
const HANDOVER_NOTICE = (
  <div style={{ maxHeight: 360, overflow: 'auto', fontSize: 13, lineHeight: 1.9 }}>
    <Paragraph>
      企业的生产管理通常都存在两班倒、三班倒、四班三倒的情况，生产班组都会存在交接班，目的：
    </Paragraph>
    <ul>
      <li>确保生产工作的连续性</li>
      <li>确保生产管理各项绩效</li>
      <li>防止同样问题重复出现</li>
      <li>降低生产班组间的争执</li>
      <li>增强生产班组间的和谐</li>
      <li>确保生产要求贯彻有效</li>
    </ul>

    <Paragraph strong>第一：需要提醒接班班组注意的事项</Paragraph>
    <Paragraph type="secondary">
      ①交班班组在生产过程中遇到的问题，交接班过程中予以提醒。<br />
      ②交班班组在生产过程中出现的不稳定情况，告知接班班组多加关注。<br />
      ③未处理好的工作事项，在交接班过程中特别说明、写明，防止被错用或误用。
    </Paragraph>

    <Paragraph strong>第二：需传达给接班班组的要求事项</Paragraph>
    <Paragraph type="secondary">
      交班班组务必将领导或管理人员对生产班组的要求详细告知接班班组，必要时当面沟通交流，确保接班班组理解精准，执行正确到位。
    </Paragraph>

    <Paragraph strong>第三：需要接班班组帮助完成的事项</Paragraph>
    <Paragraph type="secondary">
      未完成的工作事项需在交接班过程中特别交接清楚，必要时与接班班组当面沟通协调，征得同意，确保有效完成。
    </Paragraph>

    <Paragraph strong>第四：告知生产过程中有变化的情况</Paragraph>
    <Paragraph type="secondary">
      包括：工艺技术标准变化、操作作业指导书变化、设备设施变化、物料使用变化、质量判定标准变化、安全生产变化。需在交接班过程中着重提醒。
    </Paragraph>

    <Paragraph strong>第五：与接班班组需要讨论的问题</Paragraph>
    <Paragraph type="secondary">
      交班班组遇到的问题一直找不到解决办法，需与接班班组共同探讨分析，需在交接班过程中说明写明。
    </Paragraph>

    <Paragraph strong>第六：需与接班班组讨论的改善课题</Paragraph>
    <Paragraph type="secondary">
      交班班组在管理过程中想到的改善思路，希望得到接班班组的建议或帮助，需在交接班过程中说明写明。
    </Paragraph>
  </div>
)

export default function HandoverPage() {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [records, setRecords] = useState<ShiftHandoverRecord[]>([])
  const [modalVisible, setModalVisible] = useState(false)
  const [editing, setEditing] = useState<ShiftHandoverRecord | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  // 筛选
  const [positionFilter, setPositionFilter] = useState<string | undefined>()
  const [workshopFilter, setWorkshopFilter] = useState<string | undefined>()
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null)
  const [positionOptions, setPositionOptions] = useState<string[]>(DEFAULT_POSITIONS)

  // 页面加载时从数据库拉取历史岗位
  useEffect(() => {
    getDistinctPositions().then(res => {
      if (res.code === 200 && res.data?.length) {
        const merged = [...new Set([...DEFAULT_POSITIONS, ...res.data])]
        setPositionOptions(merged)
      }
    }).catch(() => {})
  }, [])
  // 表单联动
  const [, setFormWorkshop] = useState<string>('')
  const [formScheduleMode, setFormScheduleMode] = useState<ScheduleMode>('4-3')
  // 须知弹窗
  const [noticeVisible, setNoticeVisible] = useState(false)
  const [noticeMode, setNoticeMode] = useState<'submit' | 'confirm'>('submit')
  const pendingFormData = useRef<Record<string, unknown> | null>(null)
  const [confirmRecordId, setConfirmRecordId] = useState<string | null>(null)
  const [countdown, setCountdown] = useState(3)
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // 详情
  const [detailVisible, setDetailVisible] = useState(false)
  const [detailRecord, setDetailRecord] = useState<ShiftHandoverRecord | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { page: 1, page_size: 200 }
      if (positionFilter) params.position = positionFilter
      if (workshopFilter) params.workshop = workshopFilter
      if (dateRange) {
        params.date_from = dateRange[0].format('YYYY-MM-DD')
        params.date_to = dateRange[1].format('YYYY-MM-DD')
      }
      const res = await getShiftHandovers(params)
      if (res.code === 200) setRecords(res.data)
      else message.error('加载失败')
    } catch { message.error('加载失败') }
    finally { setLoading(false) }
  }, [positionFilter, workshopFilter, dateRange, message])

  useEffect(() => { load() }, [load])

  // 飞书用户搜索
  const [userOptions, setUserOptions] = useState<{ value: string; label: string }[]>([])
  const searchUsers = async (kw: string) => {
    if (!kw) { setUserOptions([]); return }
    try {
      const res = await authFetch(API(`/shift-handovers/search-users?q=${encodeURIComponent(kw)}`))
      if (res.code === 200 && res.data) {
        setUserOptions(res.data.map((u: any) => ({ value: u.name, label: `${u.name}${u.department ? ' · ' + u.department : ''}` })))
      }
    } catch {}
  }

  const filtered = records
  const paginated = filtered.slice((page - 1) * pageSize, page * pageSize)

  const handleWorkshopChange = (w: string) => {
    setFormWorkshop(w)
    const saved = localStorage.getItem(getScheduleLSKey(w)) as ScheduleMode | null
    const mode = (saved && SCHEDULE_MODES.some(m => m.value === saved)) ? saved : '4-3'
    setFormScheduleMode(mode)
    form.setFieldsValue({ schedule_mode: mode, shift: undefined })
    editForm.setFieldsValue({ schedule_mode: mode, shift: undefined })
  }

  const handleAdd = () => {
    setEditing(null); form.resetFields()
    setFormWorkshop(''); setFormScheduleMode('4-3')
    // 先展示须知，确认后再弹出表单
    setNoticeMode('submit')
    setNoticeVisible(true)
  }

  const handleEdit = (r: ShiftHandoverRecord) => {
    setEditing(r)
    editForm.setFieldsValue({ ...r, handover_time: r.handover_time ? dayjs(r.handover_time) : null })
    setFormWorkshop(r.workshop)
    const saved = localStorage.getItem(getScheduleLSKey(r.workshop)) as ScheduleMode | null
    setFormScheduleMode((saved && SCHEDULE_MODES.some(m => m.value === saved)) ? saved : '4-3')
    setModalVisible(true)
  }

  const handleDelete = (id: string) => {
    modal.confirm({
      title: '确认删除', content: '确定删除此交接记录？',
      onOk: async () => {
        const res = await deleteShiftHandover(id)
        if (res.code === 200) { message.success('已删除'); load() }
        else message.error(res.message || '删除失败')
      },
    })
  }

  // 表单提交 → 直接保存
  const handleFormSubmit = async () => {
    try {
      const values = editing ? await editForm.validateFields() : await form.validateFields()
      localStorage.setItem(getScheduleLSKey(values.workshop as string), formScheduleMode)
      const data = {
        position: values.position as string,
        workshop: values.workshop as string,
        shift: values.shift as string,
        handover_time: (values.handover_time as dayjs.Dayjs)?.toISOString?.() || values.handover_time as string,
        handover_from: values.handover_from as string,
        handover_to: values.handover_to as string,
        production_status: (values.production_status as string) || null,
        equipment_status: (values.equipment_status as string) || null,
        equipment_inspection: (values.equipment_inspection as string) || null,
        tools_handover: (values.tools_handover as string) || null,
        fire_emergency: (values.fire_emergency as string) || null,
        ppe_status: (values.ppe_status as string) || null,
        remarks: (values.remarks as string) || null,
      }
      if (!positionOptions.includes(data.position as string)) {
        setPositionOptions(prev => [...prev, data.position as string])
      }
      if (editing) {
        const res = await updateShiftHandover(editing.id, data)
        if (res.code === 200) { message.success('已更新'); setModalVisible(false); load() }
        else message.error(res.message || '更新失败')
      } else {
        const res = await createShiftHandover(data as ShiftHandoverCreate)
        if (res.code === 200) { message.success('已创建，等待接班人确认'); setModalVisible(false); form.resetFields(); load() }
        else message.error(res.message || '创建失败')
      }
    } catch { message.error('请检查表单填写是否完整') }
  }

  // 须知确认 — 新建时弹出表单，确认时执行 API
  const handleNoticeConfirm = async () => {
    setNoticeVisible(false)
    if (noticeMode === 'submit') { setModalVisible(true); return }
    // 确认接班
    if (!confirmRecordId) return
    const res = await confirmShiftHandover(confirmRecordId)
    if (res.code === 200) { message.success('已确认接班'); load() }
    else message.error(res.message || '确认失败')
    setConfirmRecordId(null)
  }

  // 确认接班按钮
  const handleOpenConfirm = (id: string) => {
    setConfirmRecordId(id)
    setNoticeMode('confirm')
    setCountdown(3)
    setNoticeVisible(true)
    countdownRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          if (countdownRef.current) clearInterval(countdownRef.current)
          return 0
        }
        return prev - 1
      })
    }, 1000)
  }

  const handleNoticeCancel = () => {
    if (countdownRef.current) clearInterval(countdownRef.current)
    setNoticeVisible(false)
    setConfirmRecordId(null)
    pendingFormData.current = null
  }

  const shiftOptions = getShiftOptions(formScheduleMode)

  const columns: ColumnsType<ShiftHandoverRecord> = [
    { title: '车间', dataIndex: 'workshop', key: 'workshop', width: 100 },
    { title: '岗位', dataIndex: 'position', key: 'position', width: 110 },
    { title: '班次', dataIndex: 'shift', key: 'shift', width: 70,
      render: (v: string) => <Tag>{SHIFT_LABELS[v] || v}</Tag>,
    },
    { title: '交接时间', dataIndex: 'handover_time', key: 'handover_time', width: 150,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-',
    },
    { title: '交班人', dataIndex: 'handover_from', key: 'handover_from', width: 90 },
    { title: '接班人', dataIndex: 'handover_to', key: 'handover_to', width: 90 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => v === 'confirmed'
        ? <Tag color="success">已确认</Tag>
        : <Tag color="orange">待确认</Tag>,
    },
    { title: '备注', dataIndex: 'remarks', key: 'remarks', width: 140, ellipsis: true,
      render: (v: string|null) => v || '-',
    },
    {
      title: '操作', key: 'action', width: 220, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => { setDetailRecord(r); setDetailVisible(true) }}>详情</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>编辑</Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r.id)}>删除</Button>
          {r.status === 'pending' && (
            <Button type="link" size="small" icon={<CheckOutlined />} style={{ color: '#52c41a' }}
              onClick={() => handleOpenConfirm(r.id)}>确认接班</Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div className="p-6">
      <div className="mb-6">
        <Title level={4}><CheckSquareOutlined className="mr-2" />班组交接确认</Title>
        <Text type="secondary">班组交接事项确认、签核与归档</Text>
      </div>

      <Card
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新建交接记录</Button>}
      >
        <Row gutter={16} className="mb-4">
          <Col span={6}>
            <RangePicker style={{ width: '100%' }} value={dateRange}
              onChange={(v) => setDateRange(v as [dayjs.Dayjs, dayjs.Dayjs] | null)}
              placeholder={['开始日期', '结束日期']} />
          </Col>
          <Col span={4}>
            <Select placeholder="车间" allowClear value={workshopFilter} onChange={v => { setWorkshopFilter(v); setPage(1) }}
              style={{ width: '100%' }} options={WORKSHOP_OPTIONS.map(w => ({ value: w, label: w }))} showSearch />
          </Col>
          <Col span={4}>
            <Select placeholder="岗位" allowClear value={positionFilter} onChange={v => { setPositionFilter(v); setPage(1) }}
              style={{ width: '100%' }} options={positionOptions.map(p => ({ value: p, label: p }))} showSearch />
          </Col>
          <Col><Button type="primary" icon={<SearchOutlined />} onClick={() => { setPage(1); load() }}>查询</Button></Col>
        </Row>
        <Table columns={columns} dataSource={paginated} rowKey="id" loading={loading} scroll={{ x: 1150 }}
          pagination={{ current: page, pageSize, total: filtered.length, showSizeChanger: true, showQuickJumper: true,
            showTotal: (t: number) => `共 ${t} 条`, onChange: (p, ps) => { setPage(p); setPageSize(ps) } }} />
      </Card>

      {/* ─── 新建/编辑 ─── */}
      <Modal title={editing ? '编辑交接记录' : '新建交接记录'} open={modalVisible} onOk={handleFormSubmit}
        onCancel={() => setModalVisible(false)} width={780} okText="提交" cancelText="取消" destroyOnHidden>
        <Form form={editing ? editForm : form} layout="vertical">
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="workshop" label="车间" rules={[{ required: true }]}>
                <Select placeholder="选择车间" options={WORKSHOP_OPTIONS.map(w => ({ value: w, label: w }))}
                  onChange={handleWorkshopChange} showSearch />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="position" label="岗位" rules={[{ required: true }]}>
                <Select mode="tags" maxCount={1} placeholder="选择或输入岗位"
                  options={positionOptions.map(p => ({ value: p, label: p }))} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="handover_time" label="交接时间" rules={[{ required: true }]}>
                <DatePicker showTime style={{ width: '100%' }} format="YYYY-MM-DD HH:mm" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="schedule_mode" label="排班模式">
                <Radio.Group options={SCHEDULE_MODES} value={formScheduleMode}
                  onChange={e => { setFormScheduleMode(e.target.value); form.setFieldsValue({ shift: undefined }); editForm.setFieldsValue({ shift: undefined }) }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="shift" label="班次" rules={[{ required: true }]}>
                <Select placeholder="选择班次" options={shiftOptions} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="handover_from" label="交班人" rules={[{ required: true }]}><AutoComplete options={userOptions} onSearch={searchUsers} placeholder="搜索交班人" /></Form.Item></Col>
            <Col span={12}><Form.Item name="handover_to" label="接班人" rules={[{ required: true }]}><AutoComplete options={userOptions} onSearch={searchUsers} placeholder="搜索接班人" /></Form.Item></Col>
          </Row>
          <Form.Item name="production_status" label="生产工艺运行情况"><TextArea rows={2} placeholder="当前在产批次、工艺阶段、关键工艺参数等" /></Form.Item>
          <Form.Item name="equipment_status" label="设备运行情况"><TextArea rows={2} placeholder="主要设备运行状态、有无异常或故障" /></Form.Item>
          <Form.Item name="equipment_inspection" label="设备巡检情况"><TextArea rows={2} placeholder="本班次设备巡检结果、发现的问题" /></Form.Item>
          <Form.Item name="tools_handover" label="工、器具移交"><TextArea rows={2} placeholder="移交的工器具清单及状态" /></Form.Item>
          <Form.Item name="fire_emergency" label="消防、应急器材情况"><TextArea rows={2} placeholder="消防器材、应急设备是否完好、是否在有效期内" /></Form.Item>
          <Form.Item name="ppe_status" label="人员劳动防护用品穿戴"><TextArea rows={2} placeholder="劳动防护用品穿戴是否规范、有无缺失" /></Form.Item>
          <Form.Item name="remarks" label="备注"><TextArea rows={2} placeholder="其他需要记录或交接的内容" /></Form.Item>
        </Form>
      </Modal>

      {/* ─── 交接班须知 Modal ─── */}
      <Modal
        title="交接班须知"
        open={noticeVisible}
        onOk={handleNoticeConfirm}
        onCancel={handleNoticeCancel}
        width={680}
        okText={noticeMode === 'confirm' ? (countdown > 0 ? `请阅读须知 (${countdown}s)` : '确认接班') : '已知晓，确认提交'}
        cancelText="取消"
        okButtonProps={{ disabled: noticeMode === 'confirm' && countdown > 0 }}
      >
        {noticeMode === 'confirm' && (
          <Paragraph type="warning" style={{ fontSize: 13 }}>
            请仔细阅读以下交接班须知，{countdown}s 后可点击确认
          </Paragraph>
        )}
        {HANDOVER_NOTICE}
      </Modal>

      {/* ─── 详情 ─── */}
      <Modal title="交接记录详情" open={detailVisible} onCancel={() => setDetailVisible(false)} footer={null} width={680}>
        {detailRecord && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="车间">{detailRecord.workshop}</Descriptions.Item>
            <Descriptions.Item label="岗位">{detailRecord.position}</Descriptions.Item>
            <Descriptions.Item label="班次"><Tag>{SHIFT_LABELS[detailRecord.shift] || detailRecord.shift}</Tag></Descriptions.Item>
            <Descriptions.Item label="状态">{detailRecord.status === 'confirmed' ? <Tag color="success">已确认</Tag> : <Tag color="orange">待确认</Tag>}</Descriptions.Item>
            <Descriptions.Item label="交接时间">{dayjs(detailRecord.handover_time).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
            <Descriptions.Item label="交班人">{detailRecord.handover_from}</Descriptions.Item>
            <Descriptions.Item label="接班人">{detailRecord.handover_to}</Descriptions.Item>
            <Descriptions.Item label="确认时间">{detailRecord.confirmed_at ? dayjs(detailRecord.confirmed_at).format('YYYY-MM-DD HH:mm:ss') : '-'}</Descriptions.Item>
            <Descriptions.Item label="生产工艺运行情况" span={2}><div style={{ whiteSpace: 'pre-wrap' }}>{detailRecord.production_status || '-'}</div></Descriptions.Item>
            <Descriptions.Item label="设备运行情况" span={2}><div style={{ whiteSpace: 'pre-wrap' }}>{detailRecord.equipment_status || '-'}</div></Descriptions.Item>
            <Descriptions.Item label="设备巡检情况" span={2}><div style={{ whiteSpace: 'pre-wrap' }}>{detailRecord.equipment_inspection || '-'}</div></Descriptions.Item>
            <Descriptions.Item label="工、器具移交" span={2}><div style={{ whiteSpace: 'pre-wrap' }}>{detailRecord.tools_handover || '-'}</div></Descriptions.Item>
            <Descriptions.Item label="消防、应急器材情况" span={2}><div style={{ whiteSpace: 'pre-wrap' }}>{detailRecord.fire_emergency || '-'}</div></Descriptions.Item>
            <Descriptions.Item label="人员劳动防护用品穿戴" span={2}><div style={{ whiteSpace: 'pre-wrap' }}>{detailRecord.ppe_status || '-'}</div></Descriptions.Item>
            <Descriptions.Item label="备注" span={2}>{detailRecord.remarks || '-'}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{dayjs(detailRecord.created_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
            <Descriptions.Item label="更新时间">{dayjs(detailRecord.updated_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  )
}
