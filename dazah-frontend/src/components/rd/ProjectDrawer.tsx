'use client'

import { useState, useEffect } from 'react'
import { App, Drawer, Form, Input, Select, DatePicker, Button, } from 'antd'
import dayjs from 'dayjs'
import { useResearchStore } from '@/stores/rd'
import { ResearchProjectStage, ResearchProjectStatus } from '@/types/rd'
import { createResearchProject, updateResearchProject } from '@/actions/rd'

const { TextArea } = Input

const stageOptions: { label: string; value: ResearchProjectStage }[] = [
  { label: '立项', value: '立项' },
  { label: '研发中试', value: '研发中试' },
  { label: '验证', value: '验证' },
  { label: '注册', value: '注册' },
  { label: '商业化', value: '商业化' },
]

const statusOptions: { label: string; value: ResearchProjectStatus }[] = [
  { label: '进行中', value: '进行中' },
  { label: '已暂停', value: '已暂停' },
  { label: '已完成', value: '已完成' },
  { label: '已终止', value: '已终止' },
]

interface ProjectDrawerProps {
  onRefresh?: () => void
}

export function ProjectDrawer({ onRefresh }: ProjectDrawerProps) {
  const { message } = App.useApp()

  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const { drawerOpen, editingProject, closeDrawer } = useResearchStore()

  useEffect(() => {
    if (drawerOpen) {
      if (editingProject) {
        form.setFieldsValue({
          project_no: editingProject.project_no,
          name: editingProject.name,
          project_type: editingProject.project_type ?? undefined,
          stage: editingProject.stage,
          status: editingProject.status,
          leader: editingProject.leader ?? undefined,
          start_date: editingProject.start_date ? dayjs(editingProject.start_date) : undefined,
          end_date: editingProject.end_date ? dayjs(editingProject.end_date) : undefined,
          description: editingProject.description ?? undefined
        })
      } else {
        form.resetFields()
        form.setFieldsValue({ stage: '立项', status: '进行中' })
      }
    }
  }, [drawerOpen, editingProject, form])

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      const data = {
        ...values,
        start_date: values.start_date ? values.start_date.format('YYYY-MM-DD') : null,
        end_date: values.end_date ? values.end_date.format('YYYY-MM-DD') : null
      }
      if (editingProject) {
        await updateResearchProject(editingProject.id, data)
        message.success('更新成功')
      } else {
        await createResearchProject(data)
        message.success('创建成功')
      }
      closeDrawer()
      onRefresh?.()
    } catch (error: any) {
      if (error?.message) message.error(error.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Drawer
      title={editingProject ? '编辑研发项目' : '新建研发项目'}
      size={480}
      open={drawerOpen}
      onClose={closeDrawer}
      extra={
        <Button type="primary" onClick={handleSubmit} loading={submitting}>
          保存
        </Button>
      }
    >
      <Form form={form} layout="vertical" autoComplete="off">
        <Form.Item name="project_no" label="项目编号" rules={[{ required: true, message: '请输入项目编号' }]}>
          <Input placeholder="请输入项目编号" />
        </Form.Item>
        <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
          <Input placeholder="请输入项目名称" />
        </Form.Item>
        <Form.Item name="project_type" label="项目类型">
          <Input placeholder="请输入项目类型" />
        </Form.Item>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <Form.Item name="stage" label="项目阶段">
            <Select options={stageOptions} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={statusOptions} />
          </Form.Item>
        </div>
        <Form.Item name="leader" label="负责人">
          <Input placeholder="请输入负责人" />
        </Form.Item>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <Form.Item name="start_date" label="开始日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="end_date" label="结束日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
        </div>
        <Form.Item name="description" label="描述">
          <TextArea rows={3} placeholder="请输入项目描述" />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
