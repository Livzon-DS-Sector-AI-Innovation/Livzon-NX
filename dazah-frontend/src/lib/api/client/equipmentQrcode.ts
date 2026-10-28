// 设备报修二维码 PDF 下载（客户端直连后端二进制接口）。

const QRCODE_REQUEST_TIMEOUT_MS = 30000

function getDownloadFilename(response: Response, fallback: string): string {
  const contentDisposition = response.headers.get('content-disposition') || ''
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }
  return fallback
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export async function fetchEquipmentQrcodePdf(workshopCode: string): Promise<void> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), QRCODE_REQUEST_TIMEOUT_MS)
  let response: Response
  try {
    response = await fetch(
      `/api/v1/equipment/equipments/qrcode-pdf?workshop=${encodeURIComponent(workshopCode)}`,
      { signal: controller.signal }
    )
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('导出超时（>30秒），请重试')
    }
    throw error
  } finally {
    window.clearTimeout(timeoutId)
  }
  if (!response.ok) {
    throw new Error(`设备码导出失败: ${response.status}`)
  }
  const blob = await response.blob()
  downloadBlob(blob, getDownloadFilename(response, `设备报修码_${workshopCode}.pdf`))
}
