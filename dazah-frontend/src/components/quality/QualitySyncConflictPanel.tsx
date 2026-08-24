'use client'

import Link from 'next/link'
import { Alert, Button, Card, List, Space, Tag, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { fetchQualitySyncConflicts } from '@/lib/api/client/quality'
import type { QualitySyncConflictItem } from '@/types/quality'

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

function renderDirection(value: string | null | undefined): React.ReactNode {
  if (value === 'system_to_base') return <Tag color="blue">系统到飞书</Tag>
  if (value === 'base_to_system') return <Tag color="purple">飞书到系统</Tag>
  return <Tag>未记录</Tag>
}

export function QualitySyncConflictPanel() {
  const { data, isLoading: loading, error, refetch } = useQuery({
    queryKey: ['quality-sync', 'conflicts'],
    queryFn: () => fetchQualitySyncConflicts({ limit: 10 }),
  })

  const loadError = error ? (error instanceof Error ? error.message : '加载同步冲突失败') : null
  const items: QualitySyncConflictItem[] = loadError ? [] : (data?.items ?? [])

  return (
    <Card
      title="飞书同步冲突"
      extra={(
        <Button icon={<ReloadOutlined />} onClick={() => void refetch()} loading={loading}>
          刷新
        </Button>
      )}
    >
      {loadError ? (
        <Alert
          type="error"
          showIcon
          message="同步冲突加载失败"
          description={loadError}
          style={{ marginBottom: 16 }}
        />
      ) : null}
      {items.length === 0 ? (
        <Typography.Text type="secondary">
          当前没有待处理的飞书同步冲突。
        </Typography.Text>
      ) : (
        <List
          loading={loading}
          dataSource={items}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Link key="open" href={item.route_path}>去处理</Link>,
              ]}
            >
              <List.Item.Meta
                title={(
                  <Space size={8} wrap>
                    <span>{item.entity_label}</span>
                    <Typography.Text strong>{item.record_code}</Typography.Text>
                    {renderDirection(item.feishu_last_sync_direction)}
                  </Space>
                )}
                description={(
                  <Space orientation="vertical" size={2}>
                    <Typography.Text>{item.record_title || '未命名记录'}</Typography.Text>
                    <Typography.Text type="secondary">
                      飞书更新时间：{formatDateTime(item.feishu_source_updated_at)}
                    </Typography.Text>
                    <Typography.Text type="secondary">
                      最近同步时间：{formatDateTime(item.feishu_synced_at)}
                    </Typography.Text>
                    <Typography.Text type="danger">
                      {item.feishu_last_sync_error || '检测到同步冲突，请人工确认'}
                    </Typography.Text>
                  </Space>
                )}
              />
            </List.Item>
          )}
        />
      )}
    </Card>
  )
}
