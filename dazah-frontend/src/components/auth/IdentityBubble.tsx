'use client'

import styles from './IdentityBubble.module.css'

export type IdentityBubbleState =
  | 'idle'
  | 'launching'
  | 'checking'
  | 'ready'
  | 'entering'
  | 'error'

interface IdentityBubbleProps {
  state: IdentityBubbleState
  statusText: string
  detailText?: string
  identityText?: string
  onActivate?: () => void
  disabled?: boolean
}

export function IdentityBubble({
  state,
  statusText,
  detailText,
  identityText,
  onActivate,
  disabled = false,
}: IdentityBubbleProps) {
  const interactive = Boolean(onActivate) && !disabled

  return (
    <div className={styles.identityControl} data-state={state}>
      <div className={styles.bubbleFrame}>
        <button
          type="button"
          className={styles.bubble}
          onClick={onActivate}
          disabled={!interactive}
          aria-label={interactive ? statusText : undefined}
          aria-describedby={detailText ? 'identity-bubble-detail' : undefined}
        >
          <span className={styles.checkpointMark} aria-hidden="true" />
          <span className={styles.bubbleContent}>
            {identityText && (
              <span className={styles.identityText}>{identityText}</span>
            )}
            <span className={styles.statusText}>{statusText}</span>
          </span>
        </button>
      </div>

      {detailText && (
        <p id="identity-bubble-detail" className={styles.detailText}>
          {detailText}
        </p>
      )}
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {statusText}
      </span>
    </div>
  )
}
