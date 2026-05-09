from copy import deepcopy
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, update

from app.audit import actions
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.sync_session import sync_session_factory
from app.models.audit_log import AuditLog
from app.models.background_job import BackgroundJob
from app.models.enums import (
    BackgroundJobStatus,
    LLMProvider,
    LLMProviderMode,
    LLMRequestType,
    LLMRunStatus,
    UserRole,
    WorkItemPriority,
    WorkItemStatus,
)
from app.models.idempotency_key import IdempotencyKey
from app.models.lead_work_item import LeadWorkItem
from app.models.llm_generation_run import LLMGenerationRun
from app.models.organization import Organization
from app.models.user import User
from app.schemas.lead_profile import LeadProfile

SEED_PASSWORDS = {
    "admin@acme.example": "AdminPass123!",
    "reviewer@acme.example": "ReviewerPass123!",
    "backup.reviewer@acme.example": "ReviewerPass123!",
    "inactive@acme.example": "InactivePass123!",
    "admin@globex.example": "AdminPass123!",
    "reviewer@globex.example": "ReviewerPass123!",
    "backup.reviewer@globex.example": "ReviewerPass123!",
    "inactive@globex.example": "InactivePass123!",
}

ACTIVE_DEMO_EMAILS = (
    "admin@acme.example",
    "reviewer@acme.example",
    "backup.reviewer@acme.example",
    "admin@globex.example",
    "reviewer@globex.example",
    "backup.reviewer@globex.example",
)


def _dt(days_ago: int, hour: int = 10) -> datetime:
    base = datetime(2026, 5, 9, hour, 0, tzinfo=UTC)
    return base - timedelta(days=days_ago)


def _profile(
    *,
    first_name: str,
    last_name: str,
    email: str,
    title: str,
    seniority: str,
    department: str,
    company_name: str,
    domain: str,
    industry: str,
    size_band: str,
    region: str,
    business_model: str,
    source: str,
    event_type: str,
    days_ago: int,
    summary: str,
    raw_message: str,
    buying_stage: str,
    intent_score: int,
    fit_score: int,
    urgency: str,
    pain_points: list[str],
    outcomes: list[str],
    offer: str,
    tone: str,
    cta_type: str,
    suggested_cta: str,
    owner_name: str,
) -> dict:
    event_at = _dt(days_ago)
    payload = {
        "contact": {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": "+1-555-0100",
            "title": title,
            "seniority": seniority,
            "department": department,
            "linkedin_url": f"https://linkedin.example/in/{first_name.lower()}-{last_name.lower()}",
            "timezone": "America/New_York",
        },
        "company": {
            "name": company_name,
            "domain": domain,
            "industry": industry,
            "size_band": size_band,
            "region": region,
            "funding_stage": "Series B" if size_band in {"51-200", "201-1000"} else None,
            "tech_stack": ["Salesforce", "HubSpot", "Slack"],
            "business_model": business_model,
        },
        "source_signal": {
            "source": source,
            "event_type": event_type,
            "event_at": event_at,
            "summary": summary,
            "raw_message": raw_message,
            "utm_source": "linkedin",
            "utm_campaign": "ai-sales-workbench",
        },
        "qualification": {
            "buying_stage": buying_stage,
            "intent_score": intent_score,
            "fit_score": fit_score,
            "urgency": urgency,
            "pain_points": pain_points,
            "desired_outcomes": outcomes,
            "objections": ["Needs security review"] if intent_score > 80 else [],
            "recommended_offer": offer,
        },
        "conversation_context": {
            "last_interaction_summary": summary,
            "known_preferences": ["Concise examples", "Operational detail"],
            "previous_touchpoints": [
                {
                    "channel": source,
                    "occurred_at": event_at,
                    "summary": summary,
                }
            ],
            "do_not_mention": ["unverified customer names"],
            "tone_guidance": tone,
        },
        "personalization": {
            "opening_angle": (
                f"Reference {source.lower()} signal and {company_name}'s current priority."
            ),
            "relevance_hooks": [summary, *pain_points[:2]],
            "proof_points": ["Human review workflow", "Audit trail", "Async processing"],
            "cta_type": cta_type,
            "suggested_cta": suggested_cta,
        },
        "crm": {
            "external_lead_id": f"lead_{first_name.lower()}_{last_name.lower()}",
            "owner_name": owner_name,
            "lifecycle_stage": "Marketing Qualified Lead",
            "last_touch_at": event_at - timedelta(days=1),
            "next_best_action": offer,
        },
    }
    return LeadProfile.model_validate(payload).model_dump(mode="json")


def _generation_result(profile: dict) -> dict:
    contact = profile["contact"]
    company = profile["company"]
    qualification = profile["qualification"]
    personalization = profile["personalization"]
    subject = f"Following up on {company['name']}'s AI teammate goals"
    body = (
        f"Hi {contact['first_name']},\n\n"
        f"Thanks for the context around {qualification['pain_points'][0].lower()}. "
        "It sounds like your team is looking for a safer way to let AI draft sales "
        "follow-ups while keeping a human reviewer in control.\n\n"
        "A practical next step would be to map one high-intent lead flow and show how "
        "the teammate drafts, explains, and records each action before anything is sent.\n\n"
        f"{personalization['suggested_cta']}\n\n"
        "Best,\nMira"
    )
    return {
        "subject": subject,
        "email_body": body,
        "preview_text": body.split("\n\n")[1][:140],
        "decision_trace": {
            "summary": (
                f"Used {profile['source_signal']['source']} intent and buying stage "
                "to prioritize a clear CTA."
            ),
            "selected_strategy": "Consultative follow-up with proof of human control.",
            "audience_assessment": (
                f"{contact['title']} likely cares about adoption, risk, and speed."
            ),
            "buying_stage_assessment": qualification["buying_stage"],
            "personalization_used": personalization["relevance_hooks"],
            "lead_signals_used": [profile["source_signal"]["summary"]],
            "pain_points_addressed": qualification["pain_points"],
            "objections_handled": qualification["objections"],
            "alternatives_considered": ["Send a case study", "Ask for budget timing"],
            "risk_flags": ["Avoid naming unverified customers"],
            "why_this_cta": personalization["suggested_cta"],
        },
        "quality_checks": {
            "is_personalized": True,
            "mentions_unverified_claims": False,
            "has_clear_cta": True,
            "tone_matches_guidance": True,
            "includes_sensitive_data": False,
            "hallucination_risk": "low",
            "notes": ["Grounded in provided lead signal and CRM context."],
        },
        "recommended_next_action": personalization["suggested_cta"],
        "confidence": "high" if qualification["intent_score"] >= 80 else "medium",
    }


def _scenario_data() -> list[dict]:
    return [
        {
            "org": "acme",
            "status": WorkItemStatus.PENDING_REVIEW,
            "priority": WorkItemPriority.URGENT,
            "regeneration_runs": 2,
            "profile": _profile(
                first_name="Avery",
                last_name="Shah",
                email="avery.shah@example.com",
                title="VP Sales",
                seniority="VP",
                department="Sales",
                company_name="Northstar Systems",
                domain="northstar.example",
                industry="SaaS",
                size_band="201-1000",
                region="North America",
                business_model="B2B",
                source="Demo Request",
                event_type="DemoRequested",
                days_ago=1,
                summary="Requested a demo after reviewing AI sales follow-up workflows.",
                raw_message=(
                    "We want to understand how AI teammates can help reps follow up faster."
                ),
                buying_stage="ReadyToBuy",
                intent_score=94,
                fit_score=91,
                urgency="High",
                pain_points=["Slow lead response", "Inconsistent rep follow-up"],
                outcomes=["Shorter response time", "Consistent human-approved messaging"],
                offer="Book a 30-minute workflow mapping call",
                tone="Executive",
                cta_type="BookMeeting",
                suggested_cta="Would Tuesday or Wednesday work for a 30-minute walkthrough?",
                owner_name="Mira Patel",
            ),
        },
        {
            "org": "acme",
            "status": WorkItemStatus.PENDING_REVIEW,
            "priority": WorkItemPriority.HIGH,
            "assigned_to": "backup_reviewer",
            "profile": _profile(
                first_name="Leo",
                last_name="Martinez",
                email="leo.martinez@example.com",
                title="Founder",
                seniority="FOUNDER",
                department="Executive",
                company_name="RelayStack",
                domain="relaystack.example",
                industry="Developer Tools",
                size_band="11-50",
                region="North America",
                business_model="B2B",
                source="Website",
                event_type="PricingViewed",
                days_ago=2,
                summary="Returned to the pricing page three times this week.",
                raw_message="Viewed pricing tiers and implementation FAQ.",
                buying_stage="Evaluation",
                intent_score=86,
                fit_score=83,
                urgency="High",
                pain_points=["Founder-led sales follow-up", "Limited sales operations capacity"],
                outcomes=["Automate first-pass follow-up", "Keep founder approval on key notes"],
                offer="Send a focused startup implementation path",
                tone="Concise",
                cta_type="ReplyWithContext",
                suggested_cta="Worth a quick reply with your current lead volume?",
                owner_name="Mira Patel",
            ),
        },
        {
            "org": "acme",
            "status": WorkItemStatus.PENDING_REVIEW,
            "priority": WorkItemPriority.HIGH,
            "profile": _profile(
                first_name="Priya",
                last_name="Nair",
                email="priya.nair@example.com",
                title="RevOps Manager",
                seniority="MANAGER",
                department="Revenue Operations",
                company_name="MetricLoop",
                domain="metricloop.example",
                industry="Analytics",
                size_band="51-200",
                region="EMEA",
                business_model="B2B",
                source="Webinar",
                event_type="WebinarAttended",
                days_ago=3,
                summary="Attended webinar on AI-assisted pipeline operations.",
                raw_message="Asked about auditability and handoff to CRM.",
                buying_stage="Consideration",
                intent_score=77,
                fit_score=88,
                urgency="Medium",
                pain_points=["Manual QA of follow-up emails", "CRM activity gaps"],
                outcomes=["Improve QA coverage", "Sync approved actions to CRM"],
                offer="Share an audit trail demo",
                tone="Technical",
                cta_type="ViewResource",
                suggested_cta="Can I send over a two-minute audit trail walkthrough?",
                owner_name="Mira Patel",
            ),
        },
        {
            "org": "acme",
            "status": WorkItemStatus.PENDING_REVIEW,
            "priority": WorkItemPriority.HIGH,
            "profile": _profile(
                first_name="Morgan",
                last_name="Chen",
                email="morgan.chen@example.com",
                title="Head of Customer Support",
                seniority="DIRECTOR",
                department="Customer Support",
                company_name="BrightDesk",
                domain="brightdesk.example",
                industry="Customer Support",
                size_band="1000+",
                region="North America",
                business_model="B2B",
                source="Intent Data",
                event_type="CompetitorCompared",
                days_ago=4,
                summary="Compared AI teammate features against a support automation competitor.",
                raw_message="High-intent comparison page visit from enterprise account.",
                buying_stage="Evaluation",
                intent_score=82,
                fit_score=79,
                urgency="Medium",
                pain_points=["Support follow-up backlog", "Complex approval policies"],
                outcomes=["Configurable human review", "Reliable audit history"],
                offer="Offer an enterprise workflow review",
                tone="Consultative",
                cta_type="BookMeeting",
                suggested_cta="Open to comparing review workflows next week?",
                owner_name="Mira Patel",
            ),
        },
        {
            "org": "acme",
            "status": WorkItemStatus.PENDING_REVIEW,
            "priority": WorkItemPriority.MEDIUM,
            "profile": _profile(
                first_name="Sam",
                last_name="Okafor",
                email="sam.okafor@example.com",
                title="Growth Lead",
                seniority="DIRECTOR",
                department="Growth",
                company_name="MarketSquare",
                domain="marketsquare.example",
                industry="Marketplace",
                size_band="201-1000",
                region="APAC",
                business_model="Marketplace",
                source="Product Signup",
                event_type="ProductSignup",
                days_ago=5,
                summary="Created a product workspace and invited two teammates.",
                raw_message="Signup event included marketplace growth operations role.",
                buying_stage="Awareness",
                intent_score=68,
                fit_score=85,
                urgency="Medium",
                pain_points=["High-volume seller follow-up", "Need consistent outreach quality"],
                outcomes=["Review generated outreach", "Scale follow-up experiments"],
                offer="Ask about the first workflow they want to automate",
                tone="Warm",
                cta_type="ReplyWithContext",
                suggested_cta="What follow-up workflow would be most useful to test first?",
                owner_name="Mira Patel",
            ),
        },
        {
            "org": "acme",
            "status": WorkItemStatus.PENDING_REVIEW,
            "priority": WorkItemPriority.HIGH,
            "profile": _profile(
                first_name="Elena",
                last_name="Brooks",
                email="elena.brooks@example.com",
                title="COO",
                seniority="CXO",
                department="Operations",
                company_name="CloudHarbor",
                domain="cloudharbor.example",
                industry="Cloud Services",
                size_band="51-200",
                region="North America",
                business_model="B2B",
                source="Referral",
                event_type="ReferralIntro",
                days_ago=6,
                summary="Referred by an existing customer after discussing operations automation.",
                raw_message="Customer intro mentioned interest in sales and support teammates.",
                buying_stage="Consideration",
                intent_score=81,
                fit_score=87,
                urgency="High",
                pain_points=["Manual operational handoffs", "Limited manager review time"],
                outcomes=["Delegate repeatable work", "Maintain oversight"],
                offer="Reference the intro and offer a workflow discovery call",
                tone="Executive",
                cta_type="BookMeeting",
                suggested_cta="Would a short workflow discovery call be useful this week?",
                owner_name="Mira Patel",
            ),
        },
        {
            "org": "acme",
            "status": WorkItemStatus.PENDING_REVIEW,
            "priority": WorkItemPriority.MEDIUM,
            "profile": _profile(
                first_name="Nina",
                last_name="Klein",
                email="nina.klein@example.com",
                title="Finance Operations Lead",
                seniority="MANAGER",
                department="Finance Operations",
                company_name="LedgerWorks",
                domain="ledgerworks.example",
                industry="Fintech",
                size_band="201-1000",
                region="EMEA",
                business_model="B2B",
                source="Website",
                event_type="HighIntentVisit",
                days_ago=7,
                summary="Repeated visits to security and audit pages from finance operations team.",
                raw_message="Viewed SOC2, audit log, and data handling pages.",
                buying_stage="Consideration",
                intent_score=73,
                fit_score=80,
                urgency="Medium",
                pain_points=["Audit requirements", "Approval-sensitive communication"],
                outcomes=["Clear compliance trail", "Controlled automation"],
                offer="Offer security-first overview",
                tone="Technical",
                cta_type="ViewResource",
                suggested_cta="Would a security-first overview be helpful?",
                owner_name="Mira Patel",
            ),
        },
        {
            "org": "acme",
            "status": WorkItemStatus.FAILED,
            "priority": WorkItemPriority.HIGH,
            "profile": _profile(
                first_name="Owen",
                last_name="Reed",
                email="owen.reed@example.com",
                title="Sales Director",
                seniority="DIRECTOR",
                department="Sales",
                company_name="FieldPilot",
                domain="fieldpilot.example",
                industry="Field Service",
                size_band="201-1000",
                region="North America",
                business_model="B2B",
                source="CRM Import",
                event_type="Reengagement",
                days_ago=8,
                summary="Reengaged after a quiet quarter and requested current workflow examples.",
                raw_message="Asked whether AI review can support distributed sales teams.",
                buying_stage="Evaluation",
                intent_score=78,
                fit_score=82,
                urgency="Medium",
                pain_points=["Distributed sales messaging", "Slow manager approvals"],
                outcomes=["Manager-approved AI drafts", "Faster follow-up"],
                offer="Retry processing after CRM sync issue",
                tone="Consultative",
                cta_type="BookMeeting",
                suggested_cta="Would you like to revisit the distributed team workflow?",
                owner_name="Mira Patel",
            ),
        },
        {
            "org": "globex",
            "status": WorkItemStatus.PENDING_REVIEW,
            "priority": WorkItemPriority.HIGH,
            "profile": _profile(
                first_name="Maya",
                last_name="Singh",
                email="maya.singh@example.com",
                title="Director of Revenue",
                seniority="DIRECTOR",
                department="Revenue",
                company_name="PipelineWorks",
                domain="pipelineworks.example",
                industry="Sales Technology",
                size_band="51-200",
                region="EMEA",
                business_model="B2B",
                source="Demo Request",
                event_type="DemoRequested",
                days_ago=2,
                summary="Requested a demo focused on reviewer-controlled AI sales outreach.",
                raw_message="We need a way to draft follow-ups without losing manager control.",
                buying_stage="ReadyToBuy",
                intent_score=89,
                fit_score=86,
                urgency="High",
                pain_points=["Manager review bottlenecks", "Slow inbound response"],
                outcomes=["Review AI drafts quickly", "Send consistent follow-ups"],
                offer="Book a reviewer workflow walkthrough",
                tone="Consultative",
                cta_type="BookMeeting",
                suggested_cta="Would Friday work for a reviewer workflow walkthrough?",
                owner_name="Jordan Lee",
            ),
        },
        {
            "org": "globex",
            "status": WorkItemStatus.PENDING_REVIEW,
            "priority": WorkItemPriority.MEDIUM,
            "assigned_to": "backup_reviewer",
            "profile": _profile(
                first_name="Caleb",
                last_name="Ross",
                email="caleb.ross@example.com",
                title="Sales Operations Manager",
                seniority="MANAGER",
                department="Sales Operations",
                company_name="QuotaPath Labs",
                domain="quotapath.example",
                industry="Sales Operations",
                size_band="201-1000",
                region="North America",
                business_model="B2B",
                source="Webinar",
                event_type="WebinarAttended",
                days_ago=3,
                summary="Asked how regenerated drafts preserve audit history.",
                raw_message="Can reviewers ask the AI to rewrite while keeping a trace?",
                buying_stage="Consideration",
                intent_score=72,
                fit_score=82,
                urgency="Medium",
                pain_points=["Draft revision tracking", "Reviewer feedback loops"],
                outcomes=["Trace regenerated drafts", "Reduce rewrite work"],
                offer="Share regeneration and audit trail example",
                tone="Technical",
                cta_type="ViewResource",
                suggested_cta="Can I send over a regeneration audit example?",
                owner_name="Jordan Lee",
            ),
        },
        {
            "org": "globex",
            "status": WorkItemStatus.SENT,
            "priority": WorkItemPriority.HIGH,
            "profile": _profile(
                first_name="Iris",
                last_name="Tan",
                email="iris.tan@example.com",
                title="VP Marketing",
                seniority="VP",
                department="Marketing",
                company_name="SignalForge",
                domain="signalforge.example",
                industry="Martech",
                size_band="51-200",
                region="APAC",
                business_model="B2B",
                source="Event",
                event_type="HighIntentVisit",
                days_ago=9,
                summary="Met at an event and later reviewed sales automation pages.",
                raw_message="Asked for a post-event summary and next steps.",
                buying_stage="Evaluation",
                intent_score=84,
                fit_score=78,
                urgency="High",
                pain_points=["Event lead follow-up", "Personalized recap at scale"],
                outcomes=["Faster post-event outreach", "Better personalization"],
                offer="Send event-specific follow-up",
                tone="Warm",
                cta_type="ConfirmInterest",
                suggested_cta="Should I send a short event follow-up workflow example?",
                owner_name="Jordan Lee",
            ),
        },
        {
            "org": "globex",
            "status": WorkItemStatus.REJECTED,
            "priority": WorkItemPriority.LOW,
            "reviewer_note": "Lead asked not to receive further sales outreach this quarter.",
            "profile": _profile(
                first_name="Theo",
                last_name="Park",
                email="theo.park@example.com",
                title="Operations Manager",
                seniority="MANAGER",
                department="Operations",
                company_name="Northline Labs",
                domain="northline.example",
                industry="Biotech",
                size_band="11-50",
                region="North America",
                business_model="B2B",
                source="Intent Data",
                event_type="Reengagement",
                days_ago=10,
                summary="Low-intent reengagement after old nurture campaign.",
                raw_message="Visited one article but previously asked to pause outreach.",
                buying_stage="Awareness",
                intent_score=31,
                fit_score=60,
                urgency="Low",
                pain_points=["Small operations team"],
                outcomes=["Understand future automation options"],
                offer="Hold outreach for now",
                tone="Concise",
                cta_type="ConfirmInterest",
                suggested_cta="Would you like us to check back next quarter?",
                owner_name="Jordan Lee",
            ),
        },
    ]


def _clear_existing_data(session) -> None:
    # Break the intentional latest-generation circular FK before deleting work items.
    session.execute(update(LeadWorkItem).values(latest_generation_run_id=None))
    for model in (
        IdempotencyKey,
        BackgroundJob,
        AuditLog,
        LLMGenerationRun,
        LeadWorkItem,
        User,
        Organization,
    ):
        session.execute(delete(model))
    session.commit()


def _make_user(
    org: Organization,
    email: str,
    name: str,
    role: UserRole,
    *,
    is_active: bool = True,
) -> User:
    return User(
        organization_id=org.id,
        email=email,
        name=name,
        role=role,
        password_hash=hash_password(SEED_PASSWORDS[email]),
        is_active=is_active,
    )


def _make_audit(
    org_id,
    action: str,
    *,
    work_item_id=None,
    actor_user_id=None,
    metadata: dict | None = None,
) -> AuditLog:
    return AuditLog(
        organization_id=org_id,
        work_item_id=work_item_id,
        actor_user_id=actor_user_id,
        action=action,
        metadata_json=metadata or {},
        ip_address="127.0.0.1",
        user_agent="seed-script",
    )


def seed_database() -> None:
    if get_settings().environment == "production":
        raise RuntimeError("Refusing to run destructive seed script in production.")

    with sync_session_factory() as session:
        _clear_existing_data(session)

        acme = Organization(name="Acme Growth", slug="acme")
        globex = Organization(name="Globex Revenue", slug="globex")
        session.add_all([acme, globex])
        session.flush()

        users = {
            "acme_admin": _make_user(acme, "admin@acme.example", "Acme Admin", UserRole.ADMIN),
            "acme_reviewer": _make_user(
                acme,
                "reviewer@acme.example",
                "Acme Reviewer",
                UserRole.REVIEWER,
            ),
            "acme_backup_reviewer": _make_user(
                acme,
                "backup.reviewer@acme.example",
                "Acme Backup Reviewer",
                UserRole.REVIEWER,
            ),
            "acme_inactive": _make_user(
                acme,
                "inactive@acme.example",
                "Inactive Acme User",
                UserRole.REVIEWER,
                is_active=False,
            ),
            "globex_admin": _make_user(
                globex,
                "admin@globex.example",
                "Globex Admin",
                UserRole.ADMIN,
            ),
            "globex_reviewer": _make_user(
                globex,
                "reviewer@globex.example",
                "Globex Reviewer",
                UserRole.REVIEWER,
            ),
            "globex_backup_reviewer": _make_user(
                globex,
                "backup.reviewer@globex.example",
                "Globex Backup Reviewer",
                UserRole.REVIEWER,
            ),
            "globex_inactive": _make_user(
                globex,
                "inactive@globex.example",
                "Inactive Globex User",
                UserRole.REVIEWER,
                is_active=False,
            ),
        }
        session.add_all(users.values())
        session.flush()

        orgs = {"acme": acme, "globex": globex}
        assignees = {
            "acme": {
                "reviewer": users["acme_reviewer"],
                "backup_reviewer": users["acme_backup_reviewer"],
                "admin": users["acme_admin"],
            },
            "globex": {
                "reviewer": users["globex_reviewer"],
                "backup_reviewer": users["globex_backup_reviewer"],
                "admin": users["globex_admin"],
            },
        }

        for scenario in _scenario_data():
            org_key = scenario["org"]
            org = orgs[org_key]
            assigned_user = assignees[org_key][scenario.get("assigned_to", "reviewer")]
            profile = scenario["profile"]
            result = _generation_result(profile)
            draft = f"Subject: {result['subject']}\n\n{result['email_body']}"
            status = scenario["status"]
            approved_at = (
                _dt(2, 14)
                if status in {WorkItemStatus.SENT, WorkItemStatus.FAILED}
                else None
            )

            item = LeadWorkItem(
                organization_id=org.id,
                assigned_reviewer_id=assigned_user.id,
                status=status,
                reviewer_note=scenario.get("reviewer_note"),
                ai_draft=draft,
                final_draft=draft,
                approved_draft_snapshot=draft
                if status in {WorkItemStatus.SENT, WorkItemStatus.FAILED}
                else None,
                approved_by_user_id=assigned_user.id
                if status in {WorkItemStatus.SENT, WorkItemStatus.FAILED}
                else None,
                approved_at=approved_at,
                sent_at=_dt(1, 15) if status == WorkItemStatus.SENT else None,
                lead_first_name=profile["contact"]["first_name"],
                lead_last_name=profile["contact"]["last_name"],
                lead_email=profile["contact"]["email"],
                lead_phone=profile["contact"]["phone"],
                lead_title=profile["contact"]["title"],
                lead_linkedin_url=profile["contact"]["linkedin_url"],
                company_name=profile["company"]["name"],
                company_domain=profile["company"]["domain"],
                company_industry=profile["company"]["industry"],
                company_size=profile["company"]["size_band"],
                company_region=profile["company"]["region"],
                lead_source=profile["source_signal"]["source"],
                source_event_type=profile["source_signal"]["event_type"],
                source_event_at=datetime.fromisoformat(profile["source_signal"]["event_at"]),
                source_event_summary=profile["source_signal"]["summary"],
                buying_stage=profile["qualification"]["buying_stage"],
                intent_score=profile["qualification"]["intent_score"],
                fit_score=profile["qualification"]["fit_score"],
                priority=scenario["priority"],
                lead_profile=profile,
            )
            session.add(item)
            session.flush()

            generation_run = LLMGenerationRun(
                organization_id=org.id,
                work_item_id=item.id,
                provider=LLMProvider.MOCK,
                provider_mode=LLMProviderMode.MOCK,
                model="mock-sales-followup-v1",
                prompt_version="seed-v1",
                schema_version="generation-result-v1",
                request_type=LLMRequestType.INITIAL_DRAFT,
                status=LLMRunStatus.COMPLETED,
                input_snapshot=profile,
                structured_output=result,
                decision_trace=result["decision_trace"],
                provider_raw_metadata={"seeded": True},
                token_usage={"input_tokens": 850, "output_tokens": 360},
                latency_ms=120,
                completed_at=_dt(0, 9),
            )
            session.add(generation_run)
            session.flush()
            item.latest_generation_run_id = generation_run.id

            for regeneration_number in range(1, scenario.get("regeneration_runs", 0) + 1):
                session.add(
                    _make_audit(
                        org.id,
                        actions.DRAFT_REGENERATION_STARTED,
                        work_item_id=item.id,
                        actor_user_id=assigned_user.id,
                        metadata={"feedback": "Make the CTA more specific."},
                    )
                )
                regenerated_result = deepcopy(result)
                regenerated_result["subject"] = (
                    f"{result['subject']} - revised {regeneration_number}"
                )
                regenerated_result["decision_trace"]["summary"] = (
                    "Regenerated using reviewer feedback to make the CTA more specific."
                )
                regenerated_draft = (
                    f"Subject: {regenerated_result['subject']}\n\n"
                    f"{regenerated_result['email_body']}"
                )
                regeneration_run = LLMGenerationRun(
                    organization_id=org.id,
                    work_item_id=item.id,
                    provider=LLMProvider.MOCK,
                    provider_mode=LLMProviderMode.MOCK,
                    model="mock-sales-followup-v1",
                    prompt_version="seed-v1",
                    schema_version="generation-result-v1",
                    request_type=LLMRequestType.REGENERATION,
                    status=LLMRunStatus.COMPLETED,
                    input_snapshot={
                        "lead_profile": profile,
                        "reviewer_feedback": "Make the CTA more specific.",
                    },
                    structured_output=regenerated_result,
                    decision_trace=regenerated_result["decision_trace"],
                    provider_raw_metadata={
                        "seeded": True,
                        "regeneration_number": regeneration_number,
                    },
                    token_usage={"input_tokens": 920, "output_tokens": 340},
                    latency_ms=135,
                    completed_at=_dt(0, 10 + regeneration_number),
                )
                session.add(regeneration_run)
                session.flush()
                item.ai_draft = regenerated_draft
                item.final_draft = regenerated_draft
                item.latest_generation_run_id = regeneration_run.id
                item.regeneration_count = regeneration_number
                session.add(
                    _make_audit(
                        org.id,
                        actions.DRAFT_REGENERATED,
                        work_item_id=item.id,
                        actor_user_id=assigned_user.id,
                        metadata={"generation_run_id": str(regeneration_run.id)},
                    )
                )

            session.add(
                _make_audit(
                    org.id,
                    actions.ITEM_CREATED,
                    work_item_id=item.id,
                    metadata={"source": "seed"},
                )
            )
            session.add(
                _make_audit(
                    org.id,
                    actions.AI_DRAFT_GENERATED,
                    work_item_id=item.id,
                    metadata={"generation_run_id": str(generation_run.id)},
                )
            )

            if status in {WorkItemStatus.SENT, WorkItemStatus.FAILED}:
                job_status = (
                    BackgroundJobStatus.COMPLETED
                    if status == WorkItemStatus.SENT
                    else BackgroundJobStatus.FAILED
                )
                session.add(
                    BackgroundJob(
                        organization_id=org.id,
                        work_item_id=item.id,
                        task_name="process_approval",
                        status=job_status,
                        attempt_count=1,
                        max_attempts=3,
                        error_message=(
                            "Simulated CRM sync failure"
                            if status == WorkItemStatus.FAILED
                            else None
                        ),
                        started_at=_dt(1, 14),
                        completed_at=_dt(1, 15),
                    )
                )
                session.add(
                    _make_audit(
                        org.id,
                        actions.ITEM_APPROVED,
                        work_item_id=item.id,
                        actor_user_id=assigned_user.id,
                        metadata={"approved_draft_snapshot": True},
                    )
                )
                session.add(
                    _make_audit(
                        org.id,
                        actions.JOB_STARTED,
                        work_item_id=item.id,
                        metadata={"task_name": "process_approval"},
                    )
                )
                session.add(
                    _make_audit(
                        org.id,
                        actions.JOB_COMPLETED
                        if status == WorkItemStatus.SENT
                        else actions.JOB_FAILED,
                        work_item_id=item.id,
                        metadata={"status": status.value},
                    )
                )

            if status == WorkItemStatus.REJECTED:
                session.add(
                    _make_audit(
                        org.id,
                        actions.ITEM_REJECTED,
                        work_item_id=item.id,
                        actor_user_id=assigned_user.id,
                        metadata={"reviewer_note": item.reviewer_note},
                    )
                )

        session.commit()


def main() -> None:
    seed_database()
    print("Seeded AI Sales Teammate database.")
    print("Test credentials:")
    for email in ACTIVE_DEMO_EMAILS:
        print(f"  {email} / {SEED_PASSWORDS[email]}")


if __name__ == "__main__":
    main()
