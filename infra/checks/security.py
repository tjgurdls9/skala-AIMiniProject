"""Conservative local static checks; dependency/image scanning is separate."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sys

root = Path(os.environ.get("CANDIDATE_ROOT", "/candidate"))
findings = []
secret = re.compile(r"sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]{20,}|BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY")
allowed_imports = {"pathlib", "sqlite3", "fastapi", "pydantic", "typing"}
argv = sys.argv[1:]
model_authored = "--model-authored" in argv
unknown_import_rule = "unsupported_import"
if model_authored:
    # Model-authored apps: standard library, the approved dependencies' import names (resolved by the host from the installed
    # distributions) and the candidate's own modules. If a dependency's import names could not be resolved, an unknown import is
    # reported as unverified_import instead of being waved through.
    approved = argv[argv.index("--model-authored") + 1]
    local = {p.stem for p in root.rglob("*.py")} | {p.parent.name for p in root.rglob("*.py")}
    allowed_imports = set(sys.stdlib_module_names) | {m for m in approved.split(",") if m} | local
    if "--unverified" in argv and argv[argv.index("--unverified") + 1]:
        unknown_import_rule = "unverified_import"
for path in root.rglob("*"):
    if not path.is_file() or ".git" in path.parts:
        continue
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        findings.append({"path": str(path.relative_to(root)), "rule": "unsafe_file"})
        continue
    if "vendor" in path.parts:
        continue
    text = path.read_text()
    if secret.search(text):
        findings.append({"path": str(path.relative_to(root)), "rule": "secret_format"})
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)) and not (model_authored and getattr(node, "level", 0)):
                    names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                    if any(n.split(".")[0] not in allowed_imports for n in names):
                        findings.append({"path": str(path.relative_to(root)), "rule": unknown_import_rule})
                if isinstance(node, ast.Call):
                    name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                    if name in ("eval", "exec", "compile", "__import__", "system", "popen", "getattr", "setattr", "globals", "locals", "vars", "executescript"):
                        findings.append({"path": str(path.relative_to(root)), "rule": "dynamic_execution"})
                    if name == "execute" and node.args and not isinstance(node.args[0], ast.Constant):
                        findings.append({"path": str(path.relative_to(root)), "rule": "dynamic_sql"})
                    if name == "execute" and node.args and isinstance(node.args[0], ast.Constant) and re.search(r"\b(?:DROP|TRUNCATE|DELETE|ATTACH)\b", str(node.args[0].value), re.I):
                        findings.append({"path": str(path.relative_to(root)), "rule": "destructive_sql"})
                if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                    findings.append({"path": str(path.relative_to(root)), "rule": "runtime_introspection"})
        except SyntaxError:
            findings.append({"path": str(path.relative_to(root)), "rule": "syntax_error"})
    if path.suffix in (".js", ".html") and re.search(r"innerHTML|v-html|\beval\s*\(|new\s+Function|https?://", text):
        findings.append({"path": str(path.relative_to(root)), "rule": "unsafe_browser_code"})
print(json.dumps({"checks": {"static": not findings, "secrets": not any(f["rule"] == "secret_format" for f in findings)}, "findings": findings}))
