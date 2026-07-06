import React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import clsx from "clsx";

interface TooltipProps {
  children: React.ReactNode;
  content: React.ReactNode;
  className?: string;
  delayDuration?: number;
}

export const Tooltip: React.FC<TooltipProps> = ({
  children,
  content,
  className,
  delayDuration = 200,
}) => {
  return (
    <TooltipPrimitive.Provider delayDuration={delayDuration}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>
          {children}
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            sideOffset={4}
            className={clsx(
              "z-50 overflow-hidden rounded-md border border-border-medium bg-e-3 px-3 py-1.5 text-xs text-text-primary shadow-e3 animate-scale-in",
              className
            )}
          >
            {content}
            <TooltipPrimitive.Arrow className="fill-border-medium" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
};
export default Tooltip;
