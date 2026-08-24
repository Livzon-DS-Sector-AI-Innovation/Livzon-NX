'use client'

import { useEffect } from 'react'
import { App, Modal, Form, Input, Select, InputNumber } from 'antd'
import { Department, DepartmentCreateInput, DepartmentUpdateInput } from '@/types/hr'
import { createDepartment, updateDepartment } from '@/actions/hr'

interface DepartmentFormProps {
  open: boolean
  department: Department | null
  parentId?: string | null
  onClose: () => void
  onSuccess: () => void
  departments?: Department[]
}

export default function DepartmentForm({ open, department, parentId, onClose, onSuccess, departments = [] }: DepartmentFormProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const isEdit = !!department

  useEffect(() => {
    if (open) {
      if (department) {
        form.setFieldsValue({
          name: department.name,
          leader_name: department.leader_name,
          parent_id: department.parent_id,
          headcount: department.headcount,
          description: department.description,
          sort_order: department.sort_order,
        })
      } else {
        form.resetFields()
        form.setFieldsValue({
          sort_order: 0,
          headcount: undefined,
          parent_id: parentId || undefined,
        })
      }
    }
  }, [open, department, form, parentId])

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      // code 不再让用户填写，自动用 name
      // Ant Design Select allowClear 清空时返回 undefined，
      // JSON.stringify 会省略 undefined 属性，需转为 null 才能传给后端
      const payload = {
        ...values,
        code: values.name,
        parent_id: values.parent_id ?? null,
        headcount: values.headcount ?? null,
        description: values.description ?? null,
        leader_name: values.leader_name ?? null,
      }
      if (isEdit && department) {
        await updateDepartment(department.id, payload as DepartmentUpdateInput)
        message.success('部门更新成功')
      } else {
        await createDepartment(payload as DepartmentCreateInput)
        message.success('部门创建成功')
      }
      form.resetFields()
      onSuccess()
      onClose()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '操作失败')
    }
  }

  const getParentOptions = (): { label: string; value: string }[] => {
    const excludeIds = new Set<string>()
    if (department) {
      excludeIds.add(department.id)
      const addChildren = (parentId: string) => {
        departments
          .filter((d) => d.parent_id === parentId)
          .forEach((d) => {
            excludeIds.add(d.id)
            addChildren(d.id)
          })
      }
      addChildren(department.id)
    }
    return departments
      .filter((d) => !excludeIds.has(d.id))
      .map((d) => ({ label: d.name, value: d.id }))
  }

  return (
    <Modal
      title={isEdit ? '编辑部门' : '新增部门'}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      okText="保存"
      cancelText="取消"
      width={520}
    >
      <Form form={form} layout="vertical" className="mt-4">
        <Form.Item
          name="name"
          label="部门名称"
          rules={[{ required: true, message: '请输入部门名称' }, { max: 64, message: '最多64字符' }]}
        >
          <Input placeholder="请输入部门名称" />
        </Form.Item>

        <Form.Item name="leader_name" label="部门负责人">
          <Input placeholder="请输入部门负责人" />
        </Form.Item>

        <Form.Item name="parent_id" label="上级部门">
          <Select
            placeholder="请选择上级部门"
            allowClear
            options={getParentOptions()}
            showSearch
            filterOption={(input, option) =>
              (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </Form.Item>

        <Form.Item name="headcount" label="编制人数">
          <InputNumber min={0} placeholder="请输入编制人数（选填）" style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item name="description" label="部门描述">
          <Input.TextArea rows={2} placeholder="请输入部门描述" maxLength={256} showCount />
        </Form.Item>

        <Form.Item
          name="sort_order"
          label="排序顺序"
          tooltip="数字越小越靠前，默认为 0"
        >
          <Input type="number" placeholder="请输入排序顺序（选填）" />
        </Form.Item>
      </Form>
    </Modal>
  )
}
