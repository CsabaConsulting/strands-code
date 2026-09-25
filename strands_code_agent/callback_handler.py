from typing import Any
import ast

from rich.syntax import Syntax
from rich.json import JSON
from rich.markdown import Markdown
from rich.pretty import Pretty
from rich.console import Console

DIFF_TOOLS = ("write", "edit")
SEARCH_TOOLS = ("search",)


def format_message(text):
    # Python data-structure
    try:
        return Pretty(ast.literal_eval(text))
    except (ValueError, SyntaxError):
        pass

    # JSON?
    try:
        return JSON(text, indent=4)
    except ValueError:
        pass

    # Markdown? (rough heuristic)
    import re
    if re.search(r"(^#{1,6} |\*\*|__|\[.+\]\(.+\)|```)", text, re.MULTILINE):
        return Markdown(text)

    return text


def format_diff_use(name, tool_input):
    """Render a write/edit tool call as a unified diff via Syntax("diff").

    ``edit`` inputs carry old/new snippets so the preview is exact; ``write``
    carries only new content, rendered as an all-addition diff. The body
    always carries ``---`` / ``+++`` markers. Printed inside the existing
    output_context wrap by the caller (loop.py), so raw stdout holds.
    """
    import difflib

    path = tool_input.get('path', '<unknown>')
    if name == "edit":
        old = tool_input.get('old_str', '')
        new = tool_input.get('new_str', '')
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
    else:
        old_lines = []
        content = tool_input.get('content', '')
        new_lines = content.splitlines(keepends=True)
    body = "".join(
        difflib.unified_diff(
            old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}"
        )
    )
    if not body:
        body = f"--- a/{path}\n+++ b/{path}\n(no content change)\n"
    return Syntax(body, "diff")


def format_search_use(tool_input):
    """Render a search tool call as plain path:line-oriented text."""
    pattern = tool_input.get('pattern', '')
    path = tool_input.get('path', '.')
    glob = tool_input.get('file_glob')
    suffix = f" --glob {glob}" if glob else ""
    return f"search {pattern!r} under {path}{suffix}"


class CodeAgentCallbackHandler:
    def __init__(self, code_tools=None, output_prefix="STDOUT:", format_text=True, **kwargs) -> None:
        self.console = Console()
        if code_tools is None:
            code_tools = {
                'python_repl': 'python'
            }
        self.code_tools = code_tools
        self.output_prefix = output_prefix
        if format_text:
            self.format_text = format_message
        else:
            self.format_text = lambda x: x

    def __call__(self, **kwargs: Any) -> None:
        if 'message' not in kwargs:
            return
        
        message = kwargs['message']
        role = message['role']
        for content_item in  message['content']:
            if 'text' in content_item:
                self.console.print(f"\n[{role.title()}]", end=" ")
                self.console.print(self.format_text(content_item['text'].strip()), end="\n\n")

            if 'toolUse' in content_item:
                tool_use = content_item['toolUse']
                name = tool_use['name']
                self.console.print(f"\n[Tool] {name}")
                if name in self.code_tools:
                    language = self.code_tools[name]
                    syntax = Syntax(tool_use['input']['code'], language)
                    self.console.print(syntax)
                elif name in DIFF_TOOLS:
                    self.console.print(format_diff_use(name, tool_use['input']))
                elif name in SEARCH_TOOLS:
                    self.console.print(format_search_use(tool_use['input']))
                else:
                    for var, value in tool_use['input'].items():
                        self.console.print(f"\t- {var}: {value}")
            
            if 'toolResult' in content_item:
                tool_result = content_item['toolResult']
                self.console.print(f"\n[Tool Result] Status: {tool_result['status']}")
                for tool_item in tool_result['content']:
                    if 'text' in tool_item:
                        text = tool_item['text'].strip()
                        if text.startswith(self.output_prefix):
                            body = text.removeprefix(self.output_prefix).strip()
                            self.console.print(self.output_prefix)
                            self.console.print(self.format_text(body))
                        else:
                            self.console.print(text)
