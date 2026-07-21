import * as XLSX from 'xlsx'

interface ExportColumn {
  header: string
  key: string
}

export function exportToExcel(
  data: any[],
  columns: ExportColumn[],
  filename: string
) {
  // 转换数据为简单格式
  const exportData = data.map(row => {
    const newRow: Record<string, any> = {}
    columns.forEach(col => {
      newRow[col.header] = row[col.key]
    })
    return newRow
  })

  // 创建工作表
  const worksheet = XLSX.utils.json_to_sheet(exportData)
  
  // 自动调整列宽
  const colWidths = columns.map(col => ({
    wch: Math.max(col.header.length * 1.5, 12)
  }))
  worksheet['!cols'] = colWidths

  // 创建工作簿
  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, worksheet, 'Sheet1')

  // 导出文件
  XLSX.writeFile(workbook, filename)
}
