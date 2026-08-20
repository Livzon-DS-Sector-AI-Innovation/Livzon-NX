'use client'
import { useState, useEffect } from 'react'
import {Table, Button, Space, Input, Modal, Form, Card, App, Row, Col} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { PlusOutlined, SearchOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import SyncSettingsButton from './SyncSettingsButton'
import BatchProfileButton from './BatchProfileButton'

export default function CeramicCrudTable({ api, columns, searchField, searchPlaceholder, formFields, syncTarget, syncProduct, scrollX = 1200, workshop = '203' }: any) {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm(); const [editForm] = Form.useForm()
  const [loading, setLoading] = useState(false); const [records, setRecords] = useState<any[]>([])
  const [visible, setVisible] = useState(false); const [editing, setEditing] = useState<any>(null)
  const [st, setSt] = useState(''); const [page, setPage] = useState(1); const [ps, setPs] = useState(20)

  const load = async () => { setLoading(true); try { const p: any = { page: 1, page_size: 200, workshop }; if (st) p[searchField] = st; const r = await api.list(p); if (r.code === 200) setRecords(r.data); else message.error('加载失败') } catch { message.error('加载失败') } finally { setLoading(false) } }
   
   
   
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  const openForm = (r?: any) => { setEditing(r || null); if (r) editForm.setFieldsValue(r); else form.resetFields(); setVisible(true) }
  const handleDelete = (id: string) => modal.confirm({ title: '确认删除', onOk: async () => { const r1 = await api.delete(id); if (r1.code === 200) { message.success('已删除'); load() } else message.error(r1.message || '删除失败') } })
  const handleSubmit = async () => { try { const vals = editing ? await editForm.validateFields() : await form.validateFields(); const data: Record<string, unknown> = {}; for (const [k, v] of Object.entries(vals)) { if (v instanceof dayjs) { data[k] = (v as dayjs.Dayjs).toISOString(); continue } data[k] = v ?? null } if (editing) { const r1 = await api.update(editing.id, data); if (r1.code === 200) { message.success('已更新'); setVisible(false); load() } else message.error(r1.message || '更新失败') } else { const r1 = await api.create(data); if (r1.code === 200) { message.success('已创建'); setVisible(false); form.resetFields(); load() } else message.error(r1.message || '创建失败') } } catch { message.error('请检查表单') } }

  const actionCol: ColumnsType<any> = [{ title: '操作', key: 'action', width: 160, fixed: 'right', render: (_: any, r: any) => (<Space size="small"><Button type="link" size="small" icon={<EditOutlined />} onClick={() => openForm(r)}>编辑</Button>
        <BatchProfileButton batchNo={r.batch_no || r.received_batch || r.membrane_no || r.equipment_no} /><Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r.id)}>删除</Button></Space>) }]

  return (
    <Card>
      <Row gutter={16} className="mb-4" align="middle">
        <Col span={6}><Input placeholder={searchPlaceholder} prefix={<SearchOutlined />} value={st} onChange={e => { setSt(e.target.value); if (!e.target.value) { setPage(1); load() } }} onPressEnter={() => { setPage(1); load() }} allowClear /></Col>
        <Col flex="auto" style={{ textAlign: 'right' }}><Button type="primary" icon={<PlusOutlined />} onClick={() => openForm()}>新建记录</Button></Col>
      </Row>
      <Table columns={[...columns, ...actionCol]} dataSource={records.slice((page - 1) * ps, page * ps)} rowKey="id" loading={loading} scroll={{ x: scrollX }}
        pagination={{ current: page, pageSize: ps, total: records.length, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`, onChange: (p: number, pz: number) => { setPage(p); setPs(pz) } }} />
      <Modal title={editing ? '编辑记录' : '新建记录'} open={visible} onOk={handleSubmit} onCancel={() => setVisible(false)} width={800} okText="确认" cancelText="取消" destroyOnHidden>
        <Form form={editing ? editForm : form} layout="vertical">{formFields}</Form>
      </Modal>
    </Card>
  )
}
