'use client';

import React, { useEffect, useRef, useState } from 'react';
import { X, Download, Share2 } from 'lucide-react';
import { formatUsd, formatQuantity, formatPrice, formatPercentage, formatDateTR } from '@/lib/utils';

export interface ShareCardData {
  symbol: string;
  assetName: string;
  isClosed: boolean;
  entryPrice: number;
  /** Current live price if open, exit price if closed. */
  refPrice: number;
  quantity: number;
  pnlPct: number;
  pnlAmount: number;
  closedAt?: string | null;
}

import { chartColor, withAlpha } from '@/lib/chartColors';

const CARD_SIZE = 1080;

/** Draws the share card onto a canvas. Pure Canvas 2D — no extra dependencies. */
async function drawCard(canvas: HTMLCanvasElement, data: ShareCardData) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  canvas.width = CARD_SIZE;
  canvas.height = CARD_SIZE;

  const win = data.pnlPct >= 0;
  // Renk migration (P9.6/D9-08): owned tek-kaynak (chartColors runtime-resolve).
  const green = chartColor('bull');
  const red = chartColor('bear');
  const tx = chartColor('tx'), tx2 = chartColor('tx2'), tx3 = chartColor('tx3');
  const hl16 = chartColor('hl16');
  const accent = win ? green : red;

  // Background
  const bg = ctx.createLinearGradient(0, 0, CARD_SIZE, CARD_SIZE);
  bg.addColorStop(0, chartColor('e0'));
  bg.addColorStop(1, chartColor('e2'));
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, CARD_SIZE, CARD_SIZE);

  // Subtle glow blob behind the P&L number
  const glow = ctx.createRadialGradient(CARD_SIZE / 2, 520, 50, CARD_SIZE / 2, 520, 420);
  glow.addColorStop(0, withAlpha(win ? green : red, 0.18));
  glow.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, CARD_SIZE, CARD_SIZE);

  // Logo
  try {
    const logo = await loadImage('/logo-icon-square.png');
    ctx.drawImage(logo, 64, 64, 84, 84);
  } catch { /* logo missing — skip silently */ }

  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = tx;
  ctx.font = '700 40px Arial';
  ctx.fillText('TRADEMINDS AI', 164, 100);
  ctx.fillStyle = tx2;
  ctx.font = '400 22px Arial';
  ctx.fillText('AI Trading Intelligence', 164, 130);

  // Status badge (top right)
  const badgeText = data.isClosed ? 'KAPANDI' : 'AÇIK POZİSYON';
  ctx.font = '700 24px Arial';
  const badgeW = ctx.measureText(badgeText).width + 56;
  const badgeX = CARD_SIZE - 64 - badgeW;
  roundRect(ctx, badgeX, 60, badgeW, 48, 24);
  ctx.fillStyle = data.isClosed ? hl16 : withAlpha(green, 0.15);
  ctx.fill();
  ctx.fillStyle = data.isClosed ? tx2 : green;
  ctx.fillText(badgeText, badgeX + 28, 91);
  if (!data.isClosed) {
    ctx.beginPath();
    ctx.arc(badgeX + 16, 84, 6, 0, Math.PI * 2);
    ctx.fillStyle = green;
    ctx.fill();
  }

  // Symbol + direction
  ctx.fillStyle = tx;
  ctx.font = '800 76px Arial';
  ctx.fillText(data.symbol, 64, 260);
  ctx.font = '600 28px Arial';
  ctx.fillStyle = tx2;
  ctx.fillText(data.assetName, 64, 300);

  ctx.font = '700 26px Arial';
  ctx.fillStyle = green;
  roundRect(ctx, 64, 320, 130, 46, 8);
  ctx.fillStyle = withAlpha(green, 0.15);
  ctx.fill();
  ctx.fillStyle = green;
  ctx.fillText('LONG', 96, 352);

  // Big PnL %
  const pnlText = formatPercentage(data.pnlPct);
  ctx.font = '800 190px Arial';
  ctx.fillStyle = accent;
  ctx.fillText(pnlText, 64, 620);

  // PnL amount
  const amountText = `${win ? '+' : ''}${formatUsd(Math.abs(data.pnlAmount))}`;
  ctx.font = '600 44px Arial';
  ctx.fillStyle = tx;
  ctx.fillText(amountText, 68, 680);

  // Divider
  ctx.strokeStyle = hl16;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(64, 740);
  ctx.lineTo(CARD_SIZE - 64, 740);
  ctx.stroke();

  // Stats row: Entry / Exit-or-Current / Quantity
  const statY = 800;
  const cols = [
    { label: 'GİRİŞ FİYATI', value: formatPrice(data.entryPrice) },
    { label: data.isClosed ? 'ÇIKIŞ FİYATI' : 'ANLIK FİYAT', value: formatPrice(data.refPrice) },
    { label: 'MİKTAR', value: formatQuantity(data.quantity) },
  ];
  const colWidth = (CARD_SIZE - 128) / 3;
  cols.forEach((c, i) => {
    const x = 64 + i * colWidth;
    ctx.font = '600 22px Arial';
    ctx.fillStyle = tx3;
    ctx.fillText(c.label, x, statY);
    ctx.font = '700 36px Arial';
    ctx.fillStyle = tx;
    ctx.fillText(c.value, x, statY + 46);
  });

  // Footer
  ctx.font = '500 22px Arial';
  ctx.fillStyle = tx3;
  const footerText = data.isClosed && data.closedAt
    ? `Kapanış: ${formatDateTR(data.closedAt)}`
    : 'TradeMinds AI ile kendi pozisyonunu takip et';
  ctx.fillText(footerText, 64, CARD_SIZE - 64);
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

export function ShareCardModal({ data, onClose }: { data: ShareCardData; onClose: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (canvasRef.current) {
      drawCard(canvasRef.current, data).then(() => setReady(true));
    }
  }, [data]);

  const download = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trademinds-${data.symbol.toLowerCase()}-${data.isClosed ? 'kapali' : 'acik'}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }, 'image/png');
  };

  const share = async () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob(async (blob) => {
      if (!blob) return;
      const file = new File([blob], `trademinds-${data.symbol.toLowerCase()}.png`, { type: 'image/png' });
      if (navigator.share && navigator.canShare?.({ files: [file] })) {
        try {
          await navigator.share({ files: [file], title: 'TradeMinds AI', text: `${data.symbol} pozisyonum` });
          return;
        } catch { /* user canceled or unsupported — fall back to download */ }
      }
      download();
    }, 'image/png');
  };

  return (
    <div className="fixed inset-0 z-50 bg-e-0/70 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-bg-secondary border border-border-subtle rounded-2xl p-5 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-text-primary">Paylaşım Kartı</h3>
          <button onClick={onClose} className="p-1 text-text-muted hover:text-bearish"><X className="w-4 h-4" /></button>
        </div>
        <div className="rounded-xl overflow-hidden border border-border-subtle bg-bg-primary">
          <canvas ref={canvasRef} className="w-full h-auto block" />
          {!ready && (
            <div className="flex justify-center py-20">
              <div className="w-6 h-6 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 mt-4">
          <button onClick={download} className="flex-1 flex items-center justify-center gap-1.5 text-sm font-semibold bg-bg-tertiary text-text-primary px-4 py-2.5 rounded-xl hover:bg-bg-tertiary/70 transition-colors">
            <Download className="w-4 h-4" /> İndir
          </button>
          <button onClick={share} className="flex-1 flex items-center justify-center gap-1.5 text-sm font-semibold bg-accent-primary text-white px-4 py-2.5 rounded-xl hover:bg-accent-hover transition-colors">
            <Share2 className="w-4 h-4" /> Paylaş
          </button>
        </div>
      </div>
    </div>
  );
}
