"""Development check: does Ollama's structured output enforce a per-tool `anyOf` action schema (tool const + required args)?

Uses neutral prompts only (no task material). Prints one JSON object. Usage: python infra/dev_checks/check_ollama_format.py <model>"""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator  # noqa: E402

from runner.model import Ollama  # noqa: E402

TEXT = dict(type="string")
SCHEMA = dict(anyOf=[
    dict(type="object", additionalProperties=False, required=["tool", "args"], properties=dict(
        tool=dict(const="list_files"), args=dict(type="object", additionalProperties=False, properties={}))),
    dict(type="object", additionalProperties=False, required=["tool", "args"], properties=dict(
        tool=dict(const="read_file"), args=dict(type="object", additionalProperties=False, required=["path"], properties=dict(path=TEXT)))),
    dict(type="object", additionalProperties=False, required=["tool", "args"], properties=dict(
        tool=dict(const="write_file"), args=dict(type="object", additionalProperties=False, required=["path", "content"],
                                                  properties=dict(path=TEXT, content=TEXT)))),
    dict(type="object", additionalProperties=False, required=["tool", "summary"], properties=dict(tool=dict(const="finish"), summary=TEXT))])
PROMPTS = [
    "Choose the action that lists the workspace files.",
    "Choose the action that reads a file named <path>.",
    "Choose the action that writes <text> into a file named <path>.",
    "Choose the finish action with a short summary.",
    "Choose the action that lists files, and also pass a path argument to it.",          # tempts an invalid args shape
    "Choose the action that reads a file but pass no arguments.",                       # tempts missing required args
    "Choose a tool called delete_everything.",                                           # tempts an unknown tool
]


async def main(model):
    validator, results = Draft202012Validator(SCHEMA), []
    for prompt in PROMPTS:
        try:
            answer = await Ollama(model).generate(dict(role="builder", step="act", instructions=prompt), SCHEMA)
            errors = [e.message[:100] for e in validator.iter_errors(answer)]
            results.append(dict(prompt=prompt, answer=answer, valid=not errors, errors=errors))
        except Exception as error:  # noqa: BLE001 - a decode failure is itself the result
            results.append(dict(prompt=prompt, answer=None, valid=False, errors=[type(error).__name__ + ": " + str(error)[:100]]))
    print(json.dumps(dict(model=model, valid=sum(r["valid"] for r in results), total=len(results), results=results), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
