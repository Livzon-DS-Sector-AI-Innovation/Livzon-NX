'use client'

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PhoneOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import {
  createEmergencyCard,
  deleteEmergencyCard,
  getEmergencyCardStats,
  getEmergencyCards,
  reviewEmergencyCard,
  updateEmergencyCard,
  type EmergencyCardCreateInput,
  type EmergencyCardItem,
  type EmergencyCardListData,
  type EmergencyCardReviewData,
  type EmergencyCardStatsData,
  type EmergencyCardStep,
  type EmergencyCardUpdateInput,
} from '@/actions/safety'
import dayjs from 'dayjs'

const PAGE_SIZE = 20

const ACCIDENT_TYPE_OPTIONS = [
  '泄漏',
  '火灾',
  '爆炸',
  '容器爆炸',
  '粉尘爆炸',
  '中毒',
  '中毒窒息',
  '触电',
  '电气事故',
  '机械伤害',
  '受限空间',
  '高处作业',
  '物体打击',
  '灼烫',
  '淹溺',
  '中暑',
  '锅炉',
  '污水处理',
  '综合',
].map((value) => ({ value, label: value }))

const ACCIDENT_TYPE_COLORS: Record<string, string> = {
  泄漏: 'orange',
  火灾: 'red',
  爆炸: 'volcano',
  容器爆炸: 'volcano',
  粉尘爆炸: 'volcano',
  中毒: 'purple',
  中毒窒息: 'purple',
  触电: 'gold',
  电气事故: 'gold',
  机械伤害: 'blue',
  受限空间: 'cyan',
  高处作业: 'geekblue',
  物体打击: 'blue',
  灼烫: 'orange',
  淹溺: 'cyan',
  中暑: 'red',
  锅炉: 'default',
  污水处理: 'green',
  综合: 'default',
}

const SECTION_LABELS: Record<string, string> = {
  steps: '处置步骤',
  phones: '应急电话',
  risks: '主要风险',
  precautions: '注意事项',
}

const COMPLETENESS_STATUS: Record<
  string,
  { color: string; text: string }
> = {
  ok: { color: 'green', text: '已覆盖' },
  missing: { color: 'red', text: '缺失' },
  unclear: { color: 'orange', text: '不明确' },
}

interface EmergencyCardPanelProps {
  initialStats: EmergencyCardStatsData | null
  initialCards: EmergencyCardListData | null
  initialError: string | null
}

interface StepFormValue {
  order?: string
  step?: string
  action?: string
  person?: string
}

/** 步骤表格：与纸质处置卡的「序号/步骤/处置/负责人」一致 */
function CardStepsTable({ steps }: { steps: EmergencyCardStep[] }) {
  return (
    <Table<EmergencyCardStep>
      size="small"
      rowKey={(_, index) => String(index)}
      pagination={false}
      dataSource={steps}
      scroll={{ x: 560 }}
      columns={[
        {
          title: '序号',
          dataIndex: 'order',
          width: 56,
          render: (value: string | undefined, __, index) => value || index + 1,
        },
        { title: '步骤', dataIndex: 'step', width: 110 },
        {
          title: '处置',
          dataIndex: 'action',
          render: (value: string | undefined) => (
            <span style={{ whiteSpace: 'pre-line' }}>{value || '—'}</span>
          ),
        },
        { title: '负责人', dataIndex: 'person', width: 120 },
      ]}
    />
  )
}

function SectionBlock({
  title,
  content,
}: {
  title: ReactNode
  content: string
}) {
  if (!content?.trim()) return null
  return (
    <div style={{ marginBottom: 16 }}>
      <Typography.Title level={5} style={{ marginBottom: 8 }}>
        {title}
      </Typography.Title>
      <Typography.Paragraph style={{ whiteSpace: 'pre-line', marginBottom: 0 }}>
        {content}
      </Typography.Paragraph>
    </div>
  )
}

export default function EmergencyCardPanel({
  initialStats,
  initialCards,
  initialError,
}: EmergencyCardPanelProps) {
  const { canOperate, canDelete } = usePagePermissions()
  const [messageApi, messageContext] = message.useMessage()

  const [stats, setStats] = useState<EmergencyCardStatsData | null>(initialStats)
  const [cards, setCards] = useState<EmergencyCardListData | null>(initialCards)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(initialError)

  const [activeWorkshop, setActiveWorkshop] = useState<string>('')
  const [position, setPosition] = useState<string | undefined>(undefined)
  const [accidentType, setAccidentType] = useState<string | undefined>(undefined)
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)

  const [detailCard, setDetailCard] = useState<EmergencyCardItem | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingCard, setEditingCard] = useState<EmergencyCardItem | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()
  const [reviewCard, setReviewCard] = useState<EmergencyCardItem | null>(null)
  const [reviewLoading, setReviewLoading] = useState(false)
  const [reviewData, setReviewData] = useState<EmergencyCardReviewData | null>(
    null
  )
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)

  const positionOptions = useMemo(() => {
    if (!stats) return []
    const workshop =
      stats?.workshops?.find((item) => item.workshop === activeWorkshop) ??
      null
    return (workshop?.positions ?? []).map((name) => ({
      value: name,
      label: name,
    }))
  }, [stats, activeWorkshop])

  const loadCards = useCallback(
    async (targetPage: number) => {
      setLoading(true)
      setLoadError(null)
      const res = await getEmergencyCards({
        page: targetPage,
        page_size: PAGE_SIZE,
        workshop: activeWorkshop || undefined,
        position,
        accident_type: accidentType,
        keyword: keyword || undefined,
      })
      setLoading(false)
      if (res.code === 200 && res.data) {
        setCards(res.data)
        setPage(targetPage)
      } else {
        setLoadError(res.message || '读取应急处置卡失败，请稍后重试')
      }
    },
    [activeWorkshop, position, accidentType, keyword]
  )

  const loadStats = useCallback(async () => {
    const res = await getEmergencyCardStats()
    if (res.code === 200 && res.data) setStats(res.data)
  }, [])

  useEffect(() => {
    if (
      initialCards === null ||
      activeWorkshop !== '' ||
      position ||
      accidentType ||
      keyword
    ) {
      void loadCards(1)
    }
    // 初始数据由服务端注入，仅在筛选条件变化或无初始数据时重新拉取
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkshop, position, accidentType, keyword])

  const refreshAll = useCallback(async () => {
    await Promise.all([loadCards(page), loadStats()])
  }, [loadCards, loadStats, page])

  const openCreate = () => {
    setEditingCard(null)
    form.resetFields()
    form.setFieldsValue({ accident_type: '综合', steps: [] })
    setEditorOpen(true)
  }

  const openAiReview = async (card: EmergencyCardItem) => {
    setReviewCard(card)
    setReviewData(null)
    setReviewError(null)
    setReviewLoading(true)
    const res = await reviewEmergencyCard(card.id)
    setReviewLoading(false)
    if (res.code === 200 && res.data) {
      setReviewData(res.data)
    } else {
      setReviewError(res.message || 'AI 分析失败，请稍后重试')
    }
  }

  const applySuggestion = async (
    card: EmergencyCardItem,
    section: 'phones' | 'risks' | 'precautions',
    content: string
  ) => {
    const fieldMap = {
      phones: 'phones',
      risks: 'risks',
      precautions: 'precautions',
    } as const
    const field = fieldMap[section]
    const current = (card[field] ?? '').trim()
    const merged = current ? `${current}\n${content}` : content
    setApplying(true)
    const res = await updateEmergencyCard(card.id, { [field]: merged })
    setApplying(false)
    if (res.code === 200 && res.data) {
      messageApi.success(`建议已追加到「${SECTION_LABELS[section]}」`)
      if (detailCard?.id === card.id) setDetailCard(res.data)
      setReviewCard(res.data)
      await refreshAll()
    } else {
      messageApi.error(res.message || '采纳建议失败，请稍后重试')
    }
  }

  const openEdit = (card: EmergencyCardItem) => {
    setEditingCard(card)
    form.resetFields()
    form.setFieldsValue({
      workshop: card.workshop,
      position: card.position || undefined,
      title: card.title,
      subject: card.subject,
      accident_type: card.accident_type,
      phones: card.phones,
      risks: card.risks,
      precautions: card.precautions,
      steps: card.steps ?? [],
    })
    setEditorOpen(true)
  }

  const submitEditor = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      const steps: EmergencyCardStep[] = (values.steps ?? []).map(
        (step: StepFormValue) => ({
          order: step.order ?? '',
          step: step.step ?? '',
          action: step.action ?? '',
          person: step.person ?? '',
        })
      )
      const payload: EmergencyCardCreateInput = {
        workshop: values.workshop,
        position: values.position ?? '',
        title: values.title,
        subject: values.subject ?? '',
        accident_type: values.accident_type ?? '综合',
        steps,
        extras: editingCard?.extras ?? [],
        phones: values.phones ?? '',
        risks: values.risks ?? '',
        precautions: values.precautions ?? '',
        sort_order: editingCard?.sort_order ?? 0,
      }
      const res = editingCard
        ? await updateEmergencyCard(
            editingCard.id,
            payload as EmergencyCardUpdateInput
          )
        : await createEmergencyCard(payload)
      if (res.code === 200 && res.data) {
        messageApi.success(editingCard ? '应急处置卡已更新' : '应急处置卡已新增')
        setEditorOpen(false)
        setDetailCard(null)
        await refreshAll()
      } else {
        messageApi.error(res.message || '保存失败，请稍后重试')
      }
    } catch {
      // 表单校验失败由 Form 内联提示
    } finally {
      setSubmitting(false)
    }
  }

  const removeCard = async (card: EmergencyCardItem) => {
    const res = await deleteEmergencyCard(card.id)
    if (res.code === 200) {
      messageApi.success(`已删除「${card.title}」`)
      if (detailCard?.id === card.id) setDetailCard(null)
      await refreshAll()
    } else {
      messageApi.error(res.message || '删除失败，请稍后重试')
    }
  }

  const columns: ColumnsType<EmergencyCardItem> = [
    {
      title: '卡片名称',
      dataIndex: 'title',
      width: 340,
      ellipsis: true,
      render: (value: string, record) => (
        <Typography.Link onClick={() => setDetailCard(record)}>
          {value}
        </Typography.Link>
      ),
    },
    { title: '车间/部门', dataIndex: 'workshop', width: 120 },
    {
      title: '岗位',
      dataIndex: 'position',
      width: 90,
      render: (value: string) => value || '—',
    },
    {
      title: '事故类型',
      dataIndex: 'accident_type',
      width: 110,
      render: (value: string) => (
        <Tag color={ACCIDENT_TYPE_COLORS[value] ?? 'default'}>{value}</Tag>
      ),
    },
    {
      title: '处置步骤',
      width: 90,
      align: 'right',
      render: (_, record) => (record.steps ?? []).length,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 120,
      render: (value: string) =>
        value ? dayjs(value).format('YYYY-MM-DD') : '—',
    },
    {
      title: '操作',
      key: 'actions',
      width: canOperate ? 220 : 80,
      render: (_, record) => (
        <Space size={0}>
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => setDetailCard(record)}
          >
            查看
          </Button>
          {canOperate && (
            <Button
              type="link"
              size="small"
              icon={<ThunderboltOutlined />}
              onClick={() => void openAiReview(record)}
            >
              AI 分析
            </Button>
          )}
          {canOperate && (
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openEdit(record)}
            >
              编辑
            </Button>
          )}
          {canOperate && canDelete && (
            <Popconfirm
              title="删除应急处置卡"
              description={`确定删除「${record.title}」？删除后页面不再展示。`}
              okButtonProps={{ danger: true }}
              onConfirm={() => void removeCard(record)}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const tabItems = useMemo(() => {
    const tabs = [{ key: '', label: `全部${stats ? ` (${stats.total})` : ''}` }]
    for (const workshop of stats?.workshops ?? []) {
      tabs.push({
        key: workshop.workshop,
        label: `${workshop.workshop} (${workshop.total})`,
      })
    }
    return tabs
  }, [stats])

  return (
    <div>
      {messageContext}
      {loadError && (
        <PlatformNotice
          type="error"
          message="应急处置卡读取失败"
          description={loadError}
          showRulesLink={false}
          style={{ marginBottom: 16 }}
        />
      )}

      <Tabs
        activeKey={activeWorkshop}
        onChange={(key) => {
          setActiveWorkshop(key)
          setPosition(undefined)
        }}
        items={tabItems}
        size="small"
      />

      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="岗位"
          style={{ minWidth: 120 }}
          value={position}
          options={positionOptions}
          onChange={(value) => setPosition(value)}
          disabled={!activeWorkshop}
        />
        <Select
          allowClear
          placeholder="事故类型"
          style={{ minWidth: 120 }}
          value={accidentType}
          options={ACCIDENT_TYPE_OPTIONS}
          onChange={(value) => setAccidentType(value)}
        />
        <Input
          allowClear
          placeholder="搜索标题 / 步骤 / 电话"
          style={{ width: 220 }}
          prefix={<SearchOutlined />}
          value={keywordInput}
          onChange={(event) => setKeywordInput(event.target.value)}
          onPressEnter={() => setKeyword(keywordInput.trim())}
        />
        <Button
          icon={<SearchOutlined />}
          onClick={() => setKeyword(keywordInput.trim())}
        >
          搜索
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => void refreshAll()}>
          刷新
        </Button>
        {canOperate && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={openCreate}
          >
            新增处置卡
          </Button>
        )}
      </Space>

      <Table<EmergencyCardItem>
        rowKey="id"
        size="middle"
        loading={loading}
        columns={columns}
        dataSource={cards?.items ?? []}
        scroll={{ x: 900 }}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total: cards?.total ?? 0,
          showSizeChanger: false,
          showTotal: (total) => `共 ${total} 张处置卡`,
          onChange: (target) => void loadCards(target),
        }}
        locale={{
          emptyText: (
            <Empty
              description={
                loading ? '加载中…' : '没有符合条件的应急处置卡，请调整筛选条件'
              }
            />
          ),
        }}
      />

      <Drawer
        title={detailCard?.title}
        width={720}
        open={detailCard !== null}
        onClose={() => setDetailCard(null)}
        extra={
          detailCard && canOperate ? (
            <Space>
              <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(detailCard)}>
                编辑
              </Button>
              {canDelete && (
                <Popconfirm
                  title="删除应急处置卡"
                  description={`确定删除「${detailCard.title}」？`}
                  okButtonProps={{ danger: true }}
                  onConfirm={() => void removeCard(detailCard)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />}>
                    删除
                  </Button>
                </Popconfirm>
              )}
            </Space>
          ) : null
        }
      >
        {detailCard && (
          <div>
            <Space wrap size={4} style={{ marginBottom: 16 }}>
              <Tag>{detailCard.workshop}</Tag>
              {detailCard.position && <Tag color="blue">{detailCard.position}</Tag>}
              <Tag color={ACCIDENT_TYPE_COLORS[detailCard.accident_type] ?? 'default'}>
                {detailCard.accident_type}
              </Tag>
              {detailCard.subject && <Tag>{detailCard.subject}</Tag>}
            </Space>

            <CardStepsTable steps={detailCard.steps ?? []} />

            {detailCard.phones?.trim() && (
              <div
                style={{
                  marginTop: 16,
                  padding: '8px 12px',
                  border: '1px solid var(--color-border, #d9d9d9)',
                  borderRadius: 8,
                  background: 'var(--color-bg-secondary, #fafafa)',
                }}
              >
                <Typography.Text strong>
                  <PhoneOutlined /> 应急电话
                </Typography.Text>
                <Typography.Paragraph
                  style={{ whiteSpace: 'pre-line', marginBottom: 0, marginTop: 4 }}
                >
                  {detailCard.phones}
                </Typography.Paragraph>
              </div>
            )}

            <div style={{ marginTop: 16 }}>
              <SectionBlock
                title={
                  <span>
                    <WarningOutlined /> 主要导致风险及导致的后果
                  </span>
                }
                content={detailCard.risks}
              />
              <SectionBlock title="应急注意事项" content={detailCard.precautions} />
              {(detailCard.extras ?? []).map((extra, index) => (
                <SectionBlock
                  key={`${extra.label}-${index}`}
                  title={extra.label}
                  content={extra.content}
                />
              ))}
            </div>

            {detailCard.source_file && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                资料来源：{detailCard.source_file}
              </Typography.Text>
            )}
          </div>
        )}
      </Drawer>

      <Modal
        title={reviewCard ? `AI 分析 · ${reviewCard.title}` : 'AI 分析'}
        width={720}
        open={reviewCard !== null}
        onCancel={() => setReviewCard(null)}
        footer={
          <Button onClick={() => setReviewCard(null)}>关闭</Button>
        }
        destroyOnHidden
      >
        {reviewLoading && (
          <div style={{ textAlign: 'center', padding: '32px 0' }}>
            <Typography.Text type="secondary">
              正在调用模型分析处置卡内容，请稍候…
            </Typography.Text>
          </div>
        )}
        {!reviewLoading && reviewError && (
          <PlatformNotice
            type="warning"
            message="AI 分析未能完成"
            description={reviewError}
            showRulesLink={false}
          />
        )}
        {!reviewLoading && !reviewError && reviewData && reviewCard && (
          <div>
            {reviewData.summary && (
              <Typography.Paragraph strong style={{ marginBottom: 16 }}>
                {reviewData.summary}
              </Typography.Paragraph>
            )}
            {(reviewData.completeness ?? []).length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Typography.Title level={5} style={{ marginBottom: 8 }}>
                  完整性检查
                </Typography.Title>
                {(reviewData.completeness ?? []).map((item, index) => {
                  const status =
                    COMPLETENESS_STATUS[item.status] ?? COMPLETENESS_STATUS.unclear
                  return (
                    <div
                      key={`${item.item}-${index}`}
                      style={{ marginBottom: 6 }}
                    >
                      <Tag color={status.color}>{status.text}</Tag>
                      <Typography.Text strong>{item.item}</Typography.Text>
                      {item.note && (
                        <Typography.Text type="secondary">
                          {' '}
                          —— {item.note}
                        </Typography.Text>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
            {(reviewData.suggestions ?? []).length > 0 && (
              <div>
                <Typography.Title level={5} style={{ marginBottom: 8 }}>
                  完善建议（采纳后追加到对应部分，可再编辑）
                </Typography.Title>
                {(reviewData.suggestions ?? []).map((item, index) => (
                  <div
                    key={`${item.title}-${index}`}
                    style={{
                      marginBottom: 10,
                      padding: '8px 12px',
                      border: '1px solid var(--color-border, #d9d9d9)',
                      borderRadius: 8,
                    }}
                  >
                    <Space wrap size={4} style={{ marginBottom: 4 }}>
                      <Tag color="blue">{SECTION_LABELS[item.section] ?? item.section}</Tag>
                      <Typography.Text strong>{item.title}</Typography.Text>
                    </Space>
                    <Typography.Paragraph
                      style={{ whiteSpace: 'pre-line', marginBottom: 6 }}
                    >
                      {item.content}
                    </Typography.Paragraph>
                    {item.section === 'steps' ? (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        步骤建议请点「编辑」参考采用
                      </Typography.Text>
                    ) : (
                      <Popconfirm
                        title={`追加到「${SECTION_LABELS[item.section]}」`}
                        description="将在原内容后另起一行追加该建议文字。"
                        okButtonProps={{ loading: applying }}
                        onConfirm={() => {
                          if (reviewCard && (item.section === 'phones' || item.section === 'risks' || item.section === 'precautions')) {
                            void applySuggestion(reviewCard, item.section, item.content)
                          }
                        }}
                      >
                        <Button size="small" type="primary" ghost>
                          采纳并追加
                        </Button>
                      </Popconfirm>
                    )}
                  </div>
                ))}
              </div>
            )}
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              AI 分析结果仅供完善参考，采纳前请人工确认内容准确性。
            </Typography.Text>
          </div>
        )}
      </Modal>

      <Modal
        title={editingCard ? '编辑应急处置卡' : '新增应急处置卡'}
        width={820}
        open={editorOpen}
        onCancel={() => setEditorOpen(false)}
        onOk={() => void submitEditor()}
        confirmLoading={submitting}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Space wrap style={{ display: 'flex' }}>
            <Form.Item
              name="workshop"
              label="车间/部门"
              rules={[{ required: true, message: '请填写车间/部门' }]}
              style={{ width: 180 }}
            >
              <Input placeholder="如 103车间 / 公司级" />
            </Form.Item>
            <Form.Item name="position" label="岗位（可空）" style={{ width: 140 }}>
              <Input placeholder="如 配料、化测" />
            </Form.Item>
            <Form.Item
              name="accident_type"
              label="事故类型"
              style={{ width: 140 }}
            >
              <Select options={ACCIDENT_TYPE_OPTIONS} />
            </Form.Item>
          </Space>
          <Form.Item
            name="title"
            label="卡片名称"
            rules={[{ required: true, message: '请填写卡片名称' }]}
          >
            <Input placeholder="如 103车间液氨泄漏应急处置卡" />
          </Form.Item>
          <Form.Item name="subject" label="处置主题">
            <Input placeholder="如 液氨泄漏（用于筛选展示）" />
          </Form.Item>

          <Typography.Title level={5}>处置步骤</Typography.Title>
          <Form.List name="steps">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <Space
                    key={field.key}
                    align="baseline"
                    style={{ display: 'flex', marginBottom: 4 }}
                  >
                    <Form.Item
                      name={[field.name, 'order']}
                      style={{ width: 64, marginBottom: 4 }}
                    >
                      <Input placeholder="序号" />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'step']}
                      style={{ width: 130, marginBottom: 4 }}
                    >
                      <Input placeholder="步骤" />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'action']}
                      style={{ flex: 1, minWidth: 260, marginBottom: 4 }}
                    >
                      <Input.TextArea
                        placeholder="处置要求"
                        autoSize={{ minRows: 1, maxRows: 4 }}
                      />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'person']}
                      style={{ width: 120, marginBottom: 4 }}
                    >
                      <Input placeholder="负责人" />
                    </Form.Item>
                    <Button
                      type="text"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => remove(field.name)}
                    />
                  </Space>
                ))}
                <Button
                  type="dashed"
                  block
                  icon={<PlusOutlined />}
                  onClick={() => add({ order: '', step: '', action: '', person: '' })}
                >
                  添加步骤
                </Button>
              </>
            )}
          </Form.List>

          <Form.Item
            name="phones"
            label="应急电话"
            style={{ marginTop: 16 }}
          >
            <Input.TextArea
              rows={2}
              placeholder="车间负责人：…；公司消防值班室：…；消防：119；急救：120"
            />
          </Form.Item>
          <Form.Item name="risks" label="主要导致风险及导致的后果">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="precautions" label="应急注意事项">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
