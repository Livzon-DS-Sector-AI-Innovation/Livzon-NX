'use client'

import { useState } from 'react'
import Link from 'next/link'
import { App, Button, Card, Space, Table, Tag, Input, Select, Drawer, Descriptions, Popconfirm, Modal, Form, DatePicker, Row, Col } from 'antd'
import { ReloadOutlined, SearchOutlined, SyncOutlined, DeleteOutlined, EditOutlined, FileAddOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import type { ContractVM } from '@/lib/api/client/hr'
import { deleteContractAction, updateContractAction, renewContractAction, syncContractsFromFeishu, updateContractSignStatusAction } from '@/actions/hr'
import { usePermission } from '@/hooks/usePermission'

const CONTRACT_SEQUENCES = ['首次', '第二次', '第三次', '第四次', '第五次', '第六次']

interface ContractTableClientProps {
  initialData: ContractVM[]
  initialTotal: number
}

export default function ContractTableClient({ initialData, initialTotal }: ContractTableClientProps) {
  const { message } = App.useApp()
  // 编辑权限：仅人力资源部（hr:write）可编辑/删除/续签，其他部门只读
  const { has } = usePermission()
  const canEditHr = has('hr:write')
  const [data, setData] = useState<ContractVM[]>(initialData)
  const [total, setTotal] = useState(initialTotal)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [seqFilter, setSeqFilter] = useState<string | undefined>()
  const [detailOpen, setDetailOpen] = useState(false)
  const [selected, setSelected] = useState<ContractVM | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [editForm] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [renewOpen, setRenewOpen] = useState(false)
  const [renewForm] = Form.useForm()
  const [renewing, setRenewing] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: '1', page_size: '50' })
      if (keyword) params.set('keyword', keyword)
      if (seqFilter) params.set('contract_sequence', seqFilter)
      const res = await fetch(`/api/v1/hr/contracts?${params}`)
      const json = await res.json()
      setData(json.data?.data || [])
      setTotal(json.data?.total || 0)
    } finally { setLoading(false) }
  }

  const handleSyncFromFeishu = async () => {
    setSyncing(true)
    try {
      const json = await syncContractsFromFeishu()
      message.success(json.message || `同步完成: 新增 ${json.data?.created || 0} 条, 更新 ${json.data?.updated || 0} 条`)
      await load()
    } catch (e) {
      message.error('同步失败')
    } finally { setSyncing(false) }
  }

  // 手动同步，不在页面加载时自动触发写入

  const handleDelete = async (record: ContractVM) => {
    try {
      const json = await deleteContractAction(record.id)
      if (json.code === 200) {
        message.success('删除成功（已同步飞书多维表格）')
        await load()
      } else {
        message.error(json.message || '删除失败')
      }
    } catch (e) {
      message.error('删除失败')
    }
  }

  const handleEdit = (record: ContractVM) => {
    setSelected(record)
    editForm.setFieldsValue({
      contract_sequence: record.contract_sequence,
      dept_leader_name: record.dept_leader_name,
      contract_opinion: record.contract_opinion,
      // 日期字段：Date 类型用 dayjs，String 类型也尝试解析
      contract_start_1: record.contract_start_1 ? dayjs(record.contract_start_1) : null,
      contract_end_1: record.contract_end_1 ? dayjs(record.contract_end_1) : null,
      contract_start_2: record.contract_start_2 ? dayjs(record.contract_start_2) : null,
      contract_end_2: record.contract_end_2 || null,
      contract_start_3: record.contract_start_3 ? dayjs(record.contract_start_3) : null,
      contract_end_3: record.contract_end_3 || null,
      contract_start_4: record.contract_start_4 ? dayjs(record.contract_start_4) : null,
      contract_end_4: record.contract_end_4 || null,
      contract_start_5: record.contract_start_5 ? dayjs(record.contract_start_5) : null,
      contract_end_5: record.contract_end_5 || null,
      contract_start_6: record.contract_start_6 || null,
      contract_end_6: record.contract_end_6 || null,
    })
    setEditOpen(true)
  }

  const handleEditSave = async () => {
    try {
      const values = await editForm.validateFields()
      setSaving(true)
      // 转换日期字段
      const payload: Record<string, any> = {
        contract_sequence: values.contract_sequence,
        dept_leader_name: values.dept_leader_name,
        contract_opinion: values.contract_opinion,
      }
      // Date 类型字段转 ISO 字符串
      const dateFields = ['contract_start_1', 'contract_end_1', 'contract_start_2', 'contract_start_3', 'contract_start_4', 'contract_start_5']
      for (const f of dateFields) {
        if (values[f]) {
          payload[f] = dayjs.isDayjs(values[f]) ? values[f].format('YYYY-MM-DD') : values[f]
        }
      }
      // String 类型字段直接传
      const strFields = ['contract_end_2', 'contract_end_3', 'contract_end_4', 'contract_end_5', 'contract_start_6', 'contract_end_6']
      for (const f of strFields) {
        if (values[f]) {
          payload[f] = dayjs.isDayjs(values[f]) ? values[f].format('YYYY-MM-DD') : values[f]
        }
      }

      const json = await updateContractAction(selected!.id, payload)
      if (json.code === 200) {
        message.success('更新成功（已同步飞书多维表格）')
        setEditOpen(false)
        await load()
      } else {
        message.error(json.message || '更新失败')
      }
    } catch (e) {
      if ((typeof e === 'object' && e !== null && 'errorFields' in e)) return // 表单校验错误，不提示
      message.error('更新失败')
    } finally {
      setSaving(false)
    }
  }

  const handleSignStatus = async (record: ContractVM, signedStatus: '已签署' | '拒签') => {
    try {
      const json = await updateContractSignStatusAction(record.id, signedStatus)
      if (json.code === 200) {
        message.success(json.message || `已标记为${signedStatus}`)
        await load()
      } else {
        message.error(json.message || '标记失败')
      }
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '标记失败')
    }
  }

  const handleRenew = (record: ContractVM) => {
    setSelected(record)
    renewForm.resetFields()
    setRenewOpen(true)
  }

  const handleRenewSave = async () => {
    try {
      const values = await renewForm.validateFields()
      setRenewing(true)
      const startDate = values.start_date ? dayjs(values.start_date).format('YYYY-MM-DD') : ''
      const endDate = values.end_date ? dayjs(values.end_date).format('YYYY-MM-DD') : ''
      const json = await renewContractAction(selected!.id, startDate, endDate)
      if (json.code === 200) {
        message.success(json.message || '续签日期已保存并同步至员工档案')
        setRenewOpen(false)
        await load()
      } else {
        message.error(json.message || '续签失败')
      }
    } catch (e) {
      if ((typeof e === 'object' && e !== null && 'errorFields' in e)) return
      message.error('续签失败')
    } finally {
      setRenewing(false)
    }
  }

  const columns = [
    { title: '工号', dataIndex: 'employee_number', width: 100 },
    { title: '姓名', dataIndex: 'name', width: 80 },
    { title: '性别', dataIndex: 'gender', width: 60 },
    { title: '一级部门', dataIndex: 'dept_level1', width: 120 },
    { title: '二级部门', dataIndex: 'dept_level2', width: 100 },
    { title: '岗位', dataIndex: 'position', width: 100 },
    { title: '第几次合同', dataIndex: 'contract_sequence', width: 100,
      render: (v: string) => v ? <Tag color="blue">{v}</Tag> : '-' },
    { title: '合同截止日', dataIndex: 'contract_end_1', width: 120,
      render: (v: string) => v || '-' },
    { title: '签署状态', dataIndex: 'signed_status', width: 110,
      render: (v: string | null, record: ContractVM) => {
        if (v === '已签署') return <Tag color="green">已签署{record.signed_at ? ` ${dayjs(record.signed_at).format('MM-DD')}` : ''}</Tag>
        if (v === '拒签') return <Tag color="red">拒签</Tag>
        if (record.contract_opinion === '同意续签') return <Tag color="orange">待签署</Tag>
        return '-'
      }},
    { title: '操作', width: 260,
      render: (_: any, record: ContractVM) => {
        if (!canEditHr) {
          return (
            <Button size="small" onClick={() => { setSelected(record); setDetailOpen(true) }}>详情</Button>
          )
        }
        return (
        <Space>
          <Button size="small" onClick={() => { setSelected(record); setDetailOpen(true) }}>详情</Button>
          {record.contract_opinion === '同意续签' && (
            <Button size="small" type="primary" icon={<FileAddOutlined />} onClick={() => handleRenew(record)}>续签</Button>
          )}
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          {record.contract_opinion === '同意续签' && record.signed_status === '待签署' && (
            <>
              <Popconfirm title="确认标记为已签署？" onConfirm={() => handleSignStatus(record, '已签署')}>
                <Button size="small" type="primary">标记已签署</Button>
              </Popconfirm>
              <Popconfirm title="确认标记为拒签？" onConfirm={() => handleSignStatus(record, '拒签')}>
                <Button size="small" danger>标记拒签</Button>
              </Popconfirm>
            </>
          )}
          <Popconfirm title="确定删除该合同记录？将同步删除飞书多维表格数据" onConfirm={() => handleDelete(record)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
        )
      }},
  ]

  return (
    <div className="space-y-4">
      <Card title={<Space><span>合同管理</span><Tag color="blue">{total}</Tag><Link href="/hr/contracts/approval-results" className="text-[13px] text-[var(--color-primary)]">合同到期审批结果 →</Link></Space>} extra={
        <Space>
          <Input placeholder="姓名/工号" value={keyword} onChange={e => setKeyword(e.target.value)} style={{ width: 150 }} />
          <Select placeholder="合同次数" value={seqFilter} onChange={setSeqFilter} allowClear style={{ width: 120 }}
            options={CONTRACT_SEQUENCES.map(s => ({ value: s, label: s }))} />
          <Button icon={<SearchOutlined />} onClick={load}>搜索</Button>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>刷新</Button>
          <Button icon={<SyncOutlined />} loading={syncing} onClick={handleSyncFromFeishu}>
            同步飞书
          </Button>
        </Space>
      }>
        <Table rowKey="id" columns={columns} dataSource={data} loading={loading}
          pagination={{ pageSize: 50, total, showTotal: t => `共 ${t} 条` }}
          size="small" scroll={{ x: 1000 }} />
      </Card>

      <Drawer title="合同详情" open={detailOpen} onClose={() => setDetailOpen(false)} size="large">
        {selected && (
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="工号">{selected.employee_number}</Descriptions.Item>
            <Descriptions.Item label="姓名">{selected.name}</Descriptions.Item>
            <Descriptions.Item label="性别">{selected.gender || '-'}</Descriptions.Item>
            <Descriptions.Item label="一级部门">{selected.dept_level1 || '-'}</Descriptions.Item>
            <Descriptions.Item label="二级部门">{selected.dept_level2 || '-'}</Descriptions.Item>
            <Descriptions.Item label="岗位">{selected.position || '-'}</Descriptions.Item>
            <Descriptions.Item label="职级">{selected.job_level || '-'}</Descriptions.Item>
            <Descriptions.Item label="域账户">{selected.domain_account || '-'}</Descriptions.Item>
            <Descriptions.Item label="身份证号">{selected.id_card || '-'}</Descriptions.Item>
            <Descriptions.Item label="有效期截止">{selected.id_card_expiry || '-'}</Descriptions.Item>
            <Descriptions.Item label="档案编号">{selected.archive_number || '-'}</Descriptions.Item>
            <Descriptions.Item label="第几次合同">{selected.contract_sequence || '-'}</Descriptions.Item>
            <Descriptions.Item label="首次签订">{selected.contract_start_1 || '-'}</Descriptions.Item>
            <Descriptions.Item label="首次截止">{selected.contract_end_1 || '-'}</Descriptions.Item>
            <Descriptions.Item label="第二次签订">{selected.contract_start_2 || '-'}</Descriptions.Item>
            <Descriptions.Item label="第二次截止">{selected.contract_end_2 || '-'}</Descriptions.Item>
            <Descriptions.Item label="第三次签订">{selected.contract_start_3 || '-'}</Descriptions.Item>
            <Descriptions.Item label="第三次截止">{selected.contract_end_3 || '-'}</Descriptions.Item>
            <Descriptions.Item label="第四次签订">{selected.contract_start_4 || '-'}</Descriptions.Item>
            <Descriptions.Item label="第四次截止">{selected.contract_end_4 || '-'}</Descriptions.Item>
            <Descriptions.Item label="第五次签订">{selected.contract_start_5 || '-'}</Descriptions.Item>
            <Descriptions.Item label="第五次截止">{selected.contract_end_5 || '-'}</Descriptions.Item>
            <Descriptions.Item label="第六次签订">{selected.contract_start_6 || '-'}</Descriptions.Item>
            <Descriptions.Item label="第六次截止">{selected.contract_end_6 || '-'}</Descriptions.Item>
            <Descriptions.Item label="部门负责人">{selected.dept_leader_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="分管领导">{selected.supervisor_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="签署状态">{selected.signed_status || '-'}</Descriptions.Item>
            <Descriptions.Item label="合同意见">{selected.contract_opinion ? <Tag color={selected.contract_opinion === '同意续签' ? 'green' : 'red'}>{selected.contract_opinion}</Tag> : <Tag>待审批</Tag>}</Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>

      {/* 编辑合同 Modal */}
      <Modal
        title={`编辑合同 - ${selected?.name || ''}（${selected?.employee_number || ''}）`}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        width={800}
        footer={[
          <Button key="cancel" onClick={() => setEditOpen(false)}>取消</Button>,
          <Button key="save" type="primary" loading={saving} onClick={handleEditSave}>保存</Button>,
        ]}
      >
        <Form form={editForm} layout="vertical" size="small">
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="contract_sequence" label="第几次合同">
                <Select allowClear options={CONTRACT_SEQUENCES.map(s => ({ value: s, label: s }))} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="dept_leader_name" label="部门负责人">
                <Input />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="contract_opinion" label="合同意见">
                <Select allowClear options={[
                  { value: '同意续签', label: '同意续签' },
                  { value: '不同意续签', label: '不同意续签' },
                ]} />
              </Form.Item>
            </Col>
          </Row>

          <div style={{ margin: '8px 0 16px', fontWeight: 600, color: '#666' }}>合同日期（手动填写续签日期）</div>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="contract_start_1" label="首次签订日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_end_1" label="首次截止日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_start_2" label="第二次签订日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_end_2" label="第二次截止日期">
                <Input placeholder="如 2026-08-15" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_start_3" label="第三次签订日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_end_3" label="第三次截止日期">
                <Input placeholder="如 2026-08-15" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_start_4" label="第四次签订日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_end_4" label="第四次截止日期">
                <Input placeholder="如 2026-08-15" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_start_5" label="第五次签订日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_end_5" label="第五次截止日期">
                <Input placeholder="如 2026-08-15" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_start_6" label="第六次签订日期">
                <Input placeholder="如 2026-08-15" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_end_6" label="第六次截止日期">
                <Input placeholder="如 2026-08-15" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* 续签快捷弹窗 */}
      <Modal
        title={`填写续签日期 - ${selected?.name || ''}（${selected?.contract_sequence || ''}）`}
        open={renewOpen}
        onCancel={() => setRenewOpen(false)}
        width={480}
        footer={[
          <Button key="cancel" onClick={() => setRenewOpen(false)}>取消</Button>,
          <Button key="save" type="primary" loading={renewing} onClick={handleRenewSave}>保存并同步员工档案</Button>,
        ]}
      >
        <div style={{ marginBottom: 16, padding: '8px 12px', background: '#f6ffed', borderRadius: 6, border: '1px solid #b7eb8f', fontSize: 13 }}>
          当前合同次数：<b>{selected?.contract_sequence || '-'}</b>
          <br />
          填写本次续签的开始日期和截止日期，保存后自动写入合同管理表和员工档案表对应的合同字段，并同步飞书。
        </div>
        <Form form={renewForm} layout="vertical">
          <Form.Item name="start_date" label="续签开始日期" rules={[{ required: true, message: '请选择开始日期' }]}>
            <DatePicker style={{ width: '100%' }} placement="bottomLeft" getPopupContainer={(node) => node.parentNode as HTMLElement} />
          </Form.Item>
          <Form.Item name="end_date" label="续签截止日期" rules={[{ required: true, message: '请选择截止日期' }]}>
            <DatePicker style={{ width: '100%' }} placement="bottomLeft" getPopupContainer={(node) => node.parentNode as HTMLElement} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
