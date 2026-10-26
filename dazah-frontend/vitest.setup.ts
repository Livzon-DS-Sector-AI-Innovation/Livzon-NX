// 全局测试环境补齐（React 19 + happy-dom）
// 1) React 19 的 act() 要求测试环境声明 IS_REACT_ACT_ENVIRONMENT=true（官方要求）。
// 2) happy-dom v20 在 Node 25 / vitest 4 下 window.localStorage 方法缺失
//    （getItem/clear 等为 undefined），统一补内存实现，仅在方法缺失时生效，
//    不影响其它环境。
// 3) React 19 在提交时会把被动副作用（useEffect）的 flush 排入一个 NormalPriority
//    调度回调，该回调会读取 window.event。用例在提交后立即结束时，回调可能晚于
//    happy-dom 环境销毁才执行，抛出 "ReferenceError: window is not defined"。
//    此时所有用例都是通过的，失败只来自这个未处理错误，表现为随机红灯。
//    下面的收尾在环境销毁前让出一轮宏任务，把已排队的回调跑完。
//    顺序很重要：Vitest 逆序执行 afterEach，setup 文件先注册，因此本钩子运行在
//    测试文件自己的 afterEach（通常在其中 unmount 组件）之后。

import { afterEach } from 'vitest'

export {}

declare global {
  // React 19 测试环境的 act 支持标志（happy-dom / vitest 未声明）
  var IS_REACT_ACT_ENVIRONMENT: boolean | undefined
}

globalThis.IS_REACT_ACT_ENVIRONMENT = true

// 先捕获真实定时器：用例启用 fake timers 时，这里仍要能真正让出事件循环，
// 否则收尾会被冻结到用例超时。
const realSetTimeout = globalThis.setTimeout.bind(globalThis)
const realSetImmediate: ((callback: () => void) => void) | undefined =
  typeof globalThis.setImmediate === 'function'
    ? (globalThis.setImmediate.bind(globalThis) as (callback: () => void) => void)
    : undefined

afterEach(async () => {
  // Node 环境下 React 调度器走 setImmediate；浏览器环境走 MessageChannel/
  // 定时器。两种都让出一轮，确保被动副作用回调在 window 仍然存在时执行。
  if (realSetImmediate) {
    await new Promise<void>((resolve) => realSetImmediate(resolve))
  }
  await new Promise<void>((resolve) => realSetTimeout(resolve, 0))
})

if (
  typeof window !== 'undefined' &&
  window.localStorage &&
  typeof window.localStorage.clear !== 'function'
) {
  const store = new Map<string, string>()
  const storage: Storage = {
    get length() {
      return store.size
    },
    clear: () => store.clear(),
    getItem: (key: string) => {
      const value = store.get(key)
      return value === undefined ? null : value
    },
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => {
      store.delete(key)
    },
    setItem: (key: string, value: string) => {
      store.set(key, String(value))
    },
  }
  Object.defineProperty(window, 'localStorage', { value: storage, configurable: true })
}
