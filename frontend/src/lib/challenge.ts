/**
 * Client-side adaptive challenge (Cloudflare Turnstile) — SINGLE point.
 *
 * `apiFetch` is the only caller: when the backend answers `428 challenge_required`
 * it calls `solveChallenge(sitekey)`, then retries the request once with the
 * `cf-turnstile-response` header. Because every auth/checkout call (and every
 * future protected endpoint) already goes through `apiFetch`, the challenge flow
 * is defined exactly once here — no per-form copy-paste.
 *
 * Env-gated: with no `NEXT_PUBLIC_TURNSTILE_SITE_KEY` (and the backend's secret
 * empty) the backend never returns 428, so this code never runs — zero friction.
 */

const SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
let _scriptPromise: Promise<void> | null = null;

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opts: Record<string, unknown>) => string;
      remove?: (id: string) => void;
    };
  }
}

function loadScript(): Promise<void> {
  if (typeof window === 'undefined') return Promise.reject(new Error('no window'));
  if (window.turnstile) return Promise.resolve();
  if (_scriptPromise) return _scriptPromise;
  _scriptPromise = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = SCRIPT_URL;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('Güvenlik doğrulaması yüklenemedi.'));
    document.head.appendChild(s);
  });
  return _scriptPromise;
}

/**
 * Render a managed/invisible Turnstile widget in a modal and resolve with a token.
 * Most legitimate users pass silently; if interaction is needed the modal is
 * visible with an accessible escape route (support link).
 */
export async function solveChallenge(sitekey: string): Promise<string> {
  await loadScript();
  const turnstile = window.turnstile;
  if (!turnstile) throw new Error('Güvenlik doğrulaması kullanılamıyor.');

  return new Promise<string>((resolve, reject) => {
    const overlay = document.createElement('div');
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Güvenlik doğrulaması');
    // Renk migration (P9.6/D9-08): DOM inline-style → doğrudan CSS var()
    // (canvas değil; runtime çözülür). rgba(2,6,23)/#0f172a 5.-yüzeyler,
    // #e2e8f0/#94a3b8 metinler, #60a5fa 4.-mavi link EMEKLİ → owned token.
    // z-index 9999 → z-tour+ (ad-hoc z temizliği D9-12/P2 kapsamı; renk-fazı dokunmaz).
    overlay.style.cssText =
      'position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:color-mix(in oklab, var(--e0) 70%, transparent)';

    const box = document.createElement('div');
    box.style.cssText =
      'background:var(--e1);color:var(--tx);border:1px solid var(--hl10);border-radius:16px;padding:24px;max-width:340px;text-align:center';
    const title = document.createElement('p');
    title.textContent = 'Güvenlik doğrulaması';
    title.style.cssText = 'font-weight:700;margin:0 0 6px';
    const desc = document.createElement('p');
    desc.textContent = 'Bot olmadığınızı doğrulamak için kısa bir kontrol. Genellikle birkaç saniye sürer.';
    desc.style.cssText = 'font-size:13px;color:var(--tx2);margin:0 0 14px';
    const widget = document.createElement('div');
    widget.style.cssText = 'display:flex;justify-content:center';
    const esc = document.createElement('a');
    esc.href = '/yasal';
    esc.textContent = 'Sorun mu yaşıyorsunuz? Destek / alternatif doğrulama';
    esc.style.cssText = 'display:inline-block;margin-top:14px;font-size:12px;color:var(--accent-ui)';

    box.append(title, desc, widget, esc);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    let settled = false;
    const cleanup = () => {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    };
    const done = (fn: () => void) => {
      if (settled) return;
      settled = true;
      cleanup();
      fn();
    };

    try {
      turnstile.render(widget, {
        sitekey,
        theme: 'dark',
        language: 'auto',
        callback: (token: string) => done(() => resolve(token)),
        'error-callback': () => done(() => reject(new Error('Doğrulama başarısız oldu. Lütfen tekrar deneyin.'))),
        'timeout-callback': () => done(() => reject(new Error('Doğrulama zaman aşımına uğradı. Lütfen tekrar deneyin.'))),
      });
    } catch (e) {
      done(() => reject(e as Error));
    }
  });
}

/** Parse a backend 428 body and return its sitekey when it's a Turnstile challenge. */
export function challengeSitekey(detail: unknown): string | null {
  if (detail && typeof detail === 'object') {
    const d = detail as Record<string, unknown>;
    if (d.error === 'challenge_required' && d.challenge === 'turnstile') {
      const sk = (d.sitekey as string) || process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || '';
      return sk || null;
    }
  }
  return null;
}
