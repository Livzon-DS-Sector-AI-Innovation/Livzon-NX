import { getUserErrorMessage, readBusinessErrorCode, uncertainWriteMessage, UserFacingError } from './user-error'

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
  fallback = '操作未完成，请稍后重试；若已提交，请先刷新核对结果',
): Promise<ServerActionResult<T>> {
  try {
    return { ok: true, data: await operation() }
  } catch (error) {
    if (error instanceof UserFacingError) return { ok: false, message: error.message }
    if (error instanceof ActionRequestError && error.status >= 400 && error.status < 500) {
      return { ok: false, message: getUserErrorMessage(error.message, undefined, error.status) }
    }
    const reference = crypto.randomUUID()
    // Never log action arguments, uploaded files, upstream bodies or credentials.
    console.error('[Server Action]', { name, reference,
      status: error instanceof ActionRequestError ? error.status : undefined,
      frames: error instanceof Error ? error.stack?.split('\n').filter(line => /^\s+at /.test(line)).slice(0, 12) : undefined,
    })
    return { ok: false, message: fallback, reference }
  }
}

export type BusinessErrorMessages = Readonly<Partial<Record<number, Readonly<Record<string, string>>>>>

/** Map HTTP failures without passing upstream bodies or framework messages to the browser. */
export async function requireActionResponse(
  response: Response,
  businessMessages?: BusinessErrorMessages,
): Promise<void> {
  if (response.ok) return

  const messages = businessMessages?.[response.status]
  if (messages) {
    const payload: unknown = await response.json().catch(() => null)
    const code = readBusinessErrorCode(payload)
    if (code && Object.hasOwn(messages, code)) {
      throw new UserFacingError(messages[code])
    }
  }
  throw new ActionRequestError(response.status, getUserErrorMessage(undefined, undefined, response.status))
}

/** Unwrap on the browser side, after React has serialized a normal result. */
export function unwrapServerActionResult<T>(result: ServerActionResult<T>): T {
  if (result.ok) return result.data
  throw new UserFacingError(result.reference ? `${result.message}（错误标识：${result.reference}）` : result.message)
}

export function getActionErrorMessage(error: unknown, operation: string): string {
  return error instanceof UserFacingError ? error.message : uncertainWriteMessage(operation)
}
