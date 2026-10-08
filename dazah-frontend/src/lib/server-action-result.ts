export type ServerActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; message: string; reference?: string }

/** Only explicitly classified, public API errors may cross the action boundary. */
export class ActionRequestError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
  }
}

export async function serverActionResult<T>(
  name: string,
  operation: () => Promise<T>,
): Promise<ServerActionResult<T>> {
  try {
    return { ok: true, data: await operation() }
  } catch (error) {
    if (error instanceof ActionRequestError && error.status < 500) {
      return { ok: false, message: error.message }
    }
    const reference = crypto.randomUUID()
    // Never log action arguments, uploaded files, upstream bodies or credentials.
    console.error('[Server Action]', { name, reference,
      status: error instanceof ActionRequestError ? error.status : undefined,
      frames: error instanceof Error ? error.stack?.split('\n').filter(line => /^\s+at /.test(line)).slice(0, 12) : undefined,
    })
    return { ok: false, message: '操作未完成，请稍后重试；若已提交，请先刷新核对结果', reference }
  }
}

/** Unwrap on the browser side, after React has serialized a normal result. */
export function unwrapServerActionResult<T>(result: ServerActionResult<T>): T {
  if (result.ok) return result.data
  throw new Error(result.reference ? `${result.message}（错误标识：${result.reference}）` : result.message)
}
