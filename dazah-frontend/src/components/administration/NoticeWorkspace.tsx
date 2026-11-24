'use client'

import { useEffect, useState } from 'react'

import { EyeOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tooltip,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'

import PlatformNotice from '@/components/shared/PlatformNotice'
import {
  deleteNotice,
  fetchNoticeContent,
  fetchNoticeDetail,
  fetchNoticeList,
  noticeFileUrl,
  updateNotice,
} from '@/lib/api/notice'
import { ADMIN_NOTICE_PAGE_KEY } from '@/lib/administration-pages'
import { useListUrlState } from '@/lib/useListUrlState'
import { useAuthStore } from '@/stores/auth'
import type { NoticeItem, NoticeUpdateInput } from '@/types/administration'

import NoticeImportModal from './NoticeImportModal'

/** 应用根上没有全局 QueryClientProvider（组件自带，同 MappedDatasetPage）。 */
export default function NoticeWorkspace() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
      }),
  )
  return (
    <QueryClientProvider client={queryClient}>
      <NoticeWorkspaceContent />
    </QueryClientProvider>
  )
}

interface NoticeFormValues extends NoticeUpdateInput {
  published_at: string
}

function NoticeWorkspaceContent() {
  const { message } = App.useApp()
  const canOperate = useAuthStore((state) =>
    state.hasPagePermission(ADMIN_NOTICE_PAGE_KEY, 'operate'),
  )
  // 已提交的筛选与分页保存在 URL 查询参数（list-url-state 规范）
  const { page, pageSize, params, setListQuery } = useListUrlState(20)
  const keyword = params.get('keyword') ?? ''
  const category = params.get('category') ?? ''
  const [keywordInput, setKeywordInput] = useState(keyword)
  const [importOpen, setImportOpen] = useState(false)
  const [contentNotice, setContentNotice] = useState<NoticeItem | null>(null)
  const [contentText, setContentText] = useState('')
  const [contentLoading, setContentLoading] = useState(false)
  const [editing, setEditing] = useState<NoticeItem | null>(null)

  const listQuery = useQuery({
    queryKey: ['administration-notices', page, pageSize, keyword, category],
    queryFn: () =>
      fetchNoticeList({ page, page_size: pageSize, keyword, category }),
  })
  const data = listQuery.data

  const refreshList = () => listQuery.refetch()

  const handleShowContent = async (notice: NoticeItem) => {
    setContentNotice(notice)
    setContentText('')
    setContentLoading(true)
    try {
      const detail = await fetchNoticeContent(notice.id)
      setContentText(detail.content || '（该公告未识别到正文内容）')
    } catch (error) {
      message.error((error as Error).message || '读取公告内容失败')
      setContentNotice(null)
    } finally {
      setContentLoading(false)
    }
  }

  const handleDownloadFile = (notice: NoticeItem) => {
    if (!notice.source_file_name) {
      message.warning('该公告没有原文存档')
      return
    }
    window.open(noticeFileUrl(notice.id), '_blank')
  }

  const handleDelete = async (notice: NoticeItem) => {
    try {
      await deleteNotice(notice.id)
      message.success(`已删除公告「${notice.title || notice.notice_no}」`)
      refreshList()
    } catch (error) {
      message.error((error as Error).message || '删除失败')
    }
  }

  const columns: ColumnsType<NoticeItem> = [
    { title: '编号', dataIndex: 'notice_no', key: 'notice_no', width: 130 },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: { showTitle: false },
      render: (value: string) => (
        <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 260 }}>
          {value}
        </Typography.Text>
      ),
    },
    { title: '发布单位', dataIndex: 'publisher', key: 'publisher', width: 150, ellipsis: true },
    { title: '发布日期', dataIndex: 'published_at', key: 'published_at', width: 110 },
    { title: '类别', dataIndex: 'category', key: 'category', width: 110 },
    {
      title: '备注',
      dataIndex: 'remark',
      key: 'remark',
      ellipsis: { showTitle: false },
      render: (value: string | null) =>
        value ? (
          <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 200 }}>
            {value}
          </Typography.Text>
        ) : null,
    },
    {
      title: '操作',
      key: 'actions',
      width: canOperate ? 200 : 110,
      render: (_, notice) => (
        <Space size={4} wrap>
          {canOperate && (
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => void handleShowContent(notice)}
            >
              内容
            </Button>
          )}
          {canOperate && (
            <Button type="link" size="small" onClick={() => handleDownloadFile(notice)}>
              原文
            </Button>
          )}
          {canOperate && (
            <Button type="link" size="small" onClick={() => setEditing(notice)}>
              编辑
            </Button>
          )}
          {canOperate && (
            <Popconfirm
              title="确认删除该公告？"
              description={`编号 ${notice.notice_no || '—'}·${notice.title}`}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => void handleDelete(notice)}
            >
              <Button type="link" size="small" danger>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card size="small">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Space size={8} wrap>
          <Input.Search
            placeholder="搜索编号/标题/单位"
            allowClear
            value={keywordInput}
            onChange={(event) => setKeywordInput(event.target.value)}
            onSearch={(value) => {
              // 提交筛选回第一页；空串从 URL 删除条件
              setListQuery({ keyword: value.trim() }, true)
            }}
            style={{ width: 240 }}
          />
          <Select
            placeholder="类别"
            allowClear
            value={category || undefined}
            onChange={(value) => {
              setListQuery({ category: value ?? null }, true)
            }}
            options={(data?.categories ?? []).map((item) => ({
              label: item,
              value: item,
            }))}
            style={{ minWidth: 130 }}
          />
        </Space>
        <Space size={8}>
          <Tooltip title={canOperate ? undefined : '需要操作权限'}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              disabled={!canOperate}
              onClick={() => setImportOpen(true)}
            >
              上传公告
            </Button>
          </Tooltip>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => refreshList()}
            loading={listQuery.isFetching}
          >
            刷新
          </Button>
        </Space>
      </div>

      {listQuery.isError && (
        <PlatformNotice
          type="error"
          showRulesLink={false}
          message={(listQuery.error as Error).message || '读取公告台账失败'}
        />
      )}

      <Table
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={listQuery.isLoading}
        locale={{ emptyText: '暂无公告' }}
        pagination={{
          current: page,
          pageSize,
          total: data?.total ?? 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (nextPage, nextSize) => {
            // 翻页保留筛选；页大小变化视为查询变更回第一页
            setListQuery(
              nextPage === page
                ? { page_size: nextSize, page: null }
                : { page: nextPage, page_size: nextSize },
            )
          },
        }}
      />

      <NoticeImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={refreshList}
      />

      <Modal
        open={contentNotice !== null}
        title={
          contentNotice
            ? `公告内容${contentNotice.notice_no ? `（${contentNotice.notice_no}）` : ''}`
            : '公告内容'
        }
        footer={null}
        onCancel={() => setContentNotice(null)}
        width={720}
      >
        {contentLoading ? (
          <Typography.Text type="secondary">正在读取公告内容…</Typography.Text>
        ) : (
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
            {contentText}
          </Typography.Paragraph>
        )}
      </Modal>

      <NoticeEditModal
        notice={editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null)
          refreshList()
        }}
      />
    </Card>
  )
}

interface NoticeEditModalProps {
  notice: NoticeItem | null
  onClose: () => void
  onSaved: () => void
}

/** 编辑弹窗：元数据 + 公告内容（内容经 operate 专用端点取回预填）。 */
function NoticeEditModal({ notice, onClose, onSaved }: NoticeEditModalProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<NoticeFormValues>()
  const [saving, setSaving] = useState(false)
  const noticeId = notice?.id ?? null

  useEffect(() => {
    if (!noticeId) return
    let cancelled = false
    // 依赖只留 noticeId：列表 refetch 产生新对象引用时不得重置正在编辑的表单；
    // 元数据与内容都以服务端为准（详情端点元数据 + operate 内容端点）
    form.resetFields()
    Promise.all([fetchNoticeDetail(noticeId), fetchNoticeContent(noticeId)])
      .then(([item, detail]) => {
        if (cancelled) return
        form.setFieldsValue({
          notice_no: item.notice_no,
          title: item.title,
          publisher: item.publisher,
          published_at: item.published_at ?? '',
          category: item.category,
          remark: item.remark ?? '',
          content: detail.content,
        })
      })
      .catch(() => {
        if (!cancelled) message.error('读取公告详情失败，请关闭后重试')
      })
    return () => {
      cancelled = true
    }
  }, [noticeId, form, message])

  const handleSave = async () => {
    if (!noticeId) return
    const values = await form.validateFields()
    setSaving(true)
    try {
      await updateNotice(noticeId, values)
      message.success('公告已更新')
      onSaved()
    } catch (error) {
      message.error((error as Error).message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={notice !== null}
      title="编辑公告"
      width={720}
      onCancel={onClose}
      onOk={() => void handleSave()}
      confirmLoading={saving}
      okText="保存"
      destroyOnHidden
    >
      <Form form={form} layout="vertical" size="small">
        <Space style={{ width: '100%' }} size="small" wrap>
          <Form.Item name="notice_no" label="公告编号" style={{ marginBottom: 0, width: 200 }}>
            <Input />
          </Form.Item>
          <Form.Item
            name="published_at"
            label="发布日期"
            style={{ marginBottom: 0, width: 140 }}
          >
            <Input placeholder="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item name="category" label="类别" style={{ marginBottom: 0, width: 140 }}>
            <Input />
          </Form.Item>
          <Form.Item name="publisher" label="发布单位" style={{ marginBottom: 0, width: 180 }}>
            <Input />
          </Form.Item>
        </Space>
        <Form.Item
          name="title"
          label="公告标题"
          required
          rules={[{ required: true, message: '请填写公告标题' }]}
          style={{ marginBottom: 0, marginTop: 8 }}
        >
          <Input />
        </Form.Item>
        <Form.Item
          name="content"
          label="公告内容"
          style={{ marginBottom: 0, marginTop: 8 }}
        >
          <Input.TextArea rows={8} maxLength={20000} showCount />
        </Form.Item>
        <Form.Item name="remark" label="备注" style={{ marginBottom: 0, marginTop: 8 }}>
          <Input.TextArea rows={2} maxLength={2000} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
