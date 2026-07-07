"use client";

import React from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";

interface ConfirmModalProps {
  open: boolean;
  title?: string;
  message: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Onay butonu türü: yıkıcı işlemler için 'danger' (varsayılan), diğer için 'primary'. */
  variant?: "danger" | "primary";
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Kanonik onay diyaloğu (Bible §01 INT-10) — native window.confirm() yerine.
 * ui/Modal kabuğu (portal + focus-trap + ESC + E3) + ui/Button (INT-03) üzerine
 * kurulu; yıkıcı işlemlerde variant='danger'. İşlem sürerken loading → dismiss
 * kapalı + onay butonu sönük.
 */
export function ConfirmModal({
  open,
  title = "Emin misin?",
  message,
  confirmLabel = "Onayla",
  cancelLabel = "Vazgeç",
  variant = "danger",
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      dismissible={!loading}
      title={title}
      size="max-w-sm"
      footer={
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button variant={variant} size="sm" onClick={onConfirm} isLoading={loading}>
            {confirmLabel}
          </Button>
        </div>
      }
    >
      <p className="text-sm text-text-secondary">{message}</p>
    </Modal>
  );
}

export default ConfirmModal;
