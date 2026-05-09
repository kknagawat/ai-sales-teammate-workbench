import { Badge } from "@/components/ui";
import { humanize, priorityTone, statusTone } from "@/lib/format";
import type { PublicConfig, WorkItemPriority, WorkItemStatus } from "@/lib/types";
import { Bot, CloudCog } from "lucide-react";

export function StatusBadge({ status }: { status: WorkItemStatus }) {
  return <Badge className={statusTone(status)}>{humanize(status)}</Badge>;
}

export function PriorityBadge({ priority }: { priority: WorkItemPriority }) {
  return <Badge className={priorityTone(priority)}>{humanize(priority)}</Badge>;
}

export function ProviderBadge({ config }: { config?: PublicConfig }) {
  const Icon = config?.llm.provider === "anthropic" ? CloudCog : Bot;
  const modeLabel = config?.llm.provider === "anthropic" ? "Claude mode" : "Mock mode";
  return (
    <Badge className="border-moss/20 bg-sage text-moss">
      <Icon className="h-3.5 w-3.5" />
      <span className="ml-1.5">{modeLabel}</span>
      <span className="ml-1.5 text-slate-500">{config?.llm.model_label ?? "AI"}</span>
    </Badge>
  );
}
