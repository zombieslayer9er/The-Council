from pathlib import Path

from tools.generate_typescript import render


def test_generated_typescript_is_current() -> None:
    generated = Path("contracts/typescript/types.generated.ts")
    assert generated.read_text(encoding="utf-8") == render()
