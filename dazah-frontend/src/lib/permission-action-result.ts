export type PermissionActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; message: string }

/** Expected authorization conflicts must survive production Server Action serialization. */
export async function permissionActionResult<T>(
  request: () => Promise<Response>,
): Promise<PermissionActionResult<T>> {
  try {
    const response = await request()
    const payload: unknown = await response.json().catch(() => null)
    const envelope = payload && typeof payload === 'object' ? payload : null
    if (!response.ok) {
      const detail = envelope && 'detail' in envelope ? envelope.detail : undefined
      const message = envelope && 'message' in envelope ? envelope.message : undefined
      return { ok: false, status: response.status,
        message: response.status >= 500 ? '权限服务暂时不可用，请稍后重试'
          : typeof detail === 'string' ? detail : typeof message === 'string' ? message : '权限调整未通过校验，请检查输入并刷新授权',
      }
    }
    if (!envelope || !('data' in envelope) || envelope.data === null) {
      return { ok: false, status: 502, message: '权限服务返回无效结果，请刷新确认当前授权' }
    }
    return { ok: true, data: envelope.data as T }
  } catch {
    return { ok: false, status: 503, message: '暂时无法连接权限服务，请刷新确认是否已保存' }
  }
}
