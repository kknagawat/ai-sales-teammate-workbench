"use client";

import { forwardRef } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/format";

export function Badge({
  children,
  className
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex min-h-7 items-center rounded-full border px-3 py-1 text-xs font-semibold",
        className
      )}
    >
      {children}
    </span>
  );
}

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }
>(function Button({ className, variant = "secondary", ...props }, ref) {
  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-full border px-4 text-sm font-semibold tracking-tight transition disabled:cursor-not-allowed disabled:opacity-45",
        variant === "primary" && "border-moss bg-moss text-white shadow-sm hover:bg-[#003a8c] hover:shadow-[0_0_18px_rgba(0,71,175,0.22)]",
        variant === "secondary" && "border-line bg-white text-ink shadow-sm hover:border-slate-300 hover:bg-slate-50",
        variant === "danger" && "border-coral bg-coral text-white hover:bg-[#be123c]",
        className
      )}
      {...props}
    />
  );
});

export const IconButton = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { label: string }
>(function IconButton({ label, className, children, ...props }, ref) {
  return (
    <button
      ref={ref}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-10 w-10 items-center justify-center rounded-full border border-line bg-white text-ink shadow-sm transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-45",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
});

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function TextInput({ className, ...props }, ref) {
    return (
      <input
        ref={ref}
        className={cn(
          "h-11 w-full rounded-xl border border-line bg-white px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-moss focus:ring-4 focus:ring-sage",
          className
        )}
        {...props}
      />
    );
  }
);

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function TextArea({ className, ...props }, ref) {
    return (
      <textarea
        ref={ref}
        className={cn(
          "w-full rounded-xl border border-line bg-white px-3 py-3 text-sm leading-6 outline-none transition placeholder:text-slate-400 focus:border-moss focus:ring-4 focus:ring-sage",
          className
        )}
        {...props}
      />
    );
  }
);

export function Panel({
  title,
  action,
  children,
  className
}: {
  title?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-2xl border border-line bg-white p-5 shadow-panel", className)}>
      {(title || action) && (
        <div className="mb-4 flex min-h-8 items-center justify-between gap-3">
          {title ? <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500">{title}</h2> : <span />}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-line bg-white px-6 py-12 text-center">
      <p className="text-base font-semibold text-ink">{title}</p>
      {detail ? <p className="mt-2 text-sm text-slate-500">{detail}</p> : null}
    </div>
  );
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-coral/20 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
      {message}
    </div>
  );
}

export function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-500">{children}</label>;
}
