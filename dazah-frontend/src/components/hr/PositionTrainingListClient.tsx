'use client'

import { useEffect, useState } from 'react'
import { Table, Button, Space, Modal, Form, Input, Select, App, Popconfirm, Upload } from 'antd'
import { PlusOutlined, UploadOutlined, DownloadOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { fetchPositionTrainingLists, fetchTrainingDepartments } from '@/lib/api/client/hr'
import {
  createPositionTrainingList,
  batchUpdatePositionTrainingListItems,
  importPositionTrainingLists,
  clearPositionTrainingListsByDept,
} from '@/actions/hr'
import type { PositionTrainingList, PositionTrainingListItem } from '@/types/hr'

interface ItemDisplay {
  key: string
  id: string
  listId: string
  department: string
  position: string
  level: string
  sort_order: number | null
  textbook_name: string | null
  textbook_code: string | null
  assessment_method: string | null
  remarks: string | null
}

export default function PositionTrainingListClient() {
  const { message } = App.useApp()
  const [items, setItems] = useState<ItemDisplay[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [department, setDepartment] = useState<string>('')
  const [filterPosition, setFilterPosition] = useState<string>('')
  const [currentListId, setCurrentListId] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<ItemDisplay | null>(null)
  const [importLoading, setImportLoading] = useState(false)
  const [clearLoading, setClearLoading] = useState(false)
  const [form] = Form.useForm()

  // 部门列表：数据驱动（培训模块所有有数据的部门）
  const [mergedAllDepts, setMergedAllDepts] = useState<string[]>([])

  // 首次加载时自动选中第一个部门
  useEffect(() => {
    if (mergedAllDepts.length > 0 && !department) {
      setDepartment(mergedAllDepts[0])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mergedAllDepts])

  const flattenItems = (lists: PositionTrainingList[]): ItemDisplay[] => {
    const result: ItemDisplay[] = []
    for (const list of lists) {
      for (const item of list.items || []) {
        result.push({
          key: item.id || `${list.id}_${Math.random()}`,
          id: item.id || '',
          listId: list.id,
          department: list.department || '',
          position: list.position || '',
          level: item.level,
          sort_order: item.sort_order ?? null,
          textbook_name: item.textbook_name ?? null,
          textbook_code: item.textbook_code ?? null,
          assessment_method: item.assessment_method ?? null,
          remarks: item.remarks ?? null,
        })
      }
    }
    return result
  }

  const loadData = async () => {
    if (!department) return
    setLoading(true)
    try {
      const result = await fetchPositionTrainingLists({
        department: department || undefined,
        page,
        page_size: pageSize,
      })
      const flat = flattenItems(result.data)
      setItems(flat)
      // total 用展平后的明细数量而非 API meta.total（后者是清单数）
      // 后端按清单分页，前端按明细展示，total 取明细实际数量
      setTotal(flat.length)
      if (result.data.length > 0) {
        setCurrentListId(result.data[0].id)
      } else {
        setCurrentListId(null)
      }
    } catch {
      message.error('加载岗位培训清单失败')
    } finally {
      setLoading(false)
    }
  }

  const loadDepartments = async () => {
    try {
      const depts = await fetchTrainingDepartments()
      setMergedAllDepts(depts)
    } catch {
      console.error('加载部门列表失败')
    }
  }

  useEffect(() => {
    queueMicrotask(loadDepartments)

  }, [])

  useEffect(() => {
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, department])

  // ─── CRUD ───

  const handleAdd = () => {
    setEditingItem(null)
    form.resetFields()
    form.setFieldsValue({ level: '岗位级' })
    setModalOpen(true)
  }

  const handleEdit = (item: ItemDisplay) => {
    setEditingItem(item)
    form.setFieldsValue({
      level: item.level,
      textbook_name: item.textbook_name,
      textbook_code: item.textbook_code,
      assessment_method: item.assessment_method,
      remarks: item.remarks,
    })
    setModalOpen(true)
  }

  const handleDelete = async (item: ItemDisplay) => {
    if (!item.listId) return
    try {
      const all = await fetchPositionTrainingLists({
        department: department || undefined,
        page: 1,
        page_size: 1,
      })
      if (all.data.length > 0) {
        const list = all.data[0]
        const updated = (list.items || [])
          .filter((i: PositionTrainingListItem) => i.id !== item.id)
          .map((i: PositionTrainingListItem) => ({
            level: i.level,
            sort_order: i.sort_order ?? undefined,
            textbook_name: i.textbook_name ?? undefined,
            textbook_code: i.textbook_code ?? undefined,
            assessment_method: i.assessment_method ?? undefined,
            remarks: i.remarks ?? undefined,
          }))
        await batchUpdatePositionTrainingListItems(list.id, updated)
        message.success('删除成功')
        loadData()
      }
    } catch {
      message.error('删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const newItem = {
        level: values.level,
        sort_order: undefined as number | undefined,
        textbook_name: values.textbook_name || undefined,
        textbook_code: values.textbook_code || undefined,
        assessment_method: values.assessment_method || undefined,
        remarks: values.remarks || undefined,
      }

      const all = await fetchPositionTrainingLists({
        department: department || undefined,
        page: 1,
        page_size: 1,
      })

      if (all.data.length > 0) {
        const list = all.data[0]
        const existingItems = (list.items || []).map((i: PositionTrainingListItem) => ({
          level: i.level,
          sort_order: i.sort_order ?? undefined,
          textbook_name: i.textbook_name ?? undefined,
          textbook_code: i.textbook_code ?? undefined,
          assessment_method: i.assessment_method ?? undefined,
          remarks: i.remarks ?? undefined,
        }))

        if (editingItem) {
          const idx = existingItems.findIndex(
            (i) => i.level === editingItem.level && i.textbook_name === editingItem.textbook_name,
          )
          if (idx >= 0) existingItems[idx] = newItem
        } else {
          existingItems.push(newItem)
        }

        await batchUpdatePositionTrainingListItems(list.id, existingItems)
        message.success(editingItem ? '更新成功' : '新增成功')
      } else {
        await createPositionTrainingList({
          department: department || '',
          position: '—',
          items: [{
            level: newItem.level,
            sort_order: newItem.sort_order,
            textbook_name: newItem.textbook_name,
            textbook_code: newItem.textbook_code,
            assessment_method: newItem.assessment_method,
            remarks: newItem.remarks,
          }],
        })
        message.success('已创建清单并添加明细')
        // 新部门首次入库后刷新部门列表
        loadDepartments()
      }

      setModalOpen(false)
      loadData()
    } catch {
      message.error('操作失败')
    }
  }

  // ─── 导入 ───

  const handleImport = async (file: File) => {
    setImportLoading(true)
    try {
      const result = await importPositionTrainingLists(file)
      const data = (result.data || {}) as { department?: string; imported?: number; skipped?: number }
      const importedDept = data.department
      const detail = `导入${data.imported || 0}条，跳过${data.skipped || 0}条重复`
      message.success(`${result.message || '导入成功'}（${detail}）`)
      loadDepartments()
      if (importedDept && importedDept !== department) {
        setDepartment(importedDept)
        setPage(1)
      } else {
        loadData()
      }
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '导入失败')
    } finally {
      setImportLoading(false)
    }
    return false
  }

  // ─── 导出 ───

  const handleExport = async () => {
    if (!currentListId) {
      message.warning('暂无数据可导出')
      return
    }
    try {
      const res = await fetch(`/api/v1/hr/position-training-lists/${currentListId}/export`, { cache: 'no-store' })
      if (!res.ok) throw new Error('导出失败')
      const blob = await res.blob()

      // 优先解析后端文件名（filename*=utf-8'' 编码）
      let filename = `${department}-${filterPosition || '岗位'}-岗位培训清单.docx`
      const disposition = res.headers.get('content-disposition') || ''
      const m = disposition.match(/filename\*=UTF-8''([^;]+)/i)
      if (m) filename = decodeURIComponent(m[1])

      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch {
      message.error('导出失败')
    }
  }

  // ─── 筛选后的数据 ───

  const filteredItems = filterPosition
    ? items.filter((i) => i.position === filterPosition)
    : items

  // ─── 表格列定义 ───

  const columns: ColumnsType<ItemDisplay> = [
    {
      title: '序号',
      key: 'index',
      width: 60,
      render: (_, __, index) => (page - 1) * pageSize + index + 1,
    },
    { title: '部门', dataIndex: 'department', key: 'department', width: 120 },
    { title: '岗位', dataIndex: 'position', key: 'position', width: 310 },
    { title: '培训教材名称', dataIndex: 'textbook_name', key: 'textbook_name', width: 200, ellipsis: true },
    { title: '编号', dataIndex: 'textbook_code', key: 'textbook_code', width: 160 },
    { title: '考核方式', dataIndex: 'assessment_method', key: 'assessment_method', width: 120 },
    { title: '备注', dataIndex: 'remarks', key: 'remarks', width: 100, ellipsis: true },
    { title: '级别', dataIndex: 'level', key: 'level', width: 80 },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_, record) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleEdit(record)}>编辑</Button>
          <Popconfirm title="确定删除吗？" onConfirm={() => handleDelete(record)}>
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      {/* 部门选择（2 行自适应按钮组） */}
      <div className="flex flex-wrap gap-2 max-h-[7.5rem] overflow-hidden">
        {mergedAllDepts.map((dept) => (
          <button
            key={dept}
            onClick={() => { setDepartment(dept); setPage(1) }}
            className={`
              px-4 py-2 rounded-md text-[15px] font-medium transition-all border truncate
              ${dept === department
                ? 'bg-blue-50 text-blue-600 border-blue-300 shadow-sm'
                : 'bg-white text-gray-600 border-gray-200 hover:border-blue-200 hover:text-blue-500 hover:bg-blue-50/50'
              }
            `}
          >
            {dept}
          </button>
        ))}
      </div>

      {/* Toolbar */}
      <div className="flex justify-between items-center gap-2">
        <Select
          allowClear
          placeholder="筛选岗位"
          style={{ width: 200 }}
          value={filterPosition || undefined}
          onChange={(val) => { setFilterPosition(val || ''); setPage(1) }}
          options={Array.from(
            new Set(items.map((i) => i.position).filter(Boolean)),
          ).map((p) => ({ label: p, value: p }))}
          disabled={!department}
        />
        <Space>
          <Upload
            accept=".docx,.doc"
            multiple
            showUploadList={false}
            beforeUpload={(file) => { handleImport(file); return false }}
            disabled={importLoading}
          >
            <Button icon={<UploadOutlined />} loading={importLoading}>
              {importLoading ? '导入中...' : '导入'}
            </Button>
          </Upload>
          <Button icon={<DownloadOutlined />} onClick={handleExport}>导出</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增明细</Button>
          <Popconfirm
            title={`确定清除 "${department}" 的所有岗位培训清单吗？`}
            description="此操作不可恢复，部门下全部清单和明细将被删除"
            onConfirm={async () => {
              setClearLoading(true)
              try {
                const result = await clearPositionTrainingListsByDept(department)
                message.success(result.message || '已清除')
                loadData()
              } catch (e) {
                message.error((e instanceof Error ? e.message : '') || '清除失败')
              } finally { setClearLoading(false) }
            }}
            okText="确认清除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button danger icon={<DeleteOutlined />} loading={clearLoading} disabled={!department}>
              一键清除
            </Button>
          </Popconfirm>
        </Space>
      </div>

      {/* Table */}
      <Table
        columns={columns}
        dataSource={filteredItems}
        rowKey="key"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total: filterPosition ? filteredItems.length : total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条${filterPosition ? '（岗位筛选）' : ''}`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
        locale={{ emptyText: department ? '该部门暂无岗位培训清单' : '请选择部门' }}
      />

      {/* Add / Edit Modal */}
      <Modal
        title={editingItem ? '编辑培训明细' : '新增培训明细'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        width={560}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" className="mt-4">
          <Form.Item name="level" label="级别" rules={[{ required: true, message: '请选择级别' }]}>
            <Select options={[
              { label: '部门级', value: '部门级' },
              { label: '岗位级', value: '岗位级' },
            ]} />
          </Form.Item>
          <Form.Item name="textbook_name" label="培训教材名称" rules={[{ required: true, message: '请输入教材名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="textbook_code" label="编号">
            <Input />
          </Form.Item>
          <Form.Item name="assessment_method" label="考核方式">
            <Input />
          </Form.Item>
          <Form.Item name="remarks" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
