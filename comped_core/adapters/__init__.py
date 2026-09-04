from . import claude_code, codex, pi, opencode

ADAPTERS = {
    "claude-code": (claude_code, "claude_dir"),
    "codex": (codex, "codex_dir"),
    "pi": (pi, "pi_dir"),
    "opencode": (opencode, "opencode_dir"),
}
