'use client'

import { Drawer, Form, Input, Select, DatePicker, Button, Space, App } from 'antd'
import { createRouteAction, updateRouteAction } from '@/actions/rd'
import { RouteCreate, RouteUpdate, RouteStatus, RouteDevelopment } from '@/types/rd'
import dayjs from 'dayjs'

interface RouteDrawerProps {
  open: boolean
  route: RouteDevelopment | null
  onClose: () => void
  onRefresh: () => void
}

export function RouteDrawer({ open, route, onClose, onRefresh }: RouteDrawerProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const isEditing = !!route

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      
      if (isEditing) {
        const updateData: RouteUpdate = {
          route_no: values.route_no,
          name: values.name,
          source: values.source,
          source_reference: values.source_reference,
          description: values.description,
          status: values.status,
        }
        const result = await updateRouteAction(route.id, updateData)
        if (result.error) {
          message.error(result.error)
          return
        }
        message.success('更新成功')
      } else {
        const createData: RouteCreate = {
          project_id: 'project-1',
          route_no: values.route_no,
          name: values.name,
          source: values.source,
          source_reference: values.source_reference,
          description: values.description,
        }
        const result = await createRouteAction(createData)
        if (result.error) {
          message.error(result.error)
          return
        }
        message.success('创建成功')
      }
      
      form.resetFields()
      onClose()
      onRefresh()
    } catch (error) {
      console.error('Form validation failed:', error)
    }
  }

  return (
    <Drawer
      title={isEditing ? '编辑路线' : '新建路线'}
      styles={{ wrapper: { width: 500 } }}
      open={open}
      onClose={() => {
        form.resetFields()
        onClose()
      }}
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={handleSubmit}>
            保存
          </Button>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={route ? {
          ...route,
          start_date: route.start_date ? dayjs(route.start_date) : undefined,
          end_date: route.end_date ? dayjs(route.end_date) : undefined,
        } : {
          status: 'planning',
          source: 'pdf',
        }}
      >
        <Form.Item
          name="route_no"
          label="路线编号"
          rules={[{ required: true, message: '请输入路线编号' }]}
        >
          <Input placeholder="如：RD-2026-001" />
        </Form.Item>

        <Form.Item
          name="name"
          label="路线名称"
          rules={[{ required: true, message: '请输入路线名称' }]}
        >
          <Input placeholder="如：Suzuki偶联法" />
        </Form.Item>

        <Form.Item
          name="source"
          label="来源类型"
          rules={[{ required: true }]}
        >
          <Select options={[
            { value: 'pdf', label: 'PDF文献' },
            { value: 'doi', label: 'DOI' },
            { value: 'pmid', label: 'PMID' },
            { value: 'manual', label: '手动输入' },
          ]} />
        </Form.Item>

        <Form.Item
          name="source_reference"
          label="来源引用"
        >
          <Input placeholder="DOI号、PMID或文献标题" />
        </Form.Item>

        <Form.Item
          name="description"
          label="描述"
        >
          <Input.TextArea rows={4} placeholder="路线描述" />
        </Form.Item>

        {isEditing && (
          <Form.Item
            name="status"
            label="状态"
          >
            <Select options={[
              { value: 'planning', label: '计划中' },
              { value: 'in_progress', label: '进行中' },
              { value: 'completed', label: '已完成' },
              { value: 'failed', label: '失败' },
            ]} />
          </Form.Item>
        )}
      </Form>
    </Drawer>
  )
}
