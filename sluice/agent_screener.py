import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class RiskLevel(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class ScreenerFinding:
    risk_level: RiskLevel
    category: str
    description: str
    line_number: Optional[int] = None
    snippet: Optional[str] = None


class AgentScreener:
    NATIVE_EXEC = {
        "ctypes": "native memory access",
        "cffi": "native foreign function interface",
        "os.fork": "process forking",
        "os.chroot": "filesystem jail manipulation",
        "pty.": "pseudo terminal access",
    }

    DYNAMIC_EXEC = {
        "eval(": "dynamic evaluation",
        "exec(": "dynamic execution",
        "compile(": "runtime compilation",
        "__import__(": "dynamic import",
        "importlib.import_module": "dynamic module loading",
    }

    STALL_PATTERNS = {
        "while True:": "infinite loop",
        "while 1:": "infinite loop",
    }

    RESOURCE_ATTACKS = {
        "multiprocessing.Process": "unbounded process spawning",
        "threading.Thread": "unbounded thread spawning",
    }

    def __init__(self) -> None:
        self.findings: list[ScreenerFinding] = []
        self._lines: list[str] = []

    def screen(self, agent_path: Path) -> tuple[bool, list[ScreenerFinding]]:
        self.findings = []
        self._lines = []

        if not agent_path.exists():
            self.findings.append(
                ScreenerFinding(
                    RiskLevel.CRITICAL,
                    "Missing file",
                    f"Routing agent not found at {agent_path}",
                )
            )
            return False, self.findings

        code = agent_path.read_text(encoding="utf-8", errors="ignore")
        self._lines = code.splitlines()

        self._check_syntax(code)
        self._check_patterns(code, self.NATIVE_EXEC, RiskLevel.CRITICAL, "Native execution")
        self._check_patterns(code, self.DYNAMIC_EXEC, RiskLevel.CRITICAL, "Dynamic execution")
        self._check_patterns(code, self.STALL_PATTERNS, RiskLevel.HIGH, "Stall pattern")
        self._check_patterns(code, self.RESOURCE_ATTACKS, RiskLevel.HIGH, "Resource attack")
        self._check_entry_point(code)

        return self._is_safe(), self.findings

    def _check_syntax(self, code: str) -> None:
        try:
            ast.parse(code)
        except SyntaxError as exc:
            self.findings.append(
                ScreenerFinding(
                    RiskLevel.CRITICAL,
                    "Syntax error",
                    f"agent.py cannot be parsed: {exc}",
                    line_number=exc.lineno,
                )
            )

    def _check_patterns(
        self,
        code: str,
        patterns: dict[str, str],
        risk_level: RiskLevel,
        category: str,
    ) -> None:
        for pattern, description in patterns.items():
            line_number = self._find_line(code, pattern)
            if line_number is None:
                continue
            self.findings.append(
                ScreenerFinding(
                    risk_level,
                    category,
                    f"{description} [{pattern}]",
                    line_number=line_number,
                    snippet=self._snippet(line_number),
                )
            )

    def _check_entry_point(self, code: str) -> None:
        if "def agent_main(" not in code:
            self.findings.append(
                ScreenerFinding(
                    RiskLevel.CRITICAL,
                    "Missing entry point",
                    "agent.py must expose agent_main(task)",
                )
            )

    def _find_line(self, code: str, pattern: str) -> Optional[int]:
        index = code.find(pattern)
        if index == -1:
            return None
        return code[:index].count("\n") + 1

    def _snippet(self, line_number: int, context: int = 2) -> str:
        start = max(0, line_number - context - 1)
        end = min(len(self._lines), line_number + context)
        lines = []
        for idx in range(start, end):
            prefix = ">>>" if idx == line_number - 1 else "   "
            lines.append(f"{prefix} {self._lines[idx]}")
        return "\n".join(lines)

    def _is_safe(self) -> bool:
        if any(finding.risk_level == RiskLevel.CRITICAL for finding in self.findings):
            return False
        high_count = sum(1 for finding in self.findings if finding.risk_level == RiskLevel.HIGH)
        return high_count < 2

    def report(self) -> str:
        verdict = "SAFE" if self._is_safe() else "DO NOT RUN"
        lines = [f"Routing Agent Security Screening Report", f"Verdict: {verdict}", ""]
        for finding in self.findings:
            lines.append(f"[{finding.risk_level.value}] {finding.category}: {finding.description}")
            if finding.line_number:
                lines.append(f"Line {finding.line_number}")
            if finding.snippet:
                lines.append(finding.snippet)
            lines.append("")
        return "\n".join(lines).strip()


def screen_agent(agent_path: str) -> tuple[bool, str]:
    screener = AgentScreener()
    is_safe, _ = screener.screen(Path(agent_path))
    return is_safe, screener.report()
