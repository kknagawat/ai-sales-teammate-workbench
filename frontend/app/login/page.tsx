"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, Building2, CheckCircle2, Loader2, LockKeyhole, ShieldCheck, UserPlus, UserRound } from "lucide-react";
import { apiFetch, ApiError } from "@/lib/api";
import type { AuthResponse } from "@/lib/types";
import { Button, ErrorNotice, FieldLabel, Panel, TextInput } from "@/components/ui";

const demoAccounts = [
  {
    label: "Acme Reviewer",
    email: "reviewer@acme.example",
    password: "ReviewerPass123!",
    organization_slug: "acme"
  },
  {
    label: "Acme Admin",
    email: "admin@acme.example",
    password: "AdminPass123!",
    organization_slug: "acme"
  },
  {
    label: "Globex Reviewer",
    email: "reviewer@globex.example",
    password: "ReviewerPass123!",
    organization_slug: "globex"
  },
  {
    label: "Globex Admin",
    email: "admin@globex.example",
    password: "AdminPass123!",
    organization_slug: "globex"
  }
];

type AuthMode = "login" | "signup";
type SignupMode = "CREATE_ORG_ADMIN" | "JOIN_ORG_REVIEWER";

export default function LoginPage() {
  const router = useRouter();
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [signupMode, setSignupMode] = useState<SignupMode>("CREATE_ORG_ADMIN");
  const [name, setName] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [email, setEmail] = useState(demoAccounts[0].email);
  const [password, setPassword] = useState(demoAccounts[0].password);
  const [organizationSlug, setOrganizationSlug] = useState(demoAccounts[0].organization_slug);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      if (authMode === "login") {
        await apiFetch<AuthResponse>("/auth/login", {
          method: "POST",
          json: {
            email,
            password,
            organization_slug: organizationSlug || undefined
          }
        });
      } else {
        await apiFetch<AuthResponse>("/auth/signup", {
          method: "POST",
          json: {
            mode: signupMode,
            name,
            email,
            password,
            organization_slug: organizationSlug,
            ...(signupMode === "CREATE_ORG_ADMIN"
              ? { organization_name: organizationName }
              : { invite_code: inviteCode })
          }
        });
      }
      router.push("/queue");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "Authentication failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function chooseMode(nextMode: AuthMode) {
    setAuthMode(nextMode);
    setError(null);
    if (nextMode === "signup") {
      setEmail("");
      setPassword("");
      setOrganizationSlug("");
    } else {
      const account = demoAccounts[0];
      setEmail(account.email);
      setPassword(account.password);
      setOrganizationSlug(account.organization_slug);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-7xl items-center justify-center border-x border-line bg-white px-4 py-10">
      <div className="grid w-full max-w-5xl gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <section className="flex min-h-[560px] flex-col justify-between rounded-[2rem] border border-slate-900 bg-black p-8 text-white shadow-panel">
          <div>
            <div className="inline-flex items-center gap-3 rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm font-semibold">
              <Bot className="h-4 w-4 text-white" />
              Teammates.ai
            </div>
            <h1 className="mt-8 max-w-xl text-5xl font-bold leading-tight tracking-tight">
              AI Sales Teammate Workbench
            </h1>
            <p className="mt-5 max-w-md text-base leading-7 text-slate-300">
              Review autonomous sales follow-ups, inspect decision artifacts, and approve work with a human in control.
            </p>
            <div className="mt-8 inline-flex items-center gap-2 rounded-full bg-moss px-5 py-3 text-sm font-bold text-white shadow-[0_0_28px_rgba(0,71,175,0.35)]">
              <LockKeyhole className="h-4 w-4" />
              Secure reviewer access
            </div>
          </div>
          <div className="grid gap-3 text-sm text-slate-300 sm:grid-cols-3">
            <div className="rounded-2xl border border-white/15 bg-white/5 p-3">Sales</div>
            <div className="rounded-2xl border border-white/15 bg-white/5 p-3">Review</div>
            <div className="rounded-2xl border border-white/15 bg-white/5 p-3">Audit</div>
          </div>
        </section>

        <Panel className="flex min-h-[560px] flex-col justify-center rounded-[2rem]">
          <div className="mb-8">
            <p className="text-sm font-bold uppercase tracking-wide text-moss">
              {authMode === "login" ? "Sign in" : "Sign up"}
            </p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight text-ink">
              {authMode === "login" ? "Reviewer access" : "Create access"}
            </h2>
          </div>

          <div className="mb-5 grid grid-cols-2 rounded-full border border-line bg-slate-50 p-1">
            <button
              type="button"
              onClick={() => chooseMode("login")}
              className={`inline-flex h-10 items-center justify-center gap-2 rounded-full px-3 text-sm font-semibold ${
                authMode === "login" ? "bg-white text-ink shadow-sm" : "text-slate-500"
              }`}
            >
              <UserRound className="h-4 w-4" />
              Sign in
            </button>
            <button
              type="button"
              onClick={() => chooseMode("signup")}
              className={`inline-flex h-10 items-center justify-center gap-2 rounded-full px-3 text-sm font-semibold ${
                authMode === "signup" ? "bg-white text-ink shadow-sm" : "text-slate-500"
              }`}
            >
              <UserPlus className="h-4 w-4" />
              Sign up
            </button>
          </div>

          {authMode === "login" ? (
            <div className="mb-5 grid grid-cols-2 gap-3">
              {demoAccounts.map((account) => (
                <button
                  key={account.email}
                  type="button"
                  onClick={() => {
                    setEmail(account.email);
                    setPassword(account.password);
                    setOrganizationSlug(account.organization_slug);
                  }}
                  className="flex items-center justify-between rounded-2xl border border-line bg-slate-50 px-3 py-3 text-left text-sm font-semibold hover:border-moss/30 hover:bg-sage"
                >
                  <span>{account.label}</span>
                  {email === account.email ? <CheckCircle2 className="h-4 w-4 text-moss" /> : null}
                </button>
              ))}
            </div>
          ) : null}

          {authMode === "signup" ? (
            <div className="mb-5">
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setSignupMode("CREATE_ORG_ADMIN")}
                  className="flex items-center justify-between rounded-2xl border border-line bg-slate-50 px-3 py-3 text-left text-sm font-semibold hover:border-moss/30 hover:bg-sage"
                >
                  <span className="inline-flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4" />
                    Admin
                  </span>
                  {signupMode === "CREATE_ORG_ADMIN" ? (
                    <CheckCircle2 className="h-4 w-4 text-moss" />
                  ) : null}
                </button>
                <button
                  type="button"
                  onClick={() => setSignupMode("JOIN_ORG_REVIEWER")}
                  className="flex items-center justify-between rounded-2xl border border-line bg-slate-50 px-3 py-3 text-left text-sm font-semibold hover:border-moss/30 hover:bg-sage"
                >
                  <span className="inline-flex items-center gap-2">
                    <Building2 className="h-4 w-4" />
                    Reviewer
                  </span>
                  {signupMode === "JOIN_ORG_REVIEWER" ? (
                    <CheckCircle2 className="h-4 w-4 text-moss" />
                  ) : null}
                </button>
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-500">
                Reviewer signup requires an organization invite code.
              </p>
            </div>
          ) : null}

          <form onSubmit={submit} className="space-y-4">
            {authMode === "signup" ? (
              <div>
                <FieldLabel>Name</FieldLabel>
                <TextInput
                  value={name}
                  autoComplete="name"
                  onChange={(event) => setName(event.target.value)}
                />
              </div>
            ) : null}
            {authMode === "signup" && signupMode === "CREATE_ORG_ADMIN" ? (
              <div>
                <FieldLabel>Organization name</FieldLabel>
                <TextInput
                  value={organizationName}
                  autoComplete="organization"
                  onChange={(event) => setOrganizationName(event.target.value)}
                />
              </div>
            ) : null}
            <div>
              <FieldLabel>Email</FieldLabel>
              <TextInput
                value={email}
                type="email"
                autoComplete="username"
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <div>
              <FieldLabel>Password</FieldLabel>
              <TextInput
                value={password}
                type="password"
                autoComplete={authMode === "login" ? "current-password" : "new-password"}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
            <div>
              <FieldLabel>Organization slug</FieldLabel>
              <TextInput
                value={organizationSlug}
                onChange={(event) => setOrganizationSlug(event.target.value)}
              />
            </div>
            {authMode === "signup" && signupMode === "JOIN_ORG_REVIEWER" ? (
              <div>
                <FieldLabel>Invite code</FieldLabel>
                <TextInput
                  value={inviteCode}
                  type="password"
                  autoComplete="one-time-code"
                  onChange={(event) => setInviteCode(event.target.value)}
                />
              </div>
            ) : null}
            {error ? <ErrorNotice message={error} /> : null}
            <Button type="submit" variant="primary" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : authMode === "login" ? (
                <UserRound className="h-4 w-4" />
              ) : (
                <UserPlus className="h-4 w-4" />
              )}
              {authMode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>
        </Panel>
      </div>
    </main>
  );
}
