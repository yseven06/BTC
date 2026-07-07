"use client";

import React from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, Check } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Kanonik Dropdown primitifi (Bible §01 INT-07) — native <select> yerine.
 * E3 cam panel (.glass-e3-overlay: E3 + backdrop-blur 8–10px + hairline --hl22
 * + shadow-e3) + açılış üstten-düşüş (animate-slide-down / slideDown, --dur-overlay)
 * + klavye gezinme (ok tuşları / typeahead) + ESC + focus yönetimi (Radix
 * DropdownMenu) + z-dropdown (40). Tek-değer seçimi RadioGroup + RadioItem ile
 * (kontrollü value/onValueChange). Yeni görsel dil YOK — yalnız mevcut token
 * tüketimi. Tetikleyici className ile göç sitesine hizalanabilir.
 */

export interface DropdownOption {
  value: string;
  label: React.ReactNode;
}

interface DropdownProps {
  value: string;
  onValueChange: (value: string) => void;
  options: DropdownOption[];
  placeholder?: string;
  disabled?: boolean;
  /** Tetikleyici için erişilebilir isim (görünür etiket yoksa). */
  ariaLabel?: string;
  /** Tetikleyici className — göç sitesindeki select sınıflarıyla hizalamak için. */
  className?: string;
  /** İçerik (panel) className override. */
  contentClassName?: string;
  align?: "start" | "center" | "end";
}

export function Dropdown({
  value,
  onValueChange,
  options,
  placeholder = "Seç…",
  disabled,
  ariaLabel,
  className,
  contentClassName,
  align = "start",
}: DropdownProps) {
  const selected = options.find((o) => o.value === value);

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        disabled={disabled}
        aria-label={ariaLabel}
        className={cn(
          "inline-flex items-center justify-between gap-2 rounded-control border border-[var(--hl12)] bg-e-2 px-3 py-2 text-sm text-text-primary outline-none focus-ring transition-[border-color] duration-micro hover:border-[var(--hl22)] data-[state=open]:border-[var(--hl22)] disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
      >
        <span className={cn("truncate", !selected && "text-text-muted")}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-text-muted" aria-hidden />
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align={align}
          sideOffset={4}
          className={cn(
            "glass-e3-overlay rounded-control z-dropdown min-w-[var(--radix-dropdown-menu-trigger-width)] max-h-[var(--radix-dropdown-menu-content-available-height)] overflow-y-auto p-1 outline-none",
            "motion-safe:data-[state=open]:animate-slide-down",
            contentClassName
          )}
        >
          <DropdownMenu.RadioGroup value={value} onValueChange={onValueChange}>
            {options.map((o) => (
              <DropdownMenu.RadioItem
                key={o.value}
                value={o.value}
                className="flex cursor-pointer select-none items-center justify-between gap-3 rounded-control px-3 py-1.5 text-sm text-text-primary outline-none transition-colors duration-micro data-[highlighted]:bg-e-2 data-[state=checked]:text-accent-ui"
              >
                <span className="truncate">{o.label}</span>
                <DropdownMenu.ItemIndicator>
                  <Check className="h-3.5 w-3.5 shrink-0 text-accent-ui" aria-hidden />
                </DropdownMenu.ItemIndicator>
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

export default Dropdown;
