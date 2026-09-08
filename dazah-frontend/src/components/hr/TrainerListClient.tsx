'use client'

import { useEffect, useState } from 'react'
import {
  Table, Button, Space, Modal, Form, Input, DatePicker, Select,
  Upload, App, Popconfirm,
} from 'antd'
import { PlusOutlined, ExportOutlined, ImportOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { fetchTrainers, fetchTrainingDepartments } from '@/lib/api/client/hr'
import { createTrainer, updateTrainer, deleteTrainer, importTrainers } from '@/actions/hr'
import type { Trainer, TrainerCreateInput } from '@/types/hr'
import dayjs from 'dayjs'
import { HR_DISPLAY_DATE_FORMAT } from '@/lib/dayjs-config'

export default function TrainerListClient() {
  const { message } = App.useApp()
  const [trainers, setTrainers] = useState<Trainer[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [deptFilter, setDeptFilter] = useState<string | undefined>()
  const [departments, setDepartments] = useState<string[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [editingTrainer, setEditingTrainer] = useState<Trainer | null>(null)
  const [importing, setImporting] = useState(false)
  const [form] = Form.useForm()

  // 加载部门列表（培训模块全量数据驱动部门）
  useEffect(() => {
    fetchTrainingDepartments()
      .then(setDepartments)
      .catch((e) => console.error('加载培训部门列表失败', e))
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const result = await fetchTrainers({
        keyword: keyword || undefined,
        department: deptFilter,
        page,
        page_size: pageSize,
      })
      setTrainers(result.data)
      setTotal(result.total)
    } catch (error) {
      message.error('加载培训师列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    queueMicrotask(loadData)
  }, [page, pageSize, keyword, deptFilter])

  const handleCreate = () => {
    setEditingTrainer(null)
    form.resetFields()
    setModalOpen(true)
  }

  const handleEdit = (trainer: Trainer) => {
    setEditingTrainer(trainer)
    form.setFieldsValue({
      name: trainer.name,
      // tags 模式以数组形态回填，提交时归一为单个字符串
      department: trainer.department ? [trainer.department] : [],
      position: trainer.position,
      approval_date:
        trainer.approval_date && dayjs(trainer.approval_date).isValid()
          ? dayjs(trainer.approval_date)
          : undefined,
      remarks: trainer.remarks,
    })
    setModalOpen(true)
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteTrainer(id)
      message.success('删除成功')
      loadData()
    } catch (error) {
      message.error('删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const department = Array.isArray(values.department)
        ? values.department[0]
        : values.department
      // 显式 null：后端按「显式出现的字段」应用，允许清空部门/岗位/批准时间/备注
      const data: TrainerCreateInput = {
        name: values.name,
        department: department ?? null,
        position: values.position ?? null,
        approval_date: values.approval_date
          ? values.approval_date.format('YYYY-MM-DD')
          : null,
        remarks: values.remarks ?? null,
      }

      if (editingTrainer) {
        await updateTrainer(editingTrainer.id, data)
        message.success('更新成功')
      } else {
        await createTrainer(data)
        message.success('创建成功')
      }
      setModalOpen(false)
      loadData()
      // 新建/编辑可能输入新部门（tags），刷新部门下拉
      fetchTrainingDepartments()
        .then(setDepartments)
        .catch((e) => console.error('刷新部门列表失败', e))
    } catch (error) {
      // 透传真实失败原因（如 403 权限、422 校验），不再笼统提示
      message.error((error instanceof Error ? error.message : '') || '操作失败')
    }
  }

  const handleExport = () => {
    const params = new URLSearchParams()
    if (deptFilter) params.set('department', deptFilter)
    window.open(`/api/v1/hr/trainers/export?${params}`, '_blank')
  }

  const handleImportChange = async (info: any) => {
    const file = info.file
    if (!file) return

    setImporting(true)
    try {
      const formData = new FormData()
      formData.append('file', file.originFileObj || file)
      const result = await importTrainers(formData)
      message.success(result.message || '导入成功')
      loadData()
      // 刷新部门列表
      fetchTrainingDepartments()
        .then(setDepartments)
        .catch((e) => console.error('刷新部门列表失败', e))
    } catch (error) {
      message.error((error instanceof Error ? error.message : '') || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  const columns: ColumnsType<Trainer> = [
    {
      title: '序号',
      key: 'index',
      width: 60,
      render: (_, __, index) => (page - 1) * pageSize + index + 1,
    },
    {
      title: '姓名',
      dataIndex: 'name',
      key: 'name',
      width: 100,
    },
    {
      title: '部门',
      dataIndex: 'department',
      key: 'department',
      width: 140,
    },
    {
      title: '岗位',
      dataIndex: 'position',
      key: 'position',
      width: 160,
    },
    {
      title: '批准时间',
      dataIndex: 'approval_date',
      key: 'approval_date',
      width: 120,
      render: (date: string) => (date ? dayjs(date).format(HR_DISPLAY_DATE_FORMAT) : '-'),
    },
    {
      title: '备注',
      dataIndex: 'remarks',
      key: 'remarks',
      ellipsis: true,
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm title="确定删除吗？" onConfirm={() => handleDelete(record.id)}>
            <Button type="link" size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      {/* 工具栏 */}
      <div className="flex flex-wrap items-center gap-3">
        <Input.Search
          placeholder="搜索培训师姓名"
          allowClear
          onSearch={(v) => setKeyword(v)}
          style={{ width: 240 }}
        />
        <Select
          placeholder="按部门筛选"
          allowClear
          value={deptFilter}
          onChange={(v) => {
            setDeptFilter(v)
            setPage(1)
          }}
          style={{ width: 180 }}
          options={departments.map((d) => ({ label: d, value: d }))}
        />
        <div className="flex-1" />
        <Space>
          <Upload
            accept=".docx,.xlsx,.xls"
            showUploadList={false}
            beforeUpload={() => false}
            onChange={handleImportChange}
          >
            <Button icon={<ImportOutlined />} loading={importing}>
              导入清单
            </Button>
          </Upload>
          <Button icon={<ExportOutlined />} onClick={handleExport}>
            导出清单
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新增培训师
          </Button>
        </Space>
      </div>

      {/* 表格 */}
      <Table
        columns={columns}
        dataSource={trainers}
        rowKey="id"
        loading={loading}
        scroll={{ x: 900 }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (p, ps) => {
            setPage(p)
            setPageSize(ps)
          },
        }}
      />

      {/* 新增/编辑弹窗 */}
      <Modal
        title={editingTrainer ? '编辑培训师' : '新增培训师'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="姓名"
            rules={[{ required: true, message: '请输入姓名' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="department" label="部门">
            <Select
              allowClear
              mode="tags"
              maxCount={1}
              placeholder="选择或输入部门"
              options={departments.map((d) => ({ label: d, value: d }))}
            />
          </Form.Item>
          <Form.Item name="position" label="岗位">
            <Input />
          </Form.Item>
          <Form.Item name="approval_date" label="批准时间">
            <DatePicker className="w-full" />
          </Form.Item>
          <Form.Item name="remarks" label="备注">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
