'use client'

import { useQuery } from '@tanstack/react-query'
import { Card, Empty, Pagination, Select, Table } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import {
  fetchEnergySnapshotRows,
  fetchEnergySnapshots,
  fetchEnergySources,
} from '@/lib/api/energy'

export function EnergyDataClient() {
  const [sheetId, setSheetId] = useState<string>()
  const [snapshotId, setSnapshotId] = useState<string>()
  const [page, setPage] = useState(1)
  const sourcesQuery = useQuery({ queryKey: ['energy-sources'], queryFn: () => fetchEnergySources() })
  const snapshotsQuery = useQuery({
    queryKey: ['energy-snapshots', sheetId],
    queryFn: () => fetchEnergySnapshots(sheetId as string),
    enabled: Boolean(sheetId),
  })
  const rowsQuery = useQuery({
    queryKey: ['energy-snapshot-rows', snapshotId, page],
    queryFn: () => fetchEnergySnapshotRows(snapshotId as string, { page, page_size: 50 }),
    enabled: Boolean(snapshotId),
  })

  useEffect(() => {
    if (!sheetId && sourcesQuery.data?.[0]) setSheetId(sourcesQuery.data[0].id || undefined)
  }, [sheetId, sourcesQuery.data])
  useEffect(() => {
    if (snapshotsQuery.data?.[0]) {
      setSnapshotId(snapshotsQuery.data[0].id)
      setPage(1)
    } else {
      setSnapshotId(undefined)
    }
  }, [snapshotsQuery.data])

  const snapshotData = rowsQuery.data?.data
  const headers = snapshotData?.snapshot.header_values ?? []
  const tableRows = useMemo(
    () =>
      snapshotData?.rows.map((row) => ({
        key: row.id,
        row_index: row.row_index,
        ...Object.fromEntries(headers.map((header, index) => [header || `列${index + 1}`, row.values[index] ?? ''])),
      })) ?? [],
    [headers, snapshotData?.rows],
  )

  return (
    <main style={{ maxWidth: 1280, margin: '0 auto', padding: '28px 32px 48px' }}>
      <h1 style={{ margin: 0, color: '#1a1a1a', fontSize: 28, fontWeight: 600 }}>原始数据与快照</h1>
      <p style={{ margin: '6px 0 0', color: '#787671' }}>只读查看飞书工作表的原始快照。历史版本不会参与当前看板汇总。</p>

      <Card style={{ marginTop: 24 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 1fr) minmax(220px, .7fr)', gap: 16 }}>
          <Select
            loading={sourcesQuery.isLoading}
            placeholder="选择工作表"
            value={sheetId}
            onChange={setSheetId}
            options={sourcesQuery.data?.map((item) => ({
              value: item.id,
              label: `${item.period_month || '未分类'} · ${item.document_title} / ${item.title}`,
            }))}
          />
          <Select
            loading={snapshotsQuery.isLoading}
            placeholder="选择快照"
            value={snapshotId}
            onChange={(value) => { setSnapshotId(value); setPage(1) }}
            options={snapshotsQuery.data?.map((item) => ({
              value: item.id,
              label: `版本 ${item.snapshot_number} · ${new Date(item.captured_at).toLocaleString()} · ${item.row_count} 行`,
            }))}
          />
        </div>
      </Card>

      <Card title="快照内容" style={{ marginTop: 16 }}>
        {!snapshotId ? (
          <Empty description="请选择已同步的工作表和快照" />
        ) : rowsQuery.isError ? (
          <Empty description={(rowsQuery.error as Error).message || '快照读取失败'} />
        ) : (
          <>
            <Table
              loading={rowsQuery.isLoading}
              size="small"
              dataSource={tableRows}
              pagination={false}
              scroll={{ x: 'max-content' }}
              columns={[
                { title: '#', dataIndex: 'row_index', fixed: 'left', width: 70 },
                ...headers.map((header, index) => ({ title: header || `列${index + 1}`, dataIndex: header || `列${index + 1}`, width: 160, ellipsis: true })),
              ]}
            />
            <div style={{ display: 'flex', justifyContent: 'end', marginTop: 16 }}>
              <Pagination
                current={page}
                pageSize={50}
                total={Number(rowsQuery.data?.meta?.total ?? 0)}
                showSizeChanger={false}
                onChange={setPage}
              />
            </div>
          </>
        )}
      </Card>
    </main>
  )
}
