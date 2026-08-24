'use client'

import { useMemo, useState, useTransition } from 'react'
import { App, Button, Card, Form, Input, Modal, Popconfirm, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import { createInspectionContact, deleteInspectionContact, updateInspectionContact } from '@/actions/registration'
import type { InspectionContact, InspectionContactCreate, InspectionContactUpdate } from '@/types/registration'

interface InspectionContactsPageProps {
  contacts: InspectionContact[]
}

type FormMode = 'create' | 'edit'

export default function InspectionContactsPage({ contacts }: InspectionContactsPageProps) {
  const router = useRouter()
  const { message } = App.useApp()
  const [form] = Form.useForm<InspectionContactCreate>()
  const [keyword, setKeyword] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editing, setEditing] = useState<InspectionContact | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [mode, setMode] = useState<FormMode>('create')
  const [pending, startTransition] = useTransition()

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    if (!kw) return contacts
    return contacts.filter(c => c.agency_name?.toLowerCase().includes(kw) || c.test_item?.toLowerCase().includes(kw) || c.contact_name?.toLowerCase().includes(kw))
  }, [contacts, keyword])

  const selected = useMemo(() => filtered.find(c => c.id === selectedId) || null, [filtered, selectedId])

  const columns: ColumnsType<InspectionContact> = [
    { title: '检测项目', dataIndex: 'test_item', width: 220 },
    { title: '外检机构', dataIndex: 'agency_name', width: 180 },
    { title: '联系人', dataIndex: 'contact_name', width: 90 },
    { title: '联系电话', dataIndex: 'contact_phone', width: 160 },
    { title: '邮箱', dataIndex: 'contact_email', width: 220 },
    { title: '地址', dataIndex: 'address', width: 240 },
  ]

  function openCreate() { setMode('create'); setEditing(null); form.resetFields(); setModalOpen(true) }

  function openEdit() {
    if (!selected) { message.warning('请先选择一条记录'); return }
    setMode('edit'); setEditing(selected)
    form.setFieldsValue({ test_item: selected.test_item || undefined, agency_name: selected.agency_name || undefined, contact_name: selected.contact_name || undefined, contact_phone: selected.contact_phone || undefined, contact_email: selected.contact_email || undefined, address: selected.address || undefined })
    setModalOpen(true)
  }

  function handleDelete() {
    if (!selected) { message.warning('请先选择一条记录'); return }
    startTransition(async () => { try { await deleteInspectionContact(selected.id); message.success('已删除'); setSelectedId(null); router.refresh() } catch (e) { message.error(e instanceof Error ? e.message : '删除失败') } })
  }

  async function handleSubmit(values: InspectionContactCreate) {
    startTransition(async () => {
      try {
        if (mode === 'edit' && editing) { await updateInspectionContact(editing.id, values as InspectionContactUpdate); message.success('已更新') }
        else { await createInspectionContact(values); message.success('已新增') }
        setModalOpen(false); form.resetFields(); router.refresh()
      } catch (e) { message.error(e instanceof Error ? e.message : '保存失败') }
    })
  }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={3} style={{ marginBottom: 0 }}>外检联系</Typography.Title>
      <Card size="small" extra={<Space><Button icon={<PlusOutlined />} type="primary" onClick={openCreate}>新增</Button><Button icon={<EditOutlined />} disabled={!selected} onClick={openEdit}>编辑</Button><Popconfirm title="确认删除？" onConfirm={handleDelete} disabled={!selected}><Button danger icon={<DeleteOutlined />} disabled={!selected}>删除</Button></Popconfirm></Space>}>
        <Input allowClear placeholder="搜索检测项目、外检机构、联系人" value={keyword} onChange={e => setKeyword(e.target.value)} style={{ width: 320, marginBottom: 16 }} />
        <Table rowKey="id" size="middle" columns={columns} dataSource={filtered} pagination={false} scroll={{ x: 960 }}
          rowSelection={{ type: 'radio', selectedRowKeys: selectedId ? [selectedId] : [], onChange: keys => setSelectedId((keys[0] as string) || null) }} />
      </Card>
      <Modal destroyOnHidden confirmLoading={pending} open={modalOpen} title={mode === 'create' ? '新增外检联系' : '编辑'} okText="保存" cancelText="取消" onCancel={() => setModalOpen(false)} onOk={() => form.submit()}>
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="test_item" label="检测项目"><Input /></Form.Item>
          <Form.Item name="agency_name" label="外检机构"><Input /></Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="contact_name" label="联系人" style={{ flex: 1, marginBottom: 0 }}><Input /></Form.Item>
            <Form.Item name="contact_phone" label="联系电话" style={{ flex: 1, marginBottom: 0 }}><Input /></Form.Item>
          </div>
          <Form.Item name="contact_email" label="邮箱"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="address" label="地址"><Input /></Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
