'use client'

import { useState } from 'react'
import {
  App,
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  Modal,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  createSafetyTargetAgreement,
  deleteSafetyTargetAgreement,
  downloadAgreementImportTemplate,
  getSafetyTargetAgreements,
  getSafetyTargetAgreementStats,
  importAgreementSigns,
  updateSafetyTargetAgreement,
  type SafetyTargetAgreementItem,
  type SafetyTargetAgreementStatsData,
} from '@/actions/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import PlatformNotice from '@/components/shared/PlatformNotice'
import TargetImportModal from './TargetImportModal'

const { Text, Title } = Typography

const T = {
  primary: '#5645d4',
  error: '#E03131',
  success: '#1AAE39',
  charcoal: '#37352f',
  slate: '#5d5b54',
  steel: '#787671',
  muted: '#bbb8b1',
  hairline: '#e5e3df',
  surface: '#f6f5f4',
  mint: '#d9f3e1',
  rose: '#fde0ec',
  sky: '#dcecfa',
}

const STATUS_META: Record<string, { label: string; color: string; bg: string }> = {
  unsigned: { label: '未签订', color: T.error, bg: T.rose },
  signed: { label: '已签订', color: T.success, bg: T.mint },
}

const CATEGORY_OPTIONS = ['公司领导', '部门/车间负责人', '岗位员工']

const CURRENT_YEAR = new Date().getFullYear()

interface AgreementFormValues {
  year: number
  department: string
  position: string
  category: string
  party_a?: string
  party_b?: string
  status: string
  signed_date?: string | null
  expires_date?: string | null
  goals_text?: string
  remark?: string
}

export default function TargetAgreementPanel({
  pageKey,
  initialAgreements,
  initialStats,
  initialError,
}: {
  pageKey: string
  initialAgreements: SafetyTargetAgreementItem[]
  initialStats: SafetyTargetAgreementStatsData | null
  initialError: string | null
}) {
  const { canOperate, canDelete } = usePagePermissions(pageKey)
  const { message } = App.useApp()
  const [agreements, setAgreements] =
    useState<SafetyTargetAgreementItem[]>(initialAgreements)
  const [total, setTotal] = useState(initialAgreements.length)
  const [stats, setStats] = useState<SafetyTargetAgreementStatsData | null>(initialStats)
  const [year, setYear] = useState<number>(CURRENT_YEAR)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(initialError)

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<SafetyTargetAgreementItem | null>(null)
  const [signing, setSigning] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [form] = Form.useForm<AgreementFormValues>()

  const refresh = async (
    nextYear = year,
    nextStatus = statusFilter,
    nextKeyword = keyword
  ) => {
    setLoading(true)
    try {
      const res = await getSafetyTargetAgreements({
        year: nextYear,
        status: nextStatus === 'all' ? undefined : nextStatus,
        keyword: nextKeyword || undefined,
        page_size: 200,
      })
      if (res.code === 200 && res.data) {
        setAgreements(res.data.items)
        setTotal(res.data.total)
        setError(null)
      } else {
        setError(res.message || '加载责任书失败')
      }
      const statsRes = await getSafetyTargetAgreementStats(nextYear)
      if (statsRes.code === 200) setStats(statsRes.data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载责任书失败')
    } finally {
      setLoading(false)
    }
  }

  const openCreate = () => {
    setEditing(null)
    setSigning(false)
    form.setFieldsValue({
      year: CURRENT_YEAR,
      department: '',
      position: '',
      category: '岗位员工',
      party_a: '',
      party_b: '',
      status: 'unsigned',
      signed_date: null,
      expires_date: null,
      goals_text: '',
      remark: '',
    })
    setFormOpen(true)
  }

  const openEdit = (item: SafetyTargetAgreementItem) => {
    setEditing(item)
    setSigning(false)
    form.setFieldsValue({ ...item })
    setFormOpen(true)
  }

  const openSign = (item: SafetyTargetAgreementItem) => {
    setEditing(item)
    setSigning(true)
    form.setFieldsValue({
      ...item,
      status: 'signed',
      signed_date: item.signed_date ?? new Date().toISOString().slice(0, 10),
      expires_date: item.expires_date ?? `${item.year}-12-31`,
    })
    setFormOpen(true)
  }

  const submitForm = async () => {
    const values = await form.validateFields()
    const payload = {
      year: values.year,
      department: values.department,
      position: values.position,
      category: values.category,
      party_a: values.party_a ?? '',
      party_b: values.party_b ?? '',
      status: values.status,
      signed_date: values.signed_date || null,
      expires_date: values.expires_date || null,
      goals_text: values.goals_text ?? '',
      remark: values.remark ?? '',
    }
    try {
      const res = editing
        ? await updateSafetyTargetAgreement(editing.id, payload)
        : await createSafetyTargetAgreement(payload)
      if (res.code === 200) {
        message.success(editing ? '责任书已更新' : '责任书已登记')
        setFormOpen(false)
        await refresh()
      } else {
        message.error(res.message || '保存失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const handleDelete = async (item: SafetyTargetAgreementItem) => {
    const res = await deleteSafetyTargetAgreement(item.id)
    if (res.code === 200) {
      message.success('责任书记录已删除')
      await refresh()
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const columns: ColumnsType<SafetyTargetAgreementItem> = [
    {
      title: '责任部门/单位',
      dataIndex: 'department',
      key: 'department',
      width: 170,
      render: (v: string, row) => (
        <div>
          <Text strong style={{ color: T.charcoal }}>{v}</Text>
          <div>
            <Text style={{ color: T.steel, fontSize: 12 }}>{row.position}</Text>
          </div>
        </div>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 130,
      render: (v: string) => (
        <Tag style={{ borderRadius: 6, border: 'none', backgroundColor: T.sky, color: T.primary, margin: 0 }}>
          {v}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: string) => {
        const meta = STATUS_META[v] || { label: v, color: T.steel, bg: T.surface }
        return (
          <Tag style={{ color: meta.color, backgroundColor: meta.bg, border: 'none', borderRadius: 6, fontWeight: 600 }}>
            {meta.label}
          </Tag>
        )
      },
    },
    {
      title: '甲方 / 乙方',
      key: 'parties',
      width: 160,
      render: (_, row) => (
        <Text style={{ color: T.steel, fontSize: 12 }}>
          {row.party_a || '-'}
          {row.party_b ? ` / ${row.party_b}` : ''}
        </Text>
      ),
    },
    {
      title: '签订日期 / 有效期至',
      key: 'dates',
      width: 170,
      render: (_, row) => (
        <Text style={{ color: T.steel, fontSize: 12 }}>
          {row.signed_date || '—'}
          {row.expires_date ? ` / ${row.expires_date}` : ''}
        </Text>
      ),
    },
    {
      title: '目标条款',
      dataIndex: 'goals_text',
      key: 'goals_text',
      ellipsis: true,
      render: (v: string) => (
        <Text style={{ color: T.slate, fontSize: 12 }}>
          {v ? v.split('\n').slice(0, 2).join('；') : '—'}
        </Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 170,
      render: (_, row) => (
        <Space size={4}>
          {row.status !== 'signed' && (
            <Button type="link" size="small" style={{ padding: 0 }} disabled={!canOperate} onClick={() => openSign(row)}>
              签订
            </Button>
          )}
          <Button type="link" size="small" style={{ padding: 0 }} disabled={!canOperate} onClick={() => openEdit(row)}>
            编辑
          </Button>
          <Popconfirm title="确定删除该责任书记录？" onConfirm={() => handleDelete(row)} disabled={!canDelete}>
            <Button type="link" size="small" danger style={{ padding: 0 }} disabled={!canDelete}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <Title level={5} className="!mb-1">安全目标责任书</Title>
          <Text style={{ color: T.slate, fontSize: 13 }}>
            按“谁主管、谁负责”逐级签订安全生产目标责任书，一年一签 · 已按 2026 责任书文档初始化台账
          </Text>
        </div>
        <Space>
          <Button disabled={!canOperate} onClick={() => setImportOpen(true)}>
            批量导入
          </Button>
          <Button type="primary" disabled={!canOperate} onClick={openCreate}>
            登记责任书
          </Button>
        </Space>
      </div>

      {stats && (
        <Card variant="borderless" size="small" style={{ borderRadius: 12, border: `1px solid ${T.hairline}` }}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: '应签总数', value: stats.total, color: T.primary },
              { label: '已签订', value: stats.signed, color: T.success },
              { label: '未签订', value: stats.unsigned, color: T.error },
              { label: '签订率', value: `${stats.sign_rate}%`, color: T.charcoal },
            ].map((item) => (
              <div key={item.label} className="rounded-lg p-3" style={{ backgroundColor: T.surface }}>
                <Text style={{ color: T.slate, fontSize: 12 }}>{item.label}</Text>
                <div className="text-2xl font-semibold" style={{ color: item.color }}>{item.value}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {error && (
        <PlatformNotice
          type="error"
          message="责任书台账加载失败"
          description={error}
          showRulesLink={false}
        />
      )}

      <Card variant="borderless" style={{ borderRadius: 12, border: `1px solid ${T.hairline}` }}>
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <Segmented
            value={year}
            onChange={(v) => {
              setYear(v as number)
              refresh(v as number, statusFilter, keyword)
            }}
            options={[CURRENT_YEAR - 1, CURRENT_YEAR, CURRENT_YEAR + 1]}
          />
          <Segmented
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter(v as string)
              refresh(year, v as string, keyword)
            }}
            options={[
              { label: '全部', value: 'all' },
              { label: '未签订', value: 'unsigned' },
              { label: '已签订', value: 'signed' },
            ]}
          />
          <Input.Search
            placeholder="搜索部门/岗位/签订人"
            allowClear
            style={{ maxWidth: 240 }}
            onSearch={(v) => {
              setKeyword(v)
              refresh(year, statusFilter, v)
            }}
          />
          <Text style={{ color: T.muted, fontSize: 12, marginLeft: 'auto' }}>共 {total} 条</Text>
        </div>
        <Table<SafetyTargetAgreementItem>
          rowKey="id"
          columns={columns}
          dataSource={agreements}
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          size="middle"
        />
      </Card>

      <Modal
        title={
          signing && editing
            ? `签订责任书 · ${editing.department} ${editing.position}`
            : editing
              ? '编辑责任书'
              : '登记责任书'
        }
        open={formOpen}
        onOk={submitForm}
        onCancel={() => setFormOpen(false)}
        width={680}
        destroyOnHidden
      >
        <Form<AgreementFormValues> form={form} layout="vertical" className="mt-3">
          <div className="grid grid-cols-3 gap-x-4">
            <Form.Item name="year" label="年度" rules={[{ required: true, message: '请填写年度' }]}>
              <Input type="number" />
            </Form.Item>
            <Form.Item name="department" label="责任部门/单位" rules={[{ required: true, message: '请填写部门' }]}>
              <Input placeholder="如 安全部 / 101一车间 / 公司领导" />
            </Form.Item>
            <Form.Item name="position" label="岗位/角色" rules={[{ required: true, message: '请填写岗位' }]}>
              <Input placeholder="如 负责人 / 安全管理科人员" />
            </Form.Item>
          </div>
          <div className="grid grid-cols-3 gap-x-4">
            <Form.Item name="category" label="分类" rules={[{ required: true }]}>
              <Select options={CATEGORY_OPTIONS.map((c) => ({ label: c, value: c }))} />
            </Form.Item>
            <Form.Item name="status" label="状态">
              <Select
                options={[
                  { label: '未签订', value: 'unsigned' },
                  { label: '已签订', value: 'signed' },
                ]}
              />
            </Form.Item>
            <Form.Item name="signed_date" label="签订日期">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <div className="grid grid-cols-3 gap-x-4">
            <Form.Item name="party_a" label="甲方（考核方）">
              <Input placeholder="公司/上级负责人" />
            </Form.Item>
            <Form.Item name="party_b" label="乙方（签订人）">
              <Input />
            </Form.Item>
            <Form.Item name="expires_date" label="有效期至">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Form.Item name="goals_text" label="安全生产目标条款（每行一条）">
            <Input.TextArea rows={5} placeholder="如：不发生B级及以上火灾爆炸事故" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <TargetImportModal
        title="批量导入责任书签订登记"
        open={importOpen}
        onClose={() => setImportOpen(false)}
        templateHint="下载模板后按行回填甲方/乙方与签订日期上传：台账里已有的部门/岗位会更新登记，没有的可直接在模板中追加新行"
        downloadLabel="下载签订登记模板"
        onDownload={downloadAgreementImportTemplate}
        onImport={async (file) => {
          const res = await importAgreementSigns(file)
          if (res.code === 200 && res.data) {
            const errors = res.data.errors ?? []
            const lines = [
              `更新登记 ${res.data.updated} 条，新增 ${res.data.created} 条`,
            ]
            for (const err of errors) {
              lines.push(`第 ${err.row} 行（${err.target}）失败：${err.message}`)
            }
            if (res.data.updated + res.data.created > 0) await refresh()
            return {
              ok: errors.length === 0,
              lines,
            }
          }
          return { ok: false, lines: [res.message || '导入失败'] }
        }}
      />
    </div>
  )
}
