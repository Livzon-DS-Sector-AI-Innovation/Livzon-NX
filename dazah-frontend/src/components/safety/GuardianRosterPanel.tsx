'use client'

/**
 * 作业安全监护人名单面板：车间人数卡片（点选过滤）+ 筛选列表 +
 * 新建/编辑 + Excel 导入（整表替换）+ Excel 导出。
 * 交互参照 WorkCertificatePanel；名单以最新一次导入为准。
 */

import {
  GUARDIAN_ROSTER_PAGE_KEY,
} from '@/lib/work-permit-api'

import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  Card,
  DatePicker,
  Drawer,
  Form,
  Input,
  message,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
} from 'antd'
import dayjs from 'dayjs'
import { DownloadOutlined, ImportOutlined, PlusOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import GuardianRosterImportModal from '@/components/safety/GuardianRosterImportModal'

import {
  createGuardianRoster,
  deleteGuardianRoster,
  exportGuardianRoster,
  getGuardianRoster,
  updateGuardianRoster,
} from '@/actions/safety'
import type { GuardianCreateInput } from '@/actions/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'

type GuardianRow = {
  id: string
  person_name: string
  workshop: string
  phone: string | null
  position: string | null
  score: number | null
  exam_name: string | null
  exam_date: string | null
  remark: string | null
  source_file: string | null
}

type WorkshopCount = { workshop: string; count: number }

type ListShape = {
  items: GuardianRow[]
  total: number
  workshops?: WorkshopCount[]
}

const XLSX_MIME =
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

export function GuardianRosterPanel({
  initialList,
  initialError,
}: {
  initialList: ListShape | null
  initialError: string | null
}) {
  const permissions = usePagePermissions(GUARDIAN_ROSTER_PAGE_KEY)
  const [items, setItems] = useState<GuardianRow[]>(initialList?.items ?? [])
  const [total, setTotal] = useState(initialList?.total ?? 0)
  const [workshops, setWorkshops] = useState<WorkshopCount[]>(
    initialList?.workshops ?? []
  )
  const [error, setError] = useState<string | null>(initialError)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [workshop, setWorkshop] = useState<string | null>(null)
  const [keyword, setKeyword] = useState<string | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<GuardianRow | null>(null)
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)

  const load = useCallback(
    async (
      targetPage = page,
      overrides?: {
        workshop?: string | null
        keyword?: string | null
      }
    ) => {
      // 筛选按钮先 setState 再 load：state 尚未生效，必须用显式覆盖值
      const effWorkshop =
        overrides?.workshop !== undefined ? overrides.workshop : workshop
      const effKeyword =
        overrides?.keyword !== undefined ? overrides.keyword : keyword
      setLoading(true)
      const res = await getGuardianRoster({
        pageKey: GUARDIAN_ROSTER_PAGE_KEY,
        page: targetPage,
        workshop: effWorkshop,
        keyword: effKeyword,
      })
      if (res.code === 200 && res.data) {
        setItems(res.data.items as never)
        setTotal(res.data.total)
        setWorkshops((res.data.workshops ?? []) as never)
        setError(null)
      } else {
        setError(res.message ?? '加载失败')
      }
      setLoading(false)
    },
    [page, workshop, keyword]
  )

  useEffect(() => {
    if (!initialList) {
      const timer = setTimeout(() => void load(1), 0)
      return () => clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const downloadBase64 = (base64: string, filename: string, mimeType: string) => {
    const byteCharacters = atob(base64)
    const byteNumbers = new Array(byteCharacters.length)
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i)
    }
    const blob = new Blob([new Uint8Array(byteNumbers)], { type: mimeType })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  }

  const handleExport = useCallback(async () => {
    setExporting(true)
    try {
      const response = await exportGuardianRoster(
        { workshop, keyword },
        GUARDIAN_ROSTER_PAGE_KEY
      )
      if (response.code !== 200 && response.code !== 0) {
        message.error(response.message ?? '导出失败')
        return
      }
      downloadBase64(response.data ?? '', `监护人名单.xlsx`, XLSX_MIME)
      message.success('导出成功')
    } finally {
      setExporting(false)
    }
  }, [workshop, keyword])

  const openCreate = useCallback(() => {
    setEditing(null)
    form.resetFields()
    setEditorOpen(true)
  }, [form])

  const openEdit = useCallback(
    (record: GuardianRow) => {
      setEditing(record)
      form.setFieldsValue({
        person_name: record.person_name,
        workshop: record.workshop,
        phone: record.phone,
        position: record.position,
        score: record.score,
        exam_name: record.exam_name,
        exam_date: record.exam_date ? dayjs(record.exam_date) : null,
        remark: record.remark,
      })
      setEditorOpen(true)
    },
    [form]
  )

  const handleDelete = useCallback(
    async (record: GuardianRow) => {
      const response = await deleteGuardianRoster(
        record.id,
        GUARDIAN_ROSTER_PAGE_KEY
      )
      if (response.code !== 200) {
        message.error(response.message ?? '删除失败')
        return
      }
      message.success('已删除')
      await load(page)
    },
    [load, page]
  )

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields()
    const payload: GuardianCreateInput = {
      person_name: values.person_name,
      workshop: values.workshop,
      phone: values.phone ?? null,
      position: values.position ?? null,
      score: values.score ?? null,
      exam_name: values.exam_name ?? null,
      exam_date: values.exam_date ? values.exam_date.format('YYYY-MM-DD') : null,
      remark: values.remark ?? null,
    }
    setSaving(true)
    const response = editing
      ? await updateGuardianRoster(editing.id, payload, GUARDIAN_ROSTER_PAGE_KEY)
      : await createGuardianRoster(payload, GUARDIAN_ROSTER_PAGE_KEY)
    setSaving(false)
    if (response.code !== 200) {
      message.error(response.message ?? '保存失败')
      return
    }
    message.success(editing ? '监护人已更新' : '监护人已添加')
    setEditorOpen(false)
    await load(page)
  }, [form, editing, load, page])

  const workshopOptions = workshops.map((item) => ({
    value: item.workshop,
    label: `${item.workshop}（${item.count}）`,
  }))

  const columns: ColumnsType<GuardianRow> = [
    { title: '姓名', dataIndex: 'person_name', width: 110 },
    { title: '车间/部门', dataIndex: 'workshop', width: 140 },
    {
      title: '联系电话',
      dataIndex: 'phone',
      width: 130,
      render: (value: string | null) => value ?? '-',
    },
    {
      title: '岗位',
      dataIndex: 'position',
      width: 120,
      render: (value: string | null) => value ?? '-',
    },
    {
      title: '考试分数',
      dataIndex: 'score',
      width: 90,
      render: (value: number | null) =>
        value === null ? '-' : <Tag color={value >= 80 ? 'green' : 'orange'}>{value}</Tag>,
    },
    {
      title: '考试名称',
      dataIndex: 'exam_name',
      width: 130,
      render: (value: string | null) => value ?? '-',
    },
    {
      title: '考试日期',
      dataIndex: 'exam_date',
      width: 110,
      render: (value: string | null) => value ?? '-',
    },
    {
      title: '备注',
      dataIndex: 'remark',
      ellipsis: true,
      render: (value: string | null) => value ?? '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 110,
      render: (_, record) => (
        <Space size={8}>
          {permissions.canOperate && <a onClick={() => openEdit(record)}>编辑</a>}
          {permissions.canDelete && (
            <Popconfirm
              title={`确认删除监护人「${record.person_name}」？`}
              onConfirm={() => void handleDelete(record)}
            >
              <a style={{ color: '#ff4d4f' }}>删除</a>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card size="small">
        <Space wrap>
          <Button
            onClick={() => {
              setWorkshop(null)
              setPage(1)
              void load(1, { workshop: null })
            }}
            type={workshop === null ? 'primary' : 'default'}
          >
            全部车间：{workshops.reduce((sum, item) => sum + item.count, 0)}
          </Button>
          {workshops.map((item) => (
            <Button
              key={item.workshop}
              onClick={() => {
                setWorkshop(item.workshop)
                setPage(1)
                void load(1, { workshop: item.workshop })
              }}
              type={workshop === item.workshop ? 'primary' : 'default'}
            >
              {item.workshop}：{item.count}
            </Button>
          ))}
        </Space>
      </Card>
      <Card size="small">
        <Space wrap>
          <Select
            allowClear
            showSearch
            placeholder="按车间筛选"
            style={{ width: 200 }}
            value={workshop}
            options={workshopOptions}
            onChange={(value) => {
              setWorkshop(value ?? null)
              setPage(1)
              void load(1, { workshop: value ?? null })
            }}
          />
          <Input.Search
            allowClear
            placeholder="姓名/电话/岗位"
            style={{ width: 220 }}
            onSearch={(value) => {
              setKeyword(value || null)
              setPage(1)
              void load(1, { keyword: value || null })
            }}
          />
          <Button onClick={() => void load(page)}>刷新</Button>
          <Button
            icon={<DownloadOutlined />}
            loading={exporting}
            onClick={() => void handleExport()}
          >
            导出 Excel
          </Button>
          {permissions.canOperate && (
            <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>
              Excel 导入
            </Button>
          )}
          {permissions.canOperate && (
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建监护人
            </Button>
          )}
        </Space>
      </Card>
      {error && (
        <Card size="small">
          <Space direction="vertical" size={4}>
            <Button size="small" onClick={() => void load(page)}>
              重试
            </Button>
            <span style={{ color: '#faad14' }}>{error}</span>
          </Space>
        </Card>
      )}
      <Table
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          showSizeChanger: false,
          showTotal: (value) => `共 ${value} 人`,
          onChange: (next) => {
            setPage(next)
            void load(next)
          },
        }}
        scroll={{ x: 'max-content' }}
      />

      <GuardianRosterImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => void load(1)}
      />

      <Drawer
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        size={480}
        destroyOnHidden
        title={editing ? `编辑监护人：${editing.person_name}` : '新建监护人'}
        footer={
          <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button onClick={() => setEditorOpen(false)}>取消</Button>
            <Button type="primary" loading={saving} onClick={() => void handleSubmit()}>
              保存
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item label="姓名" name="person_name" rules={[{ required: true }]}>
            <Input placeholder="监护人姓名" />
          </Form.Item>
          <Form.Item label="车间/部门" name="workshop" rules={[{ required: true }]}>
            <Input placeholder="如 103车间 / 设备动力部" />
          </Form.Item>
          <Form.Item label="联系电话" name="phone">
            <Input placeholder="联系电话（选填）" />
          </Form.Item>
          <Form.Item label="岗位" name="position">
            <Input placeholder="岗位（选填）" />
          </Form.Item>
          <Space wrap>
            <Form.Item label="考试分数" name="score">
              <Input type="number" placeholder="分数" style={{ width: 140 }} />
            </Form.Item>
            <Form.Item label="考试日期" name="exam_date">
              <DatePicker style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Form.Item label="考试名称" name="exam_name">
            <Input placeholder="如 监护人考试（选填）" />
          </Form.Item>
          <Form.Item label="备注" name="remark">
            <Input.TextArea rows={2} placeholder="备注（选填）" />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  )
}
