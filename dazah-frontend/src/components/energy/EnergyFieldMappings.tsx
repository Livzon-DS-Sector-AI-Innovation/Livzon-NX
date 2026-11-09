import { Collapse, Table, Tag, Typography } from 'antd'
import type { ImportPreview } from '@/lib/api/energy-ledger'

function record(value: unknown): value is Record<string, unknown> { return Boolean(value && typeof value === 'object' && !Array.isArray(value)) }

interface MappingRow {
  key: string; name: string; source: string; original: string; status: string; reason: string; formulas: string[]
}

export function EnergyFieldMappings({ preview }: { preview: ImportPreview }) {
  const mappings = preview.payload.field_mappings
  if (!Array.isArray(mappings)) return null
  const sheets = Array.isArray(preview.payload.sheets) ? preview.payload.sheets.filter(record) : []
  const rows: MappingRow[] = mappings.flatMap(item => {
    if (!record(item) || typeof item.business_key !== 'string' || typeof item.business_name !== 'string' || typeof item.source_sheet !== 'string' || typeof item.source_column !== 'number' || !Number.isInteger(item.source_column) || item.source_column < 2 || item.source_column > 200) return []
    const column = item.source_column
    const sheet = sheets.find(sheet => sheet.name === item.source_sheet)
    const grid = Array.isArray(sheet?.source_grid) ? sheet.source_grid : []
    const references = Array.isArray(item.formula_cells) ? item.formula_cells : []
    const formulas = references.flatMap(address => {
      if (typeof address !== 'string' || !/^[A-Z]+[1-9]\d*$/.test(address)) return []
      const row = grid[Number(address.match(/\d+$/)?.[0]) - 1]
      const formula = Array.isArray(row) ? row[column - 1] : null
      return typeof formula === 'string' && formula.startsWith('=') ? [`${address}：${formula}`] : []
    })
    return [{ key: `${item.business_key}:${item.source_sheet}:${column}`, name: `${String(item.business_sheet ?? item.source_sheet)}·${item.business_name}`, source: `${item.source_sheet}!${typeof item.source_column_letter === 'string' ? item.source_column_letter : `第${column}`}列`, original: String(item.source_label ?? ''), status: String(item.status ?? 'mapped'), reason: typeof item.reason === 'string' ? item.reason : '', formulas }]
  })
  if (!rows.length) return null
  return <Collapse items={[{ key: 'fields', label: `业务字段与本月原表映射（${rows.length} 项）`, children: <Table<MappingRow> rowKey="key" dataSource={rows} pagination={{ pageSize: 10 }} scroll={{ x: 850 }} expandable={{ rowExpandable: row => row.formulas.length > 0, expandedRowRender: row => <div style={{ maxHeight: 240, overflow: 'auto' }}>{row.formulas.map(formula => <Typography.Paragraph key={formula}><code>{formula}</code></Typography.Paragraph>)}</div> }} columns={[
    { title: '统一业务字段', dataIndex: 'name', width: 220 },
    { title: '本月原表位置', dataIndex: 'source', width: 180 },
    { title: '原始字段名', dataIndex: 'original', width: 180 },
    { title: '公式', render: (_, row) => row.formulas.length ? `${row.formulas.length} 个，展开查看` : '手填值或空白' },
    { title: '映射状态', render: (_, row) => <><Tag color={row.status === 'mapped' ? 'success' : 'warning'}>{row.status === 'excluded' ? '不纳入能源指标' : row.status === 'missing_label' ? '字段名称待核对' : row.status === 'duplicate_label' ? '同名表计，按原列区分' : '已映射'}</Tag>{row.reason && <div>{row.reason}</div>}</> },
  ]} /> }]} />
}
