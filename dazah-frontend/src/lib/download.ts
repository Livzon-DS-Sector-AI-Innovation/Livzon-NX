/** 浏览器端下载工具：Server Action 返回字节，浏览器侧触发下载（符合规范：服务端不碰 window/document） */
export function downloadBytes(bytes: ArrayBuffer, filename: string) {
  const blob = new Blob([bytes])
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/** 浏览器端打包下载：多份文件 zip 后触发下载（用于培训资料一键导出，jszip 按需加载） */
export async function downloadZip(entries: { name: string; bytes: ArrayBuffer }[], zipName: string) {
  const JSZip = (await import('jszip')).default
  const zip = new JSZip()
  for (const e of entries) zip.file(e.name, e.bytes)
  const blob = await zip.generateAsync({ type: 'blob' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = zipName.endsWith('.zip') ? zipName : `${zipName}.zip`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/** 从 Content-Disposition 提取文件名（含 filename*=UTF-8'' 形式） */
export function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback
  const star = header.match(/filename\*=(?:UTF-8|utf-8)''([^;]+)/)
  if (star) {
    try {
      return decodeURIComponent(star[1].replace(/"/g, ''))
    } catch {
      return star[1]
    }
  }
  const plain = header.match(/filename="?([^";]+)"?/)
  return plain ? plain[1] : fallback
}
