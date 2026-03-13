# askinfo

`askinfo` 是一个终端优先的资产收集 Agent。当前开源版本只保留一个主入口，用自然语言驱动资产收集、验证和 `xlsx` 报告导出。

## Quick Start

仓库内直接运行：

```bash
python agent.py "帮我梳理示例科技有限公司的互联网资产，重点关注登录页和后台"
```

安装为命令后直接运行：

```bash
askinfo "帮我梳理示例科技有限公司的互联网资产，重点关注登录页和后台"
```

## Requirements

- Python `3.10+`
- 可用的 OpenAI-compatible 接口
- 至少一个可用的资产平台 API 凭据

## Installation

推荐使用虚拟环境：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

安装完成后，当前虚拟环境里就可以直接使用：

```bash
askinfo --doctor
askinfo "帮我梳理示例科技有限公司的互联网资产"
```

## Configure .env

先复制模板：

```bash
copy .env.example .env
```

然后编辑 `.env`，按你实际要使用的平台填写。常见配置如下：

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini

FOFA_EMAIL=
FOFA_API_KEY=
QUAKE_API_KEY=
HUNTER_API_KEY=
SHODAN_API_KEY=
URLSCAN_API_KEY=
SECURITYTRAILS_API_KEY=
WHOISXML_API_KEY=

REQUEST_TIMEOUT=20
HTTP_PROXY=
HTTPS_PROXY=
```

说明：

- `OPENAI_API_KEY`：必填，终端 Agent 用它做任务规划。
- `OPENAI_BASE_URL`：如果你使用代理网关或兼容接口，在这里替换。
- `OPENAI_MODEL`：规划时使用的模型名。
- `FOFA_EMAIL` / `FOFA_API_KEY`、`QUAKE_API_KEY`、`HUNTER_API_KEY` 等：按你要启用的平台填写，没填的平台不会参与执行。
- `REQUEST_TIMEOUT`：平台请求超时，单位秒。
- `HTTP_PROXY` / `HTTPS_PROXY`：有代理时再填。

## Make `askinfo` Available In Terminal

最简单的方式是：

1. 进入项目目录
2. 激活虚拟环境
3. 执行 `pip install -e .`

这样当前虚拟环境里会自动生成 `askinfo` 命令，不需要再手动写启动脚本。

如果你想在普通终端里直接使用 `askinfo`，需要把命令所在的 `Scripts` 目录加入 `PATH`。

Windows 常见有两种方式：

1. 使用项目虚拟环境

把下面目录加入 `PATH`：

```text
<项目路径>\.venv\Scripts
```

然后重新打开终端，就可以直接执行：

```bash
askinfo --doctor
```

2. 使用当前用户的 Python 安装目录

如果你不是装在虚拟环境，而是执行了用户级安装，那么通常需要把类似下面的目录加入 `PATH`：

```text
%USERPROFILE%\AppData\Roaming\Python\Python310\Scripts
```

不同 Python 版本号会不同，比如 `Python311`、`Python312`。

## Usage

检查运行环境：

```bash
askinfo --doctor
```

执行主流程：

```bash
askinfo "帮我梳理示例科技有限公司的互联网资产，重点关注登录页和后台"
```

指定输出文件：

```bash
askinfo "帮我梳理示例科技有限公司的互联网资产" --output .\tmp\report.xlsx
```

如果你不想安装命令，也可以继续使用：

```bash
python agent.py "帮我梳理示例科技有限公司的互联网资产"
```

## Output

- 默认输出目录：`.\tmp\`
- 默认输出格式：`xlsx`

## Repository Layout

- `agent.py`: 仓库内直接运行入口
- `src/asset_mapping_agent/cli.py`: `askinfo` 命令入口
- `src/asset_mapping_agent/`: 核心实现
- `prompts/intent_and_plan.md`: Agent 规划提示词
- `.env.example`: 环境变量模板

## Notes

- 项目发布名是 `askinfo`，当前 Python 包导入名仍为 `asset_mapping_agent`。
- 仓库中的公司名、地域和域名示例均为通用占位信息，不代表真实客户数据。
