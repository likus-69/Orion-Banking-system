"""Fix all raw fetch() calls in templates to include auth headers."""
import re
from pathlib import Path

TEMPLATES_DIR = Path("/home/z/my-project/repo/backend/app/templates")

FILES_TO_FIX = [
    "beneficiaries/index.html",
    "webhooks/index.html",
    "webhooks/detail.html",
    "scheduled_transfers/index.html",
    "scheduled_transfers/detail.html",
    "dashboard/transfer.html",
    "dashboard/settings.html",
]

fixed = 0
for rel_path in FILES_TO_FIX:
    filepath = TEMPLATES_DIR / rel_path
    if not filepath.exists():
        print(f"  Not found: {rel_path}")
        continue

    content = filepath.read_text()
    original = content

    # 1. Remove local authHeaders() function definitions
    content = re.sub(
        r"\s+function authHeaders\(\)\s*\{[^}]+\}",
        "",
        content,
    )
    content = re.sub(
        r"\s+const authHeaders = \(\)\s*=>\s*\{[^}]+\}",
        "",
        content,
    )

    # 2. Replace any bare authHeaders() calls with OrionUI.authHeaders()
    content = re.sub(r"(?<!OrionUI\.)authHeaders\(\)", "OrionUI.authHeaders()", content)
    # Fix double-replacement
    content = content.replace("OrionUI.OrionUI.authHeaders()", "OrionUI.authHeaders()")

    # 3. For fetch calls with method: 'POST' and Content-Type headers → merge authHeaders
    content = re.sub(
        r"headers:\s*\{\s*'Content-Type':\s*'application/json'\s*\}",
        "headers: { 'Content-Type': 'application/json', ...OrionUI.authHeaders() }",
        content,
    )

    # 4. For fetch(url, { method: 'POST' }) without headers → add headers
    content = re.sub(
        r"fetch\(([^,)]+),\s*\{\s*method:\s*'POST'\s*\}\)",
        r"fetch(\1, { method: 'POST', headers: OrionUI.authHeaders() })",
        content,
    )

    # 5. For fetch(url, { method: 'DELETE' }) without headers → add headers
    content = re.sub(
        r"fetch\(([^,)]+),\s*\{\s*method:\s*'DELETE'\s*\}\)",
        r"fetch(\1, { method: 'DELETE', headers: OrionUI.authHeaders() })",
        content,
    )

    # 6. For fetch('/api/...') without options → add headers
    # Match: fetch('...' or fetch(`...` followed by ) and NOT .then
    for quote in ["'", "`"]:
        pattern = f"fetch\\(({quote}[^{quote}]*{quote})\\)(?!\\.then)"
        content = re.sub(
            pattern,
            lambda m, q=quote: f"fetch({m.group(1)}, {{ headers: OrionUI.authHeaders() }})",
            content,
        )

    # 7. For fetch('/api/...') .then → add headers
    for quote in ["'", "`"]:
        pattern = f"fetch\\(({quote}[^{quote}]*{quote})\\)\\.then"
        content = re.sub(
            pattern,
            lambda m, q=quote: f"fetch({m.group(1)}, {{ headers: OrionUI.authHeaders() }}).then",
            content,
        )

    # 8. For fetch(url, { method: 'POST', body: ... }) without headers → add
    content = re.sub(
        r"fetch\(([^,]+),\s*\{\s*method:\s*'POST',\s*body:",
        r"fetch(\1, { method: 'POST', headers: { 'Content-Type': 'application/json', ...OrionUI.authHeaders() }, body:",
        content,
    )

    # 9. For fetch(url, { method: 'PATCH', body: ... }) without headers → add
    content = re.sub(
        r"fetch\(([^,]+),\s*\{\s*method:\s*'PATCH',\s*body:",
        r"fetch(\1, { method: 'PATCH', headers: { 'Content-Type': 'application/json', ...OrionUI.authHeaders() }, body:",
        content,
    )

    if content != original:
        filepath.write_text(content)
        print(f"  Fixed: {rel_path}")
        fixed += 1
    else:
        print(f"  No changes needed: {rel_path}")

print(f"\nTotal files fixed: {fixed}")
