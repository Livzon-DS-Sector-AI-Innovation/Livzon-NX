'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Table,
  Input,
  Select,
  Button,
  Space,
  Tag,
  App,
  Typography,
  Modal,
  Descriptions,
  Spin,
  Card,
  Row,
  Col,
  Statistic,
  DatePicker,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  SearchOutlined,
  ExportOutlined,
  DownloadOutlined,
  EditOutlined,
  ImportOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
  AlertOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import {
  getHazardIdentifications,
  getHazardFilterOptions,
  getHILedgerStats,
  exportHazardLedgerPdf,
} from '@/actions/safety'
import type {
  HazardFilterOptions,
  HazardIdentification,
  HazardLedgerStats,
  HazardPositionOption,
} from '@/types/safety'
import { RISK_LEVEL_OPTIONS } from '@/types/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import HazardLedgerEditDrawer from './HazardLedgerEditDrawer'
import HazardLedgerImportModal from './HazardLedgerImportModal'
import dayjs from 'dayjs'

const { Text } = Typography
const { RangePicker } = DatePicker

// 风险等级图标映射（四级用蓝色，与车间图例红/橙/黄/蓝一致）
const RISK_ICONS: Record<string, React.ReactNode> = {
  level_1: <SafetyCertificateOutlined style={{ color: '#f5222d' }} />,
  level_2: <WarningOutlined style={{ color: '#fa8c16' }} />,
  level_3: <AlertOutlined style={{ color: '#faad14' }} />,
  level_4: <InfoCircleOutlined style={{ color: '#1677ff' }} />,
}

// 风险等级卡片配置
const RISK_CARD_CONFIG: Record<string, { label: string; color: string; bgColor: string }> = {
  level_1: { label: '重大风险', color: '#f5222d', bgColor: '#fff1f0' },
  level_2: { label: '较大风险', color: '#fa8c16', bgColor: '#fff7e6' },
  level_3: { label: '一般风险', color: '#faad14', bgColor: '#fffbe6' },
  level_4: { label: '低风险', color: '#1677ff', bgColor: '#e6f4ff' },
}

export default function HazardLedgerPanel() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<HazardIdentification[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<HazardLedgerStats>({
    total: 0, level_1: 0, level_2: 0, level_3: 0, level_4: 0,
  })
  const [queryParams, setQueryParams] = useState({ page: 1, page_size: 20 })
  const [keyword, setKeyword] = useState('')
  const [department, setDepartment] = useState<string | undefined>()
  const [position, setPosition] = useState<string | undefined>()
  const [riskLevel, setRiskLevel] = useState<string | undefined>()
  const [dateRange, setDateRange] = useState<[string, string] | null>(null)
  const { message } = App.useApp()
  const { canImport, canOperate } = usePagePermissions()

  // ── 车间表格导入 Modal 状态 ──
  const [importModalOpen, setImportModalOpen] = useState(false)

  // ── 在线编辑 Drawer 状态 ──
  const [editingRecord, setEditingRecord] = useState<HazardIdentification | null>(null)

  // ── AI 导出 Modal 状态 ──
  const [exportModalOpen, setExportModalOpen] = useState(false)
  const [naturalQuery, setNaturalQuery] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportStep, setExportStep] = useState<string>('')

  // ── 展开行 key ──
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])

  // ── 部门/岗位下拉选项（取自已入账数据，导入后自动刷新） ──
  const [deptOptions, setDeptOptions] = useState<string[]>([])
  const [positionPairs, setPositionPairs] = useState<HazardPositionOption[]>([])

  const loadFilterOptions = async () => {
    try {
      const res = await getHazardFilterOptions()
      if (res.code === 200 && res.data) {
        const options = res.data as HazardFilterOptions
        setDeptOptions(options.departments || [])
        setPositionPairs(options.positions || [])
      }
    } catch {
      // non-critical
    }
  }

  useEffect(() => {
    queueMicrotask(loadFilterOptions)
  }, [])


  // 岗位选项随部门联动；未选部门时展示全部
  const positionOptions = (
    department ? positionPairs.filter((pair) => pair.department === department) : positionPairs
  )
    .map((pair) => pair.position)
    .filter((value, idx, arr) => arr.indexOf(value) === idx)

  const loadStats = async () => {
    try {
      const res = await getHILedgerStats({
        department,
        position,
        risk_level: riskLevel,
        date_from: dateRange?.[0],
        date_to: dateRange?.[1],
      })
      if (res.code === 200 && res.data) {
        setStats(res.data as HazardLedgerStats)
      }
    } catch {
      // non-critical
    }
  }

  const loadData = async () => {
    setLoading(true)
    try {
      const res = await getHazardIdentifications({
        ...queryParams,
        overall_status: 'completed',
        keyword: keyword || undefined,
        department,
        position,
        risk_level: riskLevel,
        date_from: dateRange?.[0],
        date_to: dateRange?.[1],
      })
      if (res.code === 200) {
        setData(res.data as HazardIdentification[])
        setTotal(res.meta?.total || 0)
      }
    } catch {
      message.error('加载台账失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    queueMicrotask(loadStats)
  }, [])

  useEffect(() => {
    queueMicrotask(loadData)
  }, [queryParams])

  const handleSearch = () => {
    setQueryParams({ page: 1, page_size: queryParams.page_size })
    loadData()
    loadStats()
  }

  const handleReset = () => {
    setKeyword('')
    setDepartment(undefined)
    setPosition(undefined)
    setRiskLevel(undefined)
    setDateRange(null)
    setQueryParams({ page: 1, page_size: 20 })
  }

  // ── base64 → Blob → 触发下载（客户端） ──
  const downloadBase64 = (base64: string, filename: string, mimeType: string) => {
    const byteCharacters = atob(base64)
    const byteNumbers = new Array(byteCharacters.length)
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i)
    }
    const byteArray = new Uint8Array(byteNumbers)
    const blob = new Blob([byteArray], { type: mimeType })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  }

  // ── 导出 PDF（AI 解析 → 筛选 → Excel标准化填表 → PDF）──
  const handleExportPdf = async () => {
    setExporting(true)
    setExportStep('AI 正在解析筛选条件…')
    try {
      const result = await exportHazardLedgerPdf({
        natural_query: naturalQuery.trim() || undefined,
      })
      setExportStep('下载中…')
      downloadBase64(
        result.data || '',
        `危险源辨识台账_${new Date().toISOString().slice(0, 10)}.pdf`,
        'application/pdf'
      )
      message.success('PDF 导出成功')
      setExportModalOpen(false)
    } catch {
      message.error('PDF 导出失败')
    } finally {
      setExporting(false)
      setExportStep('')
    }
  }

  // ── 关闭弹窗时重置状态 ──
  const handleCloseExportModal = () => {
    setExportModalOpen(false)
    setNaturalQuery('')
  }

  const getRiskTag = (level?: string, label?: string) => {
    if (!level) return '-'
    const opt = RISK_LEVEL_OPTIONS.find((o) => o.value === level)
    return <Tag color={opt?.color}>{label || level}</Tag>
  }

  const getControlLevelTag = (level?: string) => {
    if (!level) return '-'
    const colorMap: Record<string, string> = {
      '公司级': 'red',
      '部门级': 'orange',
      '班组级': 'blue',
    }
    return <Tag color={colorMap[level] || 'default'}>{level}</Tag>
  }

  // 列结构对齐车间 Excel《作业活动安全风险分级管控措施清单》表头：
  // 风险点（序号/类别/名称）| 危险源（作业步骤/危险源辨识）| 事故类型 | 时态 | 状态
  // | 安全风险等级评定（L/E/C/D/风险等级）| 风险管控措施（工程/管理/个体防护/应急）
  // | 管控主体（管控层级/责任单位/责任人员）| 检查频次
  // 表头分组配色：对齐车间 Excel 的黄/橙/绿/蓝/红分组色带，
  // 横向滚动时分组标签移出视野也能凭颜色分辨归属
  const GROUP_BG = {
    risk: '#FFF1B8', // 风险点 / 危险源 / 事故类型 / 时态 / 状态（黄）
    assess: '#FFD591', // 安全风险等级评定（橙）
    control: '#D9F7BE', // 风险管控措施（绿）
    owner: '#BAE7FF', // 管控主体（蓝）
    frequency: '#FFCCC7', // 检查频次（红）
  } as const

  const headerCell = (bg: string) => () => ({ style: { background: bg } })

  const textCol = (
    title: string,
    dataIndex: keyof HazardIdentification,
    width: number,
    options?: { wrap?: boolean; bg?: string }
  ) => ({
    title,
    dataIndex,
    key: dataIndex as string,
    width,
    ellipsis: !options?.wrap || undefined,
    render: (v?: string) => v || '-',
    ...(options?.wrap
      ? {
          onCell: () => ({
            style: { whiteSpace: 'normal' as const, wordBreak: 'break-all' as const },
          }),
        }
      : {}),
    ...(options?.bg ? { onHeaderCell: headerCell(options.bg) } : {}),
  })

  const numCol = (
    title: string,
    dataIndex: keyof HazardIdentification,
    bg?: string
  ) => ({
    title,
    dataIndex,
    key: dataIndex as string,
    width: 48,
    align: 'center' as const,
    render: (v?: number) => v ?? '-',
    ...(bg ? { onHeaderCell: headerCell(bg) } : {}),
  })

  const columns: ColumnsType<HazardIdentification> = [
    {
      title: '序号',
      key: 'row_no',
      width: 55,
      align: 'center',
      fixed: 'left',
      render: (_, __, idx) => (queryParams.page - 1) * queryParams.page_size + idx + 1,
    },
    { title: '部门', dataIndex: 'department', key: 'department', width: 95, ellipsis: true, fixed: 'left' },
    { title: '岗位', dataIndex: 'position', key: 'position', width: 95, ellipsis: true, fixed: 'left' },
    {
      title: '风险点',
      onHeaderCell: headerCell(GROUP_BG.risk),
      children: [
        textCol('类别', 'hazard_type', 95, { bg: GROUP_BG.risk }),
        textCol('名称', 'production_step', 150, { bg: GROUP_BG.risk }),
      ],
    },
    {
      title: '危险源',
      onHeaderCell: headerCell(GROUP_BG.risk),
      children: [
        textCol('作业步骤', 'specific_activity', 150, { wrap: true, bg: GROUP_BG.risk }),
        textCol('危险源辨识', 'unsafe_behavior', 210, { wrap: true, bg: GROUP_BG.risk }),
      ],
    },
    textCol('可能发生的事故类型及后果', 'possible_accident', 140, { wrap: true, bg: GROUP_BG.risk }),
    textCol('时态', 'tense', 70, { bg: GROUP_BG.risk }),
    textCol('状态', 'state', 70, { bg: GROUP_BG.risk }),
    {
      title: '安全风险等级评定',
      onHeaderCell: headerCell(GROUP_BG.assess),
      children: [
        numCol('可能性L', 'l_inherent', GROUP_BG.assess),
        numCol('暴露频次E', 'e_inherent', GROUP_BG.assess),
        numCol('严重性C', 'c_inherent', GROUP_BG.assess),
        numCol('危险度D', 'd_inherent', GROUP_BG.assess),
        {
          title: '风险等级',
          key: 'inherent_risk',
          width: 95,
          onHeaderCell: headerCell(GROUP_BG.assess),
          render: (_, r) => getRiskTag(r.inherent_risk_level, r.inherent_risk_label),
        },
      ],
    },
    {
      title: '风险管控措施',
      onHeaderCell: headerCell(GROUP_BG.control),
      children: [
        textCol('工程措施', 'existing_engineering_controls', 200, { wrap: true, bg: GROUP_BG.control }),
        textCol('管理措施', 'existing_management_controls', 200, { wrap: true, bg: GROUP_BG.control }),
        textCol('个体防护', 'existing_ppe', 150, { wrap: true, bg: GROUP_BG.control }),
        textCol('应急措施', 'existing_emergency_measures', 150, { wrap: true, bg: GROUP_BG.control }),
      ],
    },
    {
      title: '管控主体',
      onHeaderCell: headerCell(GROUP_BG.owner),
      children: [
        {
          title: '管控层级',
          dataIndex: 'control_level',
          key: 'control_level',
          width: 85,
          onHeaderCell: headerCell(GROUP_BG.owner),
          render: (v?: string) => getControlLevelTag(v),
        },
        textCol('责任单位', 'responsible_unit', 110, { wrap: true, bg: GROUP_BG.owner }),
        textCol('责任人员', 'responsible_person', 90, { bg: GROUP_BG.owner }),
      ],
    },
    textCol('检查频次', 'check_frequency', 90, { wrap: true, bg: GROUP_BG.frequency }),
    {
      title: '操作', key: 'action', width: 110, fixed: 'right',
      render: (_, r) => (
        <Space size={0}>
          <Button
            type="link" size="small"
            onClick={() => router.push(`/safety/hazard-identification/${r.id}`)}
          >
            查看
          </Button>
          {canOperate && (
            <Button
              type="link" size="small" icon={<EditOutlined />}
              onClick={() => setEditingRecord(r)}
            >
              编辑
            </Button>
          )}
        </Space>
      ),
    },
  ]

  // ── 展开行渲染 ──
  const expandedRowRender = (record: HazardIdentification) => {
    const lecRow = (label: string, l?: number, e?: number, c?: number, d?: number, level?: string, levelLabel?: string) => (
      <Descriptions
        size="small"
        column={6}
        colon={false}
        title={<Text strong style={{ fontSize: 13 }}>{label}</Text>}
        style={{ marginBottom: 0 }}
      >
        <Descriptions.Item label="L">{l ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="E">{e ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="C">{c ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="D">{d ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="等级" span={2}>
          {level ? getRiskTag(level, levelLabel) : '-'}
        </Descriptions.Item>
      </Descriptions>
    )

    return (
      <div style={{ padding: '12px 24px', background: '#fafafa', borderRadius: 8 }}>
        <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
          {(record.check_standard || record.is_major_hazard || record.equipment_facilities) && (
            <Descriptions size="small" column={3} colon={false} title={<Text strong style={{ fontSize: 13 }}>设备设施信息</Text>}>
              {record.equipment_facilities && (
                <Descriptions.Item label="设备设施">{record.equipment_facilities}</Descriptions.Item>
              )}
              {record.check_standard && (
                <Descriptions.Item label="检查标准" span={2}>{record.check_standard}</Descriptions.Item>
              )}
              {record.is_major_hazard && (
                <Descriptions.Item label="重要危险源">{record.is_major_hazard}</Descriptions.Item>
              )}
            </Descriptions>
          )}
          {lecRow('固有风险评价', record.l_inherent, record.e_inherent, record.c_inherent, record.d_inherent, record.inherent_risk_level, record.inherent_risk_label)}

          {(record.existing_engineering_controls || record.existing_management_controls || record.existing_ppe || record.existing_emergency_measures) && (
            <Descriptions size="small" column={2} colon={false} title={<Text strong style={{ fontSize: 13 }}>现有控制措施</Text>}>
              {record.existing_engineering_controls && (
                <Descriptions.Item label="工程控制">{record.existing_engineering_controls}</Descriptions.Item>
              )}
              {record.existing_management_controls && (
                <Descriptions.Item label="管理措施">{record.existing_management_controls}</Descriptions.Item>
              )}
              {record.existing_ppe && (
                <Descriptions.Item label="PPE">{record.existing_ppe}</Descriptions.Item>
              )}
              {record.existing_emergency_measures && (
                <Descriptions.Item label="应急措施">{record.existing_emergency_measures}</Descriptions.Item>
              )}
            </Descriptions>
          )}

          {lecRow('残余风险评价', record.l_residual, record.e_residual, record.c_residual, record.d_residual, record.residual_risk_level, record.residual_risk_label)}

          {record.recommendation_content && (
            <Descriptions size="small" column={2} colon={false} title={<Text strong style={{ fontSize: 13 }}>建议措施</Text>}>
              {record.recommendation_type && (
                <Descriptions.Item label="类型">{record.recommendation_type}</Descriptions.Item>
              )}
              {record.recommendation_priority && (
                <Descriptions.Item label="优先级">
                  <Tag>{record.recommendation_priority}</Tag>
                </Descriptions.Item>
              )}
              <Descriptions.Item label="内容" span={2}>{record.recommendation_content}</Descriptions.Item>
            </Descriptions>
          )}

          {lecRow('措施后风险评价', record.l_post, record.e_post, record.c_post, record.d_post, record.post_risk_level, record.post_risk_label)}
        </Space>
      </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        marginBottom: 24,
      }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 600, color: '#1a1a1a', margin: 0 }}>
            危险源辨识台账
          </h1>
          <p style={{ fontSize: 14, color: '#5d5b54', margin: '4px 0 0' }}>
            已完成危险源辨识记录的查询、统计与导出
          </p>
        </div>
        <Space>
          {canImport && (
            <Button icon={<ImportOutlined />} onClick={() => setImportModalOpen(true)}>
              导入车间表格
            </Button>
          )}
          <Button type="primary" icon={<ExportOutlined />} onClick={() => setExportModalOpen(true)}>
            导出 PDF
          </Button>
        </Space>
      </div>

      {/* Stat Cards */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={4}>
          <Card
            size="small"
            style={{ borderRadius: 12, border: '1px solid #e5e3df' }}
            styles={{ body: { padding: '16px 20px' } }}
          >
            <Statistic
              title="总记录数"
              value={stats.total}
              styles={{ content: { color: '#1677ff', fontSize: 24 } }}
            />
          </Card>
        </Col>
        {['level_1', 'level_2', 'level_3', 'level_4'].map((level) => {
          const cfg = RISK_CARD_CONFIG[level]
          const count = stats[level as keyof HazardLedgerStats] as number
          return (
            <Col xs={12} sm={5} key={level}>
              <Card
                size="small"
                style={{
                  borderRadius: 12,
                  border: `1px solid ${cfg.color}20`,
                  background: cfg.bgColor,
                }}
                styles={{ body: { padding: '16px 20px' } }}
              >
                <Statistic
                  title={cfg.label}
                  value={count}
                  prefix={RISK_ICONS[level]}
                  styles={{ content: { color: cfg.color, fontSize: 24 } }}
                />
              </Card>
            </Col>
          )
        })}
      </Row>

      {/* Filter Bar */}
      <div style={{
        background: '#f6f5f4', borderRadius: 12, border: '1px solid #e5e3df',
        padding: '16px 20px', marginBottom: 16,
      }}>
        <Space wrap>
          <Input
            placeholder="搜索编号/部门/岗位/作业"
            prefix={<SearchOutlined />}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 200 }}
            allowClear
          />
          <Select
            placeholder="部门"
            showSearch
            allowClear
            value={department}
            onChange={(v) => {
              setDepartment(v || undefined)
              // 切换部门后，若已选岗位不属于新部门则清空
              if (v && position && !positionPairs.some((p) => p.department === v && p.position === position)) {
                setPosition(undefined)
              }
            }}
            style={{ width: 150 }}
            options={deptOptions.map((d) => ({ value: d, label: d }))}
          />
          <Select
            placeholder="岗位"
            showSearch
            allowClear
            value={position}
            onChange={(v) => setPosition(v || undefined)}
            style={{ width: 150 }}
            options={positionOptions.map((p) => ({ value: p, label: p }))}
          />
          <Select
            placeholder="风险等级"
            allowClear
            value={riskLevel}
            onChange={(v) => setRiskLevel(v)}
            style={{ width: 120 }}
            options={RISK_LEVEL_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          />
          <RangePicker
            placeholder={['开始日期', '结束日期']}
            value={dateRange ? [dayjs(dateRange[0]), dayjs(dateRange[1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setDateRange([dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')])
              } else {
                setDateRange(null)
              }
            }}
            style={{ width: 240 }}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
            查询
          </Button>
          <Button icon={<ReloadOutlined />} onClick={handleReset}>
            重置
          </Button>
        </Space>
      </div>

      {/* Table */}
      <div style={{ borderRadius: 12, border: '1px solid #e5e3df', padding: 16, background: '#fff' }}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          scroll={{ x: 2600 }}
          size="small"
          expandable={{
            expandedRowRender,
            expandedRowKeys,
            onExpandedRowsChange: (keys) => setExpandedRowKeys(keys as string[]),
            rowExpandable: () => true,
          }}
          pagination={{
            current: queryParams.page,
            pageSize: queryParams.page_size,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (page, pageSize) => setQueryParams({ page, page_size: pageSize }),
          }}
        />
      </div>

      {/* ── 导出 PDF Modal（AI 解析→筛选→Excel标准化填表→PDF）── */}
      <Modal
        title={
          <span>
            <ExportOutlined style={{ marginRight: 8, color: '#5645D4' }} />
            导出 PDF
          </span>
        }
        open={exportModalOpen}
        onCancel={handleCloseExportModal}
        width={520}
        footer={[
          <Button key="cancel" onClick={handleCloseExportModal}>
            取消
          </Button>,
          <Button
            key="export"
            type="primary"
            icon={<DownloadOutlined />}
            loading={exporting}
            onClick={handleExportPdf}
          >
            导出 PDF
          </Button>,
        ]}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* 自然语言输入 */}
          <div>
            <Text strong style={{ display: 'block', marginBottom: 6 }}>
              用自然语言描述要导出哪些记录：
            </Text>
            <Input.TextArea
              placeholder={'例如：\n- "上月所有重大风险记录"\n- "合成岗位最近三个月的数据"\n- "生产部一级和二级风险的危险源"'}
              value={naturalQuery}
              onChange={(e) => setNaturalQuery(e.target.value)}
              rows={3}
            />
            <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
              留空则导出全部已完成记录；输入自然语言后点击「导出 PDF」，AI 将自动解析筛选条件并导出。
            </Text>
          </div>

          {/* 导出进度提示 */}
          {exporting && (
            <div style={{ textAlign: 'center', padding: 16 }}>
              <Spin description={exportStep || '正在导出…'} />
            </div>
          )}
        </div>
      </Modal>

      {/* ── 车间表格导入 Modal ── */}
      <HazardLedgerImportModal
        open={importModalOpen}
        onClose={() => setImportModalOpen(false)}
        onImported={() => {
          loadData()
          loadStats()
          loadFilterOptions()
        }}
      />

      {/* ── 在线编辑 Drawer ── */}
      {editingRecord && (
        <HazardLedgerEditDrawer
          key={`${editingRecord.id}-${editingRecord.updated_at}`}
          record={editingRecord}
          open
          onClose={() => setEditingRecord(null)}
          onSaved={() => {
            loadData()
            loadStats()
            loadFilterOptions()
          }}
        />
      )}
    </div>
  )
}
