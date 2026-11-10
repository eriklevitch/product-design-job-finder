"""Optional: writes three tailored resume bullets and a cover letter
opening for each job, using ONLY what's in your portfolio_notes.md, so it
never invents experience. Needs an Anthropic API key; without one, jobs
are still added to your tracker, just without a draft."""
from anthropic import Anthropic

from settings import env, resolve_path

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_WRITING_STYLE = [
    "Plain, first-person voice.",
    "Active voice.",
    "Direct and brief. Cut any sentence that doesn't carry information.",
    'No stock phrases like "I\'m excited to", "passionate about" or '
    '"I believe I would be a great fit".',
]
EMPTY_NOTES_HINT = "(No portfolio notes yet. Add your experience to portfolio_notes.md.)"


def drafting_key(config: dict) -> str | None:
    """The Anthropic key, or None if drafting isn't set up."""
    cfg = config.get("anthropic") or {}
    return env(cfg.get("api_key_env", "ANTHROPIC_API_KEY"))


def load_portfolio_notes(config: dict) -> str:
    path = resolve_path(config.get("portfolio_notes_path", "portfolio_notes.md"))
    if not path.exists():
        return EMPTY_NOTES_HINT
    return path.read_text()


def generate_draft(job: dict, portfolio_notes: str, config: dict) -> str:
    cfg = config.get("anthropic") or {}
    client = Anthropic(api_key=drafting_key(config))

    # Some personal API keys that span several workspaces need this
    # header. Most people can ignore it.
    extra_headers = {}
    workspace_id = env("ANTHROPIC_WORKSPACE_ID")
    if workspace_id:
        extra_headers["anthropic-workspace-id"] = workspace_id

    role = config.get("your_role") or "product designer"
    style = config.get("writing_style") or DEFAULT_WRITING_STYLE
    style_lines = "\n".join(f"- {line}" for line in style)

    description = job.get("description", "").strip()
    description_block = (
        description if description
        else "(No description text available for this posting. Reference it generically.)"
    )

    prompt = f"""You're helping a {role} tailor application materials.
Use ONLY the experience below. Never invent projects, metrics, or claims
that aren't in the source material.

SOURCE MATERIAL (the person's real experience):
{portfolio_notes}

JOB POSTING:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}

JOB DESCRIPTION (use it to ground the cover letter in specifics, such as a
responsibility, a product area or a problem they mention, rather than
writing something that could apply to any job):
{description_block}

If the source material contains more than one summary (for example one for
leadership roles and one for individual-contributor roles), use only the
one that best fits this posting, and don't mention this instruction.

WRITING STYLE (follow exactly):
{style_lines}

Produce:
1. Three resume bullets (from the source material) most relevant to this
   posting, rewritten to mirror the posting's language where honest.
2. A cover letter opening (3-4 sentences) that names something specific
   from the job description and connects it to a specific piece of the
   source material.

Keep total output under 200 words. Plain text, no markdown headers."""

    resp = client.messages.create(
        model=cfg.get("model") or DEFAULT_MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
        extra_headers=extra_headers or None,
    )
    return "".join(block.text for block in resp.content if block.type == "text")
