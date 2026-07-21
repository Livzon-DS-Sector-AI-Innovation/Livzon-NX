'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Button, DatePicker, Form, Input, Modal, Select } from 'antd'
import { PlusOutlined, ReloadOutlined, DownloadOutlined } from '@ant-design/icons'
import { CapaTable } from './CapaTable'
import { useCapaStore } from '@/stores/quality'
import { fetchFeishuCapas, fetchDepartmentContacts } from '@/lib/api/quality'
import { createFeishuCapa } from '@/actions/quality'
import type { DepartmentContact } from '@/types/quality'
import type { Dayjs } from 'dayjs'

interface CapaFormValues {
  CAPA编号: string
  启动日期?: Dayjs | null
  事件部门?: string
  涉及产品?: string
  CAPA简述?: string
  CAPA效果评估?: string
  关闭日期?: Dayjs | null
  QA质量员?: string
  QA质量员确认日期?: Dayjs | null
  CAPA状态?: string
}

export function CapaPage() {
  const { message } = App.useApp()
  const [createOpen, setCreateOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<CapaFormValues>()
  const [qaContacts, setQaContacts] = useState<DepartmentContact[]>([])
  const {
    setCapas,
    setTotal,
    setLoading,
    loading,
    page,
    pageSize,
    keyword,
    departmentFilter,
    productFilter,
    statusFilter,
    setKeyword,
    setDepartmentFilter,
    setProductFilter,
    setStatusFilter,
  } = useCapaStore()

  const qaOptions = useMemo(() =>
    qaContacts
      .filter(c => c.department === 'QA')
      .map(c => ({ label: c.name ?? '', value: c.name ?? '' })),
    [qaContacts],
  )

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const result = await fetchFeishuCapas({
        keyword: keyword || undefined,
        page,
        page_size: pageSize,
      })
      setCapas(result.items)
      setTotal(result.total)
    } catch (error) {
      console.warn('加载CAPA数据失败:', error)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, keyword, setCapas, setTotal, setLoading])

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    fetchDepartmentContacts().then(setQaContacts)
  }, [])

  const openCreate = useCallback(() => {
    form.resetFields()
    form.setFieldsValue({ CAPA状态: '进行中', QA质量员: '杨小芹' })
    setCreateOpen(true)
  }, [form])

  const handleCreate = useCallback(async () => {
    const values = await form.validateFields()
    const payload: Record<string, unknown> = {
      CAPA编号: values.CAPA编号,
      启动日期: values.启动日期 ? values.启动日期.format('YYYY-MM-DD') : null,
      事件部门: values.事件部门 || null,
      涉及产品: values.涉及产品 || null,
      CAPA简述: values.CAPA简述 || null,
      CAPA效果评估: values.CAPA效果评估 || null,
      关闭日期: values.关闭日期 ? values.关闭日期.format('YYYY-MM-DD') : null,
      QA质量员: values.QA质量员 || null,
      QA质量员确认日期: values.QA质量员确认日期 ? values.QA质量员确认日期.format('YYYY-MM-DD') : null,
      CAPA状态: values.CAPA状态 || '进行中',
    }
    try {
      setSaving(true)
      await createFeishuCapa(payload)
      message.success('CAPA创建成功')
      setCreateOpen(false)
      await loadData()
    } catch (error: any) {
      message.error(error?.message || '创建CAPA失败')
    } finally {
      setSaving(false)
    }
  }, [form, loadData, message])

  const handleExport = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (keyword) params.set('keyword', keyword)
      if (departmentFilter) params.set('department', departmentFilter)
      if (productFilter) params.set('product', productFilter)
      if (statusFilter) params.set('status', statusFilter)
      const qs = params.toString()
      const res = await fetch(`/api/v1/quality/feishu/capas/export${qs ? `?${qs}` : ''}`)
      if (!res.ok) throw new Error('导出失败')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `CAPA登记汇总表_${new Date().toISOString().slice(0, 10)}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch (err: any) {
      message.error(err.message || '导出失败')
    }
  }, [keyword, departmentFilter, productFilter, statusFilter, message])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>CAPA台账</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadData}>
            从飞书拉取
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleExport}>
            导出Word
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建CAPA
          </Button>
        </div>
      </div>
      <CapaTable loading={loading} onRefresh={loadData} />
      <Modal
        title="新建CAPA"
        open={createOpen}
        onOk={() => void handleCreate()}
        onCancel={() => setCreateOpen(false)}
        confirmLoading={saving}
        destroyOnHidden
        width={640}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="CAPA编号" label="CAPA编号" rules={[{ required: true, message: '请输入CAPA编号' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="启动日期" label="启动日期">
            <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item name="事件部门" label="事件部门">
            <Input />
          </Form.Item>
          <Form.Item name="涉及产品" label="涉及产品">
            <Input />
          </Form.Item>
          <Form.Item name="CAPA简述" label="CAPA简述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="CAPA效果评估" label="CAPA效果评估">
            <Input />
          </Form.Item>
          <Form.Item name="关闭日期" label="关闭日期">
            <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item name="QA质量员" label="QA质量员">
            <Select showSearch allowClear placeholder="选择QA质量员" options={qaOptions} />
          </Form.Item>
          <Form.Item name="QA质量员确认日期" label="QA质量员确认日期">
            <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item name="CAPA状态" label="CAPA状态">
            <Select
              options={[
                { value: '进行中', label: '进行中' },
                { value: '已完成', label: '已完成' },
                { value: '已关闭', label: '已关闭' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
