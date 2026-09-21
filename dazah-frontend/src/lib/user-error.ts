const STATUS_MESSAGES: Record<number, string> = {
  400: '请求内容有误，请检查后重试',
  401: '登录已失效，请重新登录',
  403: '没有执行此操作的权限，请联系管理员',
  404: '请求的内容不存在或已被删除，请刷新后重试',
  409: '数据已发生变化，请刷新后重试',
  413: '文件过大，请缩小文件后重试',
  422: '填写内容有误，请检查后重试',
  429: '操作过于频繁，请稍后重试',
  502: '服务暂时不可用，请稍后重试',
  503: '服务暂时不可用，请稍后重试',
  504: '请求超时，请稍后重试',
}

/** 将外部异常转换为可直接展示给用户的中文提示。原始异常仅用于日志。 */
export function getUserErrorMessage(
  error: unknown,
  fallback = '操作未完成，请稍后重试',
  status?: number,
): string {
  const message = typeof error === 'string'
    ? error.trim()
    : error instanceof Error
      ? error.message.trim()
      : ''

  if (/^请求失败[:：]?\s*\d{3}\b/i.test(message)) {
    return status && STATUS_MESSAGES[status] ? STATUS_MESSAGES[status] : '请求未完成，请稍后重试'
  }
  if (/failed to fetch|fetch failed|econn|proxy error/i.test(message)) {
    return '网络连接失败，请检查网络后重试'
  }
  if (/\p{Script=Han}/u.test(message)) return message
  if (status && [401, 403, 404, 409, 413, 429, 502, 503, 504].includes(status)) {
    return STATUS_MESSAGES[status]
  }
  if (/abort|timeout|timed out/i.test(message)) return '请求超时，请稍后重试'
  if (/network|failed to fetch|fetch failed|load failed|econn|proxy error/i.test(message)) {
    return '网络连接失败，请检查网络后重试'
  }
  if (status && STATUS_MESSAGES[status]) return STATUS_MESSAGES[status]
  if (status && status >= 500) return '服务暂时不可用，请稍后重试'
  return fallback
}
