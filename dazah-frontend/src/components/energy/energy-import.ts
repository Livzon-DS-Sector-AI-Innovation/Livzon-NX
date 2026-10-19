import type { ImportPreview } from '@/lib/api/energy-ledger'

export interface ImportColumn { key: string; sheet: string; column: number; label: string; count: number }
export interface ImportAdjustment { key: string; sheet: string; label: string; date: string; value: string }
function record(value: unknown): value is Record<string, unknown> { return Boolean(value && typeof value === 'object' && !Array.isArray(value)) }

export function importRows(preview?: ImportPreview): { columns: ImportColumn[]; manualRows: ImportAdjustment[] } {
  const columns: ImportColumn[] = [], manualRows: ImportAdjustment[] = []
  const sheets = preview?.payload.sheets
  if (!Array.isArray(sheets)) return { columns, manualRows }
  const formulaColumns = new Set<string>()
  const formulas = preview?.payload.formulas
  if (Array.isArray(formulas)) for (const formula of formulas) {
    if (!record(formula) || typeof formula.sheet !== 'string' || typeof formula.cell !== 'string') continue
    const letters = formula.cell.match(/^[A-Z]+/)?.[0]
    if (!letters) continue
    let column = 0
    for (const letter of letters) column = column * 26 + letter.charCodeAt(0) - 64
    formulaColumns.add(`${formula.sheet}:${column}`)
  }
  for (const sheet of sheets) {
    if (!record(sheet) || typeof sheet.name !== 'string' || !Array.isArray(sheet.headers) || !Array.isArray(sheet.cells)) continue
    const counts = new Map<number, number>()
    for (const cell of sheet.cells) {
      if (!record(cell) || typeof cell.column !== 'number' || typeof cell.date !== 'string' || typeof cell.value !== 'string') continue
      if (typeof sheet.category === 'string' && Array.isArray(sheet.input_columns) && sheet.input_columns.includes(cell.column)) counts.set(cell.column, (counts.get(cell.column) || 0) + 1)
      // Only isolated literal overrides within an actual formula column can be
      // offered for review. Value-only exports are never adjustment candidates.
      const label = sheet.headers[cell.column - 1]
      if (typeof sheet.category !== 'string' && formulaColumns.has(`${sheet.name}:${cell.column}`) && typeof label === 'string' && label && !label.includes('大罐数量')) {
        manualRows.push({ key: `${sheet.name}:${cell.column}:${cell.date}`, sheet: sheet.name, label, date: cell.date, value: cell.value })
      }
    }
    for (const [column, count] of counts) {
      const label = sheet.headers[column - 1]
      if (typeof label === 'string' && label && !label.includes('大罐数量')) columns.push({ key: `${sheet.name}:${column}`, sheet: sheet.name, column, label, count })
    }
  }
  return { columns, manualRows }
}
