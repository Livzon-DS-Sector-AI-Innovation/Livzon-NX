export const WORKSPACE_IDENTITY_TRANSITION_KEY = 'dazah.workspace-identity-transition'

export type WorkspaceIdentityArrival = 'opening' | 'restored'
export type WorkspaceIdentityOrigin = { x: number; y: number }

// Register before the first paint so only the explicit identity navigation uses a snapshot.
export const workspaceIdentityTransitionInitScript = `(() => {
  const key = '${WORKSPACE_IDENTITY_TRANSITION_KEY}';
  const root = document.documentElement;
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');

  window.addEventListener('pageswap', event => {
    if (root.dataset.workspaceIdentityDeparting !== 'true' || motion.matches) {
      event.viewTransition?.skipTransition();
    }
    delete root.dataset.workspaceIdentityDeparting;
  });

  window.addEventListener('pagereveal', event => {
    let marker;
    try {
      const stored = sessionStorage.getItem(key);
      if (stored) {
        sessionStorage.removeItem(key);
        marker = JSON.parse(stored);
      }
    } catch {}
    const transition = event.viewTransition;
    if (!transition) return;
    const { arrival, origin } = marker || {};
    if (motion.matches || (arrival !== 'opening' && arrival !== 'restored')) {
      transition.skipTransition();
      return;
    }

    if (arrival === 'restored' && [origin?.x, origin?.y].every(n => Number.isFinite(n) && n >= 0 && n <= 1)) {
      root.style.setProperty('--workspace-identity-origin-x', origin.x * 100 + '%');
      root.style.setProperty('--workspace-identity-origin-y', origin.y * 100 + '%');
    }
    root.dataset.workspaceIdentityTransition = arrival;
    transition.finished.finally(() => {
      delete root.dataset.workspaceIdentityTransition;
      root.style.removeProperty('--workspace-identity-origin-x');
      root.style.removeProperty('--workspace-identity-origin-y');
    });
  });
})();`
