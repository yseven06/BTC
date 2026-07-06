import React from "react";
import clsx from "clsx";
import { FolderOpen } from "lucide-react";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  className,
}) => {
  return (
    <div
      className={clsx(
        "flex flex-col items-center justify-center p-8 text-center rounded-xl border border-dashed border-border-medium bg-e-1",
        className
      )}
    >
      <div className="flex items-center justify-center w-12 h-12 rounded-full bg-bg-tertiary border border-border-subtle text-text-muted mb-4">
        {icon || <FolderOpen className="w-6 h-6 text-accent-primary" />}
      </div>
      <h3 className="text-base font-bold text-text-primary mb-1">{title}</h3>
      <p className="text-xs text-text-secondary max-w-[280px] mb-4">{description}</p>
      {action && <div className="flex justify-center">{action}</div>}
    </div>
  );
};
export default EmptyState;
