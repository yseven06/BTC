import React from 'react';
import { notFound } from 'next/navigation';
import { Karot } from '@/components/signals/Karot';
import { REST_STATE, ENGINES } from '@/lib/karot-geometry';

/**
 * Karot görsel-QA harness (DEV-ONLY) — Bible §05 v1.4 statik primitif.
 * 5 hal × 3 ölçek + loading + highlight. Geometry-Freeze (karot-15) regresyon
 * yüzeyi: yabancı-kör okunabilirlik burada denetlenir. Prod'da erişilemez.
 */

const BULL = REST_STATE;
const BEAR = REST_STATE.map((x) => -x);
const SPLIT = [0.5, 0.3, -0.4, 0.2, -0.5, 0.35, -0.3, 0.25, -0.2];
const WEAK = [0.1, -0.08, 0.12, -0.05, 0.09, 0.06, -0.1, 0.04, 0.07];

const STATES: { label: string; confs: readonly number[]; loading?: boolean }[] = [
  { label: 'Uzlaşma · bull', confs: BULL },
  { label: 'Uzlaşma · bear', confs: BEAR },
  { label: 'Bölünmüş', confs: SPLIT },
  { label: 'Kararsız', confs: WEAK },
  { label: 'Loading', confs: BULL, loading: true },
];
const SIZES = [16, 48, 200];

const cell: React.CSSProperties = {
  background: 'var(--e1)',
  border: '1px solid var(--hl12)',
  borderRadius: 12,
  padding: 16,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  gap: 10,
};
const lbl: React.CSSProperties = {
  fontFamily: 'ui-monospace, monospace',
  fontSize: 10,
  letterSpacing: '0.06em',
  color: 'var(--tx3)',
  textTransform: 'uppercase',
};

export default function KarotLabPage() {
  if (process.env.NODE_ENV === 'production') notFound();

  return (
    <div style={{ background: 'var(--e0)', color: 'var(--tx)', minHeight: '100vh', padding: 40 }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        <div style={lbl}>Karot · Görsel-QA Harness · Bible §05 v1.4 (DEV)</div>
        <h1 style={{ fontSize: 24, fontWeight: 750, margin: '6px 0 4px' }}>
          Fitilli Omurga — statik primitif
        </h1>
        <p style={{ color: 'var(--tx2)', fontSize: 13, maxWidth: '70ch', margin: 0 }}>
          5 hal × 3 ölçek (16 silüet=3-küme · 48 kart · 200 hero). Fitiller=slate kanıt,
          omurga+karar-ucu=cyan (yalnız Uzlaşma), tint fill-opacity .14, bölünmüş çift-nokta,
          kararsız/loading tx3. Cyan-bütçe: bir Karot'ta cyan yalnız omurga+karar-ucu.
        </p>

        {/* 5 hal × 3 ölçek matrisi */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: `120px repeat(${SIZES.length}, 1fr)`,
            gap: 12,
            marginTop: 28,
            alignItems: 'end',
          }}
        >
          <div />
          {SIZES.map((s) => (
            <div key={`h${s}`} style={{ ...lbl, textAlign: 'center' }}>{s}px</div>
          ))}
          {STATES.map((st) => (
            <React.Fragment key={st.label}>
              <div style={{ ...lbl, textTransform: 'none', fontSize: 12, color: 'var(--tx2)' }}>
                {st.label}
              </div>
              {SIZES.map((s) => (
                <div key={`${st.label}-${s}`} style={cell}>
                  <Karot confs={st.confs} size={s} loading={st.loading} title={`${st.label} ${s}px`} />
                </div>
              ))}
            </React.Fragment>
          ))}
        </div>

        {/* highlight (AI-Thought çapraz-vurgu) */}
        <h2 style={{ fontSize: 16, margin: '36px 0 12px' }}>Highlight — SMC (slot 2) vurgusu</h2>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <div style={cell}>
            <Karot confs={BULL} size={200} highlight={2} title="Highlight 200" />
            <span style={lbl}>200 · SMC vurgulu</span>
          </div>
          <div style={cell}>
            <Karot confs={BULL} size={48} highlight={2} title="Highlight 48" />
            <span style={lbl}>48 · SMC vurgulu</span>
          </div>
        </div>

        {/* dashboard satır simülasyonu (16px hizası) */}
        <h2 style={{ fontSize: 16, margin: '36px 0 12px' }}>Dashboard satır hizası (omurga-rayı)</h2>
        <div style={{ background: 'var(--e1)', border: '1px solid var(--hl12)', borderRadius: 12, padding: 8, maxWidth: 420 }}>
          {STATES.filter((s) => !s.loading).map((st) => (
            <div
              key={`row-${st.label}`}
              style={{
                display: 'grid',
                gridTemplateColumns: 'auto 1fr auto',
                gap: 12,
                alignItems: 'center',
                padding: '8px 10px',
                borderBottom: '1px solid var(--hl10)',
              }}
            >
              <Karot confs={st.confs} size={18} title={st.label} />
              <span style={{ fontSize: 12, fontWeight: 600 }}>{st.label}</span>
              <span style={{ ...lbl }}>{ENGINES.length} motor</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
