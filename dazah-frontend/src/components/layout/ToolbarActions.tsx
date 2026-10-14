'use client'

import { useState, useSyncExternalStore } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ModuleMenu } from '@/lib/menu-config'
import type { User } from '@/types/user'
import { MyTodos } from './MyTodos'
import { FeedbackEntry } from './FeedbackEntry'

const subscribe = () => () => {}
const clientReady = () => true
const serverReady = () => false

export function ToolbarActions({ user, modules }: { user: User; modules: ModuleMenu[] }) {
  const [client] = useState(() => new QueryClient())
  const ready = useSyncExternalStore(subscribe, clientReady, serverReady)
  return <QueryClientProvider client={client}>
    <FeedbackEntry user={user} ready={ready} />
    <MyTodos user={user} modules={modules} ready={ready} />
  </QueryClientProvider>
}
