'use client'

import Link from 'next/link'
import { useState } from 'react'
import type { LocalLoginMode } from '@/lib/local-auth'

const errorMessages: Record<string, string> = {
  feishu_not_configured: '飞书应用凭证未配置，请联系系统管理员。',
  redirect_uri_missing: '飞书回调地址未配置，请联系系统管理员。',
  invalid_state: '登录状态已失效，请重新发起授权。',
  missing_code: '飞书未返回授权码，请重新登录。',
  access_denied: '你已取消飞书授权。',
  account_disabled: '账号已停用，请联系系统管理员。',
  callback_failed: '飞书授权登录失败，请稍后重试。',
  local_login_failed: '账号或密码不正确，请重新输入。',
  local_login_forbidden: '本地登录当前不可用，或该账号不具备应急管理员权限。',
  missing_credentials: '请输入账号和密码。',
  missing_token: '登录响应无效，请重新登录。',
}

interface LoginPanelProps {
  error?: string
  nextPath: string
  localLoginMode: LocalLoginMode
}

function BrandMark() {
  return (
    <span
      aria-hidden="true"
      className="grid h-9 w-9 shrink-0 grid-cols-2 gap-1 rounded-lg bg-[#176b5b] p-[7px]"
    >
      <span className="rounded-[2px] bg-white" />
      <span className="rounded-[2px] bg-white/55" />
      <span className="col-span-2 rounded-[2px] bg-white" />
    </span>
  )
}

function FeishuMark() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-5 w-5"
      fill="none"
    >
      <path d="M5.2 4.5 11 9v5.3L5.2 9.8V4.5Z" fill="#3370FF" />
      <path d="m18.8 4.5-5.8 4.6v5.2l5.8-4.5V4.5Z" fill="#00D6B9" />
      <path d="M5.2 12.2 11 16.7V22l-5.8-4.6v-5.2Z" fill="#7B67EE" />
      <path d="m18.8 12.2-5.8 4.5V22l5.8-4.6v-5.2Z" fill="#FF8800" />
    </svg>
  )
}

export function LoginPanel({
  error,
  nextPath,
  localLoginMode,
}: LoginPanelProps) {
  const [showLocalLogin, setShowLocalLogin] = useState(
    Boolean(error?.startsWith('local_') || error === 'missing_credentials'),
  )
  const message = error ? errorMessages[error] || '登录失败，请重新尝试。' : null
  const feishuHref = `/auth/login?next=${encodeURIComponent(nextPath)}`
  const localLoginAvailable = localLoginMode !== 'disabled'
  const emergencyOnly = localLoginMode === 'admin_only'

  return (
    <main className="flex min-h-dvh flex-col bg-[#f7f8f6] text-[#16211f]">
      <header className="border-b border-[#dfe4e0] bg-white/80 px-5 backdrop-blur-sm sm:px-8">
        <div className="mx-auto flex h-[72px] max-w-[1120px] items-center justify-between gap-6">
          <div className="flex items-center gap-3">
          <BrandMark />
          <div>
              <p className="text-sm font-semibold tracking-[-0.01em] text-[#17231f]">
              原料药工厂管理平台
            </p>
              <p className="mt-0.5 hidden text-[11px] text-[#73807c] sm:block">
              丽珠集团（宁夏）制药有限公司
            </p>
          </div>
        </div>
          <p className="flex items-center gap-2 text-xs font-medium text-[#687570]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#2b8a78]" />
            内部系统
          </p>
        </div>
      </header>

      <div className="flex flex-1 items-center px-5 py-12 sm:px-8 sm:py-16">
        <div className="mx-auto grid w-full max-w-[960px] gap-12 lg:grid-cols-[280px_1px_420px] lg:items-center lg:justify-between lg:gap-16">
          <section
            aria-labelledby="system-context-title"
            className="hidden lg:block"
          >
            <p className="text-xs font-semibold tracking-[0.12em] text-[#367567]">
              统一数字化工作台
            </p>
            <h1
              id="system-context-title"
              className="mt-4 text-[1.75rem] font-semibold leading-[1.25] tracking-[-0.035em] text-[#17231f]"
            >
              原料药生产协同与追溯
            </h1>
            <p className="mt-4 text-sm leading-6 text-[#66736e]">
              连接生产、质量、仓储与 EHS 业务，在统一权限体系下完成日常操作。
            </p>

            <div className="mt-8 border-y border-[#dfe4e0]">
              {['生产执行', '质量协同', '仓储与 EHS'].map(
              (item, index) => (
                <div
                  key={item}
                    className="grid grid-cols-[28px_1fr] items-center border-b border-[#e6eae7] py-3.5 last:border-b-0"
                >
                    <span className="font-mono text-[10px] text-[#8a9691]">
                    0{index + 1}
                  </span>
                    <span className="text-sm font-medium text-[#43504b]">
                    {item}
                  </span>
                </div>
              ),
            )}
          </div>
          </section>

          <div aria-hidden="true" className="hidden h-full min-h-80 bg-[#dfe4e0] lg:block" />

          <section aria-labelledby="login-title" className="w-full max-w-[420px]">
            <div className="mb-8">
              <p className="text-xs font-semibold tracking-[0.12em] text-[#367567]">
                身份认证
              </p>
              <h2
                id="login-title"
                className="mt-3 text-[1.85rem] font-semibold leading-tight tracking-[-0.035em] text-[#10201c] sm:text-[2rem]"
              >
                登录工作台
              </h2>
              <p className="mt-3 max-w-[38ch] text-sm leading-6 text-[#687570]">
                使用企业飞书身份继续，仅授权范围内的成员可以访问。
              </p>
            </div>

          {message && (
            <div
              role="alert"
                className="mb-5 rounded-r-md border-l-2 border-[#b94a42] bg-[#fff3f0] px-4 py-3 text-sm leading-6 text-[#87352f]"
            >
              {message}
            </div>
          )}

          <Link
            href={feishuHref}
              className="group flex h-12 w-full items-center justify-center gap-2.5 rounded-lg bg-[#145c4f] px-5 text-sm font-semibold text-white transition-colors duration-200 hover:bg-[#104d43] focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-[#367567] active:bg-[#0d443a]"
          >
            <span className="grid h-7 w-7 place-items-center rounded-md bg-white">
              <FeishuMark />
            </span>
            使用飞书授权登录
            <span
              aria-hidden="true"
              className="ml-1 transition-transform duration-200 group-hover:translate-x-0.5"
            >
              →
            </span>
          </Link>

            <div className="mt-5 grid grid-cols-[18px_1fr] gap-x-3 border-b border-[#dfe4e0] pb-6 text-xs leading-5 text-[#75817d]">
            <svg
              aria-hidden="true"
              viewBox="0 0 20 20"
                className="mt-0.5 h-[18px] w-[18px] text-[#367567]"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
            >
              <path d="M10 2.5 16 5v4.2c0 3.8-2.3 6.6-6 8.3-3.7-1.7-6-4.5-6-8.3V5l6-2.5Z" />
              <path d="m7.5 10 1.6 1.6 3.5-3.5" />
            </svg>
              <p>身份范围由飞书应用统一管理，平台操作将按账号记录审计日志。</p>
            </div>

          {localLoginAvailable && (
            <div className="pt-5">
              <button
                type="button"
                aria-expanded={showLocalLogin}
                aria-controls="local-login-form"
                onClick={() => setShowLocalLogin((value) => !value)}
                  className="flex min-h-10 w-full items-center justify-between rounded-md px-1 text-left text-sm font-medium text-[#50615c] transition-colors hover:text-[#145c4f] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#367567]"
              >
                <span>
                  {emergencyOnly ? '管理员应急入口' : '使用本地开发账号'}
                </span>
                <span
                  aria-hidden="true"
                  className={`text-lg transition-transform duration-200 ${showLocalLogin ? 'rotate-45' : ''}`}
                >
                  +
                </span>
              </button>

              {showLocalLogin && (
                <form
                  id="local-login-form"
                  action="/auth/local-login"
                  method="post"
                  className="mt-3 grid gap-4 border-t border-[#dfe5e1] pt-5"
                >
                  <input type="hidden" name="next" value={nextPath} />
                  {emergencyOnly && (
                    <p className="border-l-2 border-[#c88a35] bg-[#fff9ed] px-3 py-2 text-xs leading-5 text-[#76541f]">
                      仅用于飞书认证故障期间的系统恢复，普通本地账号无法登录。
                    </p>
                  )}
                  <label className="grid gap-2">
                    <span className="text-sm font-medium text-[#33433f]">账号</span>
                    <input
                      name="username"
                      autoComplete="username"
                      required
                        className="h-11 rounded-lg border border-[#c9d1cd] bg-white px-3 text-sm text-[#15211f] outline-none transition focus:border-[#367567] focus:ring-2 focus:ring-[#367567]/15"
                    />
                  </label>
                  <label className="grid gap-2">
                    <span className="text-sm font-medium text-[#33433f]">密码</span>
                    <input
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      required
                        className="h-11 rounded-lg border border-[#c9d1cd] bg-white px-3 text-sm text-[#15211f] outline-none transition focus:border-[#367567] focus:ring-2 focus:ring-[#367567]/15"
                    />
                  </label>
                  <button
                    type="submit"
                      className="mt-1 h-11 rounded-lg border border-[#9eaaa5] bg-white px-4 text-sm font-semibold text-[#263934] transition-colors duration-200 hover:border-[#516760] hover:bg-[#f2f6f3] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#367567] active:bg-[#eaf0ec]"
                  >
                    验证并进入系统
                  </button>
                </form>
              )}
            </div>
            )}
          </section>
        </div>
      </div>

      <footer className="px-5 pb-6 sm:px-8">
        <div className="mx-auto flex max-w-[1120px] flex-col gap-1 border-t border-[#e3e7e4] pt-5 text-[11px] text-[#89938f] sm:flex-row sm:items-center sm:justify-between sm:gap-4">
          <span>© 2026 丽珠集团（宁夏）制药有限公司</span>
          <span>权限分级 · 操作留痕 · 受控访问</span>
        </div>
      </footer>
    </main>
  )
}
