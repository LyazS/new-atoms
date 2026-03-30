from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from enum import StrEnum
from typing import Any

from loguru import logger
from pydantic import BaseModel, ValidationError

from app.schemas.session import (
    FrontendToolName,
    PendingFrontendTool,
    Session,
    WorkspacePatch,
    WorkspacePatchOp,
    WorkspacePatchOpName,
)
from app.services.session_store import SessionStore, session_store


class ListFilesArgs(BaseModel):
    path: str
    recursive: bool


class ReadFileItemArgs(BaseModel):
    path: str


class ReadFileArgs(BaseModel):
    files: list[ReadFileItemArgs]


class ApplyDiffArgs(BaseModel):
    path: str
    diff: str


class WriteToFileArgs(BaseModel):
    path: str
    content: str


class DeleteFilesArgs(BaseModel):
    paths: list[str]


class CompleteTaskArgs(BaseModel):
    message: str


DIFF_BLOCK_RE = re.compile(
    r"<<<<<<< SEARCH\n:start_line:(?P<start_line>\d+)\n-------\n(?P<search>.*?)\n=======\n(?P<replace>.*?)\n>>>>>>> REPLACE",
    re.DOTALL,
)


class ToolExecutionKind(StrEnum):
    BACKEND = "backend"
    FRONTEND = "frontend"
    COMPLETE = "complete"


@dataclass
class ToolExecutionResult:
    kind: ToolExecutionKind
    tool_message: str | None = None
    workspace_patch: WorkspacePatch | None = None
    pending_frontend_tool: PendingFrontendTool | None = None
    completion_message: str | None = None


@dataclass
class DiffBlock:
    start_line: int
    search: str
    replace: str


def get_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": (
                    "请求列出指定目录下的文件和子目录。"
                    "如果 recursive 为 true，则递归列出该目录下所有文件和目录；"
                    "如果 recursive 为 false，则只列出顶层内容。"
                    "不要用这个工具确认你刚创建的文件是否成功生成，若创建失败，用户或后续流程会反馈。\n\n"
                    "参数：\n"
                    "- path: 必填，要查看内容的目录路径，相对于当前工作区\n"
                    "- recursive: 必填，是否递归列出目录内容。true 为递归，false 为仅顶层。\n\n"
                    "示例：列出当前目录顶层内容\n"
                    '{ "path": ".", "recursive": false }\n\n'
                    "示例：递归列出 src 目录下所有内容\n"
                    '{ "path": "src", "recursive": true }'
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "要查看的目录路径，相对于工作区",
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "true 表示递归列出，false 表示仅列出顶层",
                        },
                    },
                    "required": ["path", "recursive"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": (
                    "Read one or more files and return their contents with line numbers for diffing or discussion. "
                    "IMPORTANT: You can read a maximum of 5 files in a single request. If you need to read more files, "
                    "use multiple sequential read_file requests. Structure: { files: [{ path: 'relative/path.ts' }] }. "
                    "The 'path' is required and relative to workspace. Supports text extraction from PDF and DOCX files, "
                    "but may not handle other binary files properly. Example single file: "
                    "{ files: [{ path: 'src/app.ts' }] }. Example multiple files (within 5-file limit): "
                    "{ files: [{ path: 'file1.ts' }, { path: 'file2.ts' }] }. "
                    "Return format: <file><path>...</path><content>...</content></file>. "
                    "Inside <content>, each line must start with 'N|' where N is the source line number, "
                    "for example: 1|const a = 1"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "files": {
                            "type": "array",
                            "description": "List of files to read; request related files together when allowed",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {
                                        "type": "string",
                                        "description": "Path to the file to read, relative to the workspace",
                                    }
                                },
                                "required": ["path"],
                                "additionalProperties": False,
                            },
                            "minItems": 1,
                        }
                    },
                    "required": ["files"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "apply_diff",
                "description": (
                    "Apply precise, targeted modifications to an existing file using one or more "
                    "search/replace blocks. This tool is for surgical edits only; the 'SEARCH' block "
                    "must exactly match the existing content, including whitespace and indentation. "
                    "To make multiple targeted changes, provide multiple SEARCH/REPLACE blocks in the "
                    "'diff' parameter. Use the 'read_file' tool first if you are not confident in the "
                    "exact content to search for."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "The path of the file to modify, relative to the current workspace directory."
                            ),
                        },
                        "diff": {
                            "type": "string",
                            "description": (
                                "A string containing one or more search/replace blocks defining the changes. "
                                "The ':start_line:' is required and indicates the starting line number of the "
                                "original content. You must not add a start line for the replacement content. "
                                "Each block must follow this format:\n"
                                "<<<<<<< SEARCH\n"
                                ":start_line:[line_number]\n"
                                "-------\n"
                                "[exact content to find]\n"
                                "=======\n"
                                "[new content to replace with]\n"
                                ">>>>>>> REPLACE"
                            ),
                        },
                    },
                    "required": ["path", "diff"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_to_file",
                "description": (
                    "Request to write content to a file. This tool is primarily used for creating new files "
                    "or for scenarios where a complete rewrite of an existing file is intentionally required. "
                    "If the file exists, it will be overwritten. If it doesn't exist, it will be created. "
                    "This tool will automatically create any directories needed to write the file.\n\n"
                    "**Important:** You should prefer using other editing tools over write_to_file when making "
                    "changes to existing files, since write_to_file is slower and cannot handle large files. "
                    "Use write_to_file primarily for new file creation.\n\n"
                    "When using this tool, use it directly with the desired content. You do not need to display "
                    "the content before using the tool. ALWAYS provide the COMPLETE file content in your response. "
                    "This is NON-NEGOTIABLE. Partial updates or placeholders like '// rest of code unchanged' are "
                    "STRICTLY FORBIDDEN. Failure to do so will result in incomplete or broken code.\n\n"
                    "When creating a new project, organize all new files within a dedicated project directory unless "
                    "the user specifies otherwise. Structure the project logically, adhering to best practices for "
                    "the specific type of project being created.\n\n"
                    "Example: Writing a configuration file\n"
                    '{ "path": "frontend-config.json", "content": "{\\n  \\"apiEndpoint\\": \\"https://api.example.com\\",\\n'
                    '  \\"theme\\": {\\n    \\"primaryColor\\": \\"#007bff\\"\\n  }\\n}" }'
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "The path of the file to write to (relative to the current workspace directory)",
                        },
                        "content": {
                            "type": "string",
                            "description": (
                                "The content to write to the file. ALWAYS provide the COMPLETE intended content of "
                                "the file, without any truncation or omissions. You MUST include ALL parts of the "
                                "file, even if they haven't been modified. Do NOT include line numbers in the content."
                            ),
                        },
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_files",
                "description": "删除当前虚拟工作区中已经存在的文件。",
                "parameters": {
                    "type": "object",
                    "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
                    "required": ["paths"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_diagnostics",
                "description": "请求前端同步当前工作区，运行一次诊断，并返回编译或运行反馈。",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "complete_task",
                "description": "以面向用户的消息标记任务完成。若任务涉及页面、界面或可视化效果，应明确提示用户在右侧预览区域查看最终效果，不要提及 localhost、本地端口、URL 或类似访问地址。",
                "parameters": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
    ]


class ToolExecutor:
    def __init__(self, session_store: SessionStore) -> None:
        self.session_store = session_store

    def execute(
        self,
        *,
        session: Session,
        turn_id: str,
        tool_name: str,
        tool_call_id: str,
        raw_arguments: str,
    ) -> ToolExecutionResult:
        started_at = time.perf_counter()
        try:
            parsed_arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError as exc:
            logger.warning("tool args json decode failed session_id={} turn_id={} tool={}", session.session_id, turn_id, tool_name)
            return ToolExecutionResult(kind=ToolExecutionKind.BACKEND, tool_message=f"工具参数不是合法的 JSON：{exc}")

        logger.debug(
            "tool call tool={} arguments={}",
            tool_name,
            parsed_arguments,
        )

        try:
            if tool_name == "list_files":
                args = ListFilesArgs.model_validate(parsed_arguments)
                result = ToolExecutionResult(
                    kind=ToolExecutionKind.BACKEND,
                    tool_message=self._list_files(session=session, path=args.path, recursive=args.recursive),
                )
            elif tool_name == "read_file":
                args = ReadFileArgs.model_validate(parsed_arguments)
                if len(args.files) > 5:
                    raise ValueError("read_file 一次最多只能读取 5 个文件。")
                rendered_files: list[str] = []
                for item in args.files:
                    normalized_path = self._normalize_file_path(item.path)
                    content = session.workspace_files.get(normalized_path)
                    rendered_files.append(
                        self._render_file_block(
                            path=item.path,
                            content=self._format_file_with_line_numbers(content) if content is not None else "1|[file not found]",
                        )
                    )
                result = ToolExecutionResult(
                    kind=ToolExecutionKind.BACKEND,
                    tool_message="\n".join(rendered_files),
                )
            elif tool_name == "apply_diff":
                args = ApplyDiffArgs.model_validate(parsed_arguments)
                result = self._apply_diff(session=session, path=args.path, diff=args.diff)
            elif tool_name == "write_to_file":
                args = WriteToFileArgs.model_validate(parsed_arguments)
                result = self._write_to_file(session=session, path=args.path, content=args.content)
            elif tool_name == "delete_files":
                args = DeleteFilesArgs.model_validate(parsed_arguments)
                result = self._delete_files(session=session, paths=args.paths)
            elif tool_name == "run_diagnostics":
                pending = PendingFrontendTool(
                    tool_name=FrontendToolName.RUN_DIAGNOSTICS,
                    tool_call_id=tool_call_id,
                    arguments={},
                )
                result = ToolExecutionResult(kind=ToolExecutionKind.FRONTEND, pending_frontend_tool=pending)
            elif tool_name == "complete_task":
                args = CompleteTaskArgs.model_validate(parsed_arguments)
                result = ToolExecutionResult(kind=ToolExecutionKind.COMPLETE, completion_message=args.message)
            else:
                result = ToolExecutionResult(kind=ToolExecutionKind.BACKEND, tool_message=f"未知工具：{tool_name}")
        except ValidationError as exc:
            result = ToolExecutionResult(kind=ToolExecutionKind.BACKEND, tool_message=f"工具参数校验失败：{exc}")
        except ValueError as exc:
            result = ToolExecutionResult(kind=ToolExecutionKind.BACKEND, tool_message=str(exc))

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info("tool={} tool_message={}", tool_name, result.tool_message)
        return result

    def _list_files(self, *, session: Session, path: str, recursive: bool) -> str:
        normalized = self._normalize_directory_path(path)
        entries: set[str] = set()

        for workspace_path in session.workspace_files:
            relative = self._relative_to_directory(workspace_path, normalized)
            if relative is None or relative == "":
                continue

            relative_path = PurePosixPath(relative)
            if recursive:
                parts = relative_path.parts
                current_parts: list[str] = []
                for index, part in enumerate(parts):
                    current_parts.append(part)
                    candidate = "/".join(current_parts)
                    if index < len(parts) - 1:
                        entries.add(f"{candidate}/")
                    else:
                        entries.add(candidate)
            else:
                first = relative_path.parts[0]
                if len(relative_path.parts) == 1:
                    entries.add(first)
                else:
                    entries.add(f"{first}/")

        display_path = normalized or "."
        lines = [
            f"<path>{display_path}</path>",
            "<entries>",
        ]

        lines.extend(sorted(entries))
        lines.append("</entries>")

        if normalized not in ("", ".") and not entries:
            lines.append("目录不存在，或目录下没有可见内容。")

        return "\n".join(lines)

    def _normalize_directory_path(self, path: str) -> str:
        raw = (path or ".").strip()
        candidate = raw.replace("\\", "/").lstrip("/")
        normalized = PurePosixPath(candidate)
        parts = [part for part in normalized.parts if part not in ("", ".")]
        if any(part == ".." for part in parts):
            raise ValueError("目录路径不允许包含 ..")
        return "/".join(parts)

    def _normalize_file_path(self, path: str) -> str:
        raw = (path or "").strip()
        candidate = raw.replace("\\", "/").lstrip("/")
        normalized = PurePosixPath(candidate)
        parts = [part for part in normalized.parts if part not in ("", ".")]
        if not parts:
            raise ValueError("文件路径不能为空")
        if any(part == ".." for part in parts):
            raise ValueError("文件路径不允许包含 ..")
        return f"/{'/'.join(parts)}"

    def _relative_to_directory(self, workspace_path: str, directory: str) -> str | None:
        normalized_file = workspace_path.replace("\\", "/").lstrip("/")
        if directory in ("", "."):
            return normalized_file
        prefix = f"{directory}/"
        if normalized_file == directory:
            return ""
        if not normalized_file.startswith(prefix):
            return None
        return normalized_file[len(prefix):]

    def _delete_files(self, *, session: Session, paths: list[str]) -> ToolExecutionResult:
        normalized_pairs = [(path, self._normalize_file_path(path)) for path in paths]
        missing = [original for original, normalized in normalized_pairs if normalized not in session.workspace_files]
        if missing:
            return ToolExecutionResult(
                kind=ToolExecutionKind.BACKEND,
                tool_message=f"无法删除不存在的文件：{', '.join(missing)}",
            )

        patch = WorkspacePatch(
            ops=[WorkspacePatchOp(op=WorkspacePatchOpName.DELETE, path=normalized) for _, normalized in normalized_pairs]
        )
        self.session_store.apply_workspace_patch(session, patch)
        return ToolExecutionResult(
            kind=ToolExecutionKind.BACKEND,
            tool_message=json.dumps({"deleted": paths}, ensure_ascii=False),
            workspace_patch=patch,
        )

    def _write_to_file(self, *, session: Session, path: str, content: str) -> ToolExecutionResult:
        normalized_path = self._normalize_file_path(path)
        patch = WorkspacePatch(ops=[WorkspacePatchOp(op=WorkspacePatchOpName.UPSERT, path=normalized_path, code=content)])
        self.session_store.apply_workspace_patch(session, patch)
        return ToolExecutionResult(
            kind=ToolExecutionKind.BACKEND,
            tool_message=json.dumps({"written": path}, ensure_ascii=False),
            workspace_patch=patch,
        )

    def _apply_diff(self, *, session: Session, path: str, diff: str) -> ToolExecutionResult:
        normalized_path = self._normalize_file_path(path)
        original = session.workspace_files.get(normalized_path)
        if original is None:
            return ToolExecutionResult(kind=ToolExecutionKind.BACKEND, tool_message=f"文件不存在：{path}")

        try:
            blocks = self._parse_diff_blocks(diff)
        except ValueError as exc:
            return ToolExecutionResult(kind=ToolExecutionKind.BACKEND, tool_message=str(exc))

        updated_lines = original.splitlines(keepends=True)
        line_offset = 0

        for block in blocks:
            if block.start_line < 1:
                return ToolExecutionResult(
                    kind=ToolExecutionKind.BACKEND,
                    tool_message=f"diff 格式无效：start_line 必须从 1 开始，收到 {block.start_line}",
                )

            search_lines = block.search.splitlines(keepends=True)
            current_start = block.start_line - 1 + line_offset

            if current_start < 0 or current_start > len(updated_lines):
                return ToolExecutionResult(
                    kind=ToolExecutionKind.BACKEND,
                    tool_message=(
                        f"SEARCH 片段定位失败：{path} 的第 {block.start_line} 行超出当前文件范围。"
                    ),
                )

            current_slice = updated_lines[current_start : current_start + len(search_lines)]
            current_segment = "".join(current_slice)
            search_text = block.search

            # The diff format places the delimiter on the next line, so the parsed SEARCH/REPLACE
            # body usually omits the trailing newline from the last matched line.
            if current_segment != search_text and current_segment.endswith("\n"):
                if current_segment[:-1] == search_text:
                    search_text = current_segment

            if current_segment != search_text:
                return ToolExecutionResult(
                    kind=ToolExecutionKind.BACKEND,
                    tool_message=(
                        f"SEARCH 片段未能在 {path} 的第 {block.start_line} 行精确匹配当前内容。"
                        "请先调用 read_file，并在保留精确空白字符和缩进的前提下重试。"
                    ),
                )

            replace_text = block.replace
            if current_slice and current_slice[-1].endswith("\n") and replace_text and not replace_text.endswith("\n"):
                replace_text = f"{replace_text}\n"

            replace_lines = replace_text.splitlines(keepends=True)
            updated_lines[current_start : current_start + len(search_lines)] = replace_lines
            line_offset += len(replace_lines) - len(search_lines)

        updated = "".join(updated_lines)

        patch = WorkspacePatch(ops=[WorkspacePatchOp(op=WorkspacePatchOpName.UPSERT, path=normalized_path, code=updated)])
        self.session_store.apply_workspace_patch(session, patch)
        return ToolExecutionResult(
            kind=ToolExecutionKind.BACKEND,
            tool_message=json.dumps({"updated": path}, ensure_ascii=False),
            workspace_patch=patch,
        )

    def _parse_diff_blocks(self, diff: str) -> list[DiffBlock]:
        blocks: list[DiffBlock] = []
        cursor = 0

        for match in DIFF_BLOCK_RE.finditer(diff):
            gap = diff[cursor : match.start()]
            if gap.strip():
                raise ValueError("diff 格式无效：SEARCH/REPLACE 代码块之间不能包含额外内容。")

            search = match.group("search")
            if search == "":
                raise ValueError("diff 格式无效：SEARCH 片段不能为空。")

            blocks.append(
                DiffBlock(
                    start_line=int(match.group("start_line")),
                    search=search,
                    replace=match.group("replace"),
                )
            )
            cursor = match.end()

        if not blocks:
            raise ValueError("diff 格式无效，未找到 SEARCH/REPLACE 代码块。")

        if diff[cursor:].strip():
            raise ValueError("diff 格式无效：SEARCH/REPLACE 代码块之后不能包含额外内容。")

        return blocks

    def _format_file_with_line_numbers(self, content: str) -> str:
        lines = content.splitlines()
        if not lines:
            return "1|"
        return "\n".join(f"{index}|{line}" for index, line in enumerate(lines, start=1))

    def _render_file_block(self, *, path: str, content: str) -> str:
        return "\n".join(
            [
                "<file>",
                "<path>",
                path,
                "</path>",
                "<content>",
                content,
                "</content>",
                "</file>",
            ]
        )


tool_executor = ToolExecutor(session_store=session_store)
