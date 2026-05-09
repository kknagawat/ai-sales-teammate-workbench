import { clsx, type ClassValue } from "clsx";
import type { WorkItemPriority, WorkItemStatus } from "./types";

export function cn(...values: ClassValue[]) {
  return clsx(values);
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "Not set";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(new Date(value));
}

export function humanize(value: string) {
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function statusTone(status: WorkItemStatus) {
  switch (status) {
    case "PENDING_REVIEW":
      return "border-amber/30 bg-amber-50 text-amber-700";
    case "REGENERATING":
      return "border-moss/25 bg-sage text-moss";
    case "PROCESSING":
      return "border-moss/25 bg-sage text-moss";
    case "SENT":
      return "border-[#10b981]/30 bg-[#ecfdf5] text-[#047857]";
    case "FAILED":
      return "border-coral/30 bg-[#fff1f2] text-[#be123c]";
    case "REJECTED":
      return "border-slate-300 bg-slate-100 text-slate-700";
  }
}

export function priorityTone(priority: WorkItemPriority) {
  switch (priority) {
    case "URGENT":
      return "border-coral/30 bg-[#fff1f2] text-[#be123c]";
    case "HIGH":
      return "border-amber/30 bg-amber-50 text-amber-700";
    case "MEDIUM":
      return "border-moss/25 bg-sage text-moss";
    case "LOW":
      return "border-line bg-white text-slate-500";
  }
}

export function isTransient(status: WorkItemStatus) {
  return status === "PROCESSING" || status === "REGENERATING";
}

export function canReview(status: WorkItemStatus) {
  return status === "PENDING_REVIEW" || status === "FAILED";
}

export function getString(value: unknown, fallback = "Not available") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

export function getStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}
