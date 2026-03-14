"""
PromptManager - Prompt 节点树 + Patch 引擎

架构：
  Prompt Tree（有序节点列表）
    base → tools → strategy → knowledge_scope → answer_format

  Patch 机制（YAML 格式，存于 prompts_override/patches.yaml）：
    - op: before | after | replace | append_line
      target: <节点名>
      content: |
        插入的内容

  加载优先级：
    prompts_override/patches.yaml   （各环境定制，不进 git）
    prompts/<节点名>.txt             （通用模板，进 git）

典型用法（公司定制 prompts_override/patches.yaml）：
    - op: after
      target: strategy
      content: |
        企业环境附加规则：
        - 优先搜索本地知识库，不要使用 web_search

    - op: replace
      target: base
      content: |
        你是XX公司内部知识助手，只回答与公司业务相关的问题。
"""
import os
from typing import List, Dict, Any, TYPE_CHECKING
from loguru import logger

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

if TYPE_CHECKING:
    from app.agent.tools.base import BaseTool

# ── 路径常量 ──────────────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_PROMPTS_DIR = os.path.join(_PROJECT_ROOT, "prompts")
_OVERRIDE_DIR = os.path.join(_PROJECT_ROOT, "prompts_override")
_PATCHES_FILE = os.path.join(_OVERRIDE_DIR, "patches.yaml")

# MCP 工具前缀
_MCP_PREFIXES = (
    "filesystem_", "fetch_", "github_", "sqlite_",
    "git_", "brave_search_", "puppeteer_", "redis_",
)

# Prompt 节点的默认顺序（节点名 == prompts/<name>.txt）
_DEFAULT_NODE_ORDER = [
    "base",
    "tools",
    "strategy",
    "knowledge_scope",
    "answer_format",
]


# ── 节点加载 ──────────────────────────────────────────────────────────────────

def _load_node(name: str) -> str:
    """从 prompts/<name>.txt 读取节点内容"""
    path = os.path.join(_PROMPTS_DIR, f"{name}.txt")
    if not os.path.exists(path):
        logger.warning(f"⚠️ prompt 节点文件缺失：prompts/{name}.txt")
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _load_nodes() -> Dict[str, str]:
    """加载所有默认节点，返回 {节点名: 内容} 的有序字典"""
    return {name: _load_node(name) for name in _DEFAULT_NODE_ORDER}


# ── Patch 加载 ────────────────────────────────────────────────────────────────

def _load_patches() -> List[Dict[str, Any]]:
    """
    加载 prompts_override/patches.yaml。
    文件不存在时静默返回空列表（无定制 = 使用通用版）。
    """
    if not os.path.exists(_PATCHES_FILE):
        return []

    if not _YAML_AVAILABLE:
        logger.error(
            "❌ 发现 patches.yaml 但未安装 PyYAML，忽略 patch。"
            "请执行: pip install pyyaml"
        )
        return []

    with open(_PATCHES_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        return []
    if not isinstance(data, list):
        logger.error("❌ patches.yaml 格式错误：顶层应为列表，忽略所有 patch")
        return []

    logger.info(f"📋 加载 {len(data)} 条 prompt patch（来自 prompts_override/patches.yaml）")
    return data


# ── Patch 应用引擎 ────────────────────────────────────────────────────────────

def _apply_patches(
    nodes: Dict[str, str],
    patches: List[Dict[str, Any]],
) -> Dict[str, str]:
    """
    将 patches 应用到节点字典上，返回修改后的节点字典。

    支持的操作（op）：
      after        在目标节点内容末尾追加（最常用）
      before       在目标节点内容开头插入
      replace      完整替换目标节点内容
      append_line  在目标节点末尾追加一行（简写形式，content 为单行字符串）
    """
    # 转为列表以支持插入新节点（未来扩展），当前操作只改内容
    result = dict(nodes)

    for i, patch in enumerate(patches):
        op = patch.get("op", "").strip()
        target = patch.get("target", "").strip()
        content = patch.get("content", "")

        if not op or not target:
            logger.warning(f"⚠️ patch[{i}] 缺少 op 或 target，跳过")
            continue

        if target not in result:
            logger.warning(
                f"⚠️ patch[{i}] 目标节点 '{target}' 不存在，跳过"
                f"（可用节点：{list(result.keys())}）"
            )
            continue

        content = content.strip() if isinstance(content, str) else str(content).strip()

        if op == "after":
            result[target] = result[target] + "\n\n" + content
            logger.debug(f"✅ patch[{i}] after:{target} 已应用")

        elif op == "before":
            result[target] = content + "\n\n" + result[target]
            logger.debug(f"✅ patch[{i}] before:{target} 已应用")

        elif op == "replace":
            result[target] = content
            logger.debug(f"✅ patch[{i}] replace:{target} 已应用")

        elif op == "append_line":
            result[target] = result[target] + "\n" + content
            logger.debug(f"✅ patch[{i}] append_line:{target} 已应用")

        else:
            logger.warning(f"⚠️ patch[{i}] 未知操作 op='{op}'，跳过")

    return result


# ── 工具列表渲染 ──────────────────────────────────────────────────────────────

def _render_tools_placeholder(
    nodes: Dict[str, str],
    tools: List["BaseTool"],
) -> Dict[str, str]:
    """
    将 tools 节点中的 {{TOOLS_PLACEHOLDER}} 替换为实际工具描述。
    工具按标准工具 / MCP 工具分组渲染。
    """
    if "tools" not in nodes:
        return nodes

    standard, mcp = [], []
    for tool in tools:
        desc = f"- **{tool.name}**: {tool.description}"
        if tool.name.startswith(_MCP_PREFIXES):
            mcp.append(desc)
        else:
            standard.append(desc)

    parts = []
    if standard:
        parts.append("\n".join(standard))
    if mcp:
        parts.append(
            "\n**MCP 扩展工具**（通过 Model Context Protocol 接入）:\n"
            + "\n".join(mcp)
        )

    tools_text = "\n".join(parts) if parts else "（暂无可用工具）"
    result = dict(nodes)
    result["tools"] = result["tools"].replace("{{TOOLS_PLACEHOLDER}}", tools_text)
    return result


# ── 公开接口 ──────────────────────────────────────────────────────────────────

class PromptManager:
    """
    Prompt 节点树管理器，支持 Patch 差量定制。

    使用方式：
        manager = PromptManager()
        system_prompt = manager.build_system_prompt(tools=tools_list, knowledge_tree=tree)
    """

    def build_system_prompt(
        self,
        tools: List["BaseTool"] = None,
        knowledge_tree: str = "",
    ) -> str:
        """
        构建最终系统 Prompt。

        流程：
          1. 加载通用节点（prompts/*.txt）
          2. 应用 patch（prompts_override/patches.yaml，若存在）
          3. 渲染工具占位符
          4. 注入知识库目录树
          5. 按节点顺序拼接
        """
        # 1. 加载通用节点
        nodes = _load_nodes()

        # 2. 应用 patch
        patches = _load_patches()
        if patches:
            nodes = _apply_patches(nodes, patches)

        # 3. 渲染工具占位符
        if tools:
            nodes = _render_tools_placeholder(nodes, tools)
        else:
            # 向后兼容：无工具对象时填入默认描述
            fallback = "\n".join([
                "- **search_knowledge**: 在知识库中进行语义搜索（RAG检索）",
                "- **run_bash**: 执行 bash 命令来探索文件（如 ls, cat, head, tail, grep, rg, find 等）",
                "- **run_python**: 执行 Python 代码进行数据分析或复杂处理",
                "- **calculator**: 执行数学计算",
                "- **web_search**: 搜索互联网获取最新信息",
            ])
            nodes["tools"] = nodes["tools"].replace("{{TOOLS_PLACEHOLDER}}", fallback)

        # 4. 注入知识库目录树（插入 base 节点之后）
        if knowledge_tree:
            nodes["base"] = nodes["base"] + f"\n\n知识库结构：\n{knowledge_tree}"

        # 5. 按顺序拼接非空节点
        sections = [
            nodes[name]
            for name in _DEFAULT_NODE_ORDER
            if nodes.get(name, "").strip()
        ]
        return "\n\n".join(sections)
