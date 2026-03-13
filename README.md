# askinfo

`askinfo` 是一个终端优先的资产收集 Agent。当前开源版本面向直接命令行使用，核心入口是：

```bash
askinfo "帮我梳理示例科技有限公司的互联网资产，重点关注登录页和后台"
```

它会完成自然语言规划、多平台查询、资产归一化、去重归并、有效性验证和 `xlsx` 报告导出。

## Requirements

- Python `3.10+`
- 可用的 OpenAI-compatible 接口
- 至少一个可用的资产平台 API 凭据

## Install

如果你希望在任意目录、任意新终端里都能直接执行 `askinfo`，推荐使用用户级安装：

```bash
python -m pip install -r requirements.txt
python -m pip install --user .
```

安装完成后，直接在普通终端里使用：

```bash
askinfo --doctor
askinfo "帮我梳理示例科技有限公司的互联网资产"
```

如果系统提示找不到 `askinfo`，请确认下面目录已经加入 `PATH`：

```text
C:\Users\<你的用户名>\AppData\Roaming\Python\Python310\Scripts
```

不同 Python 版本号会不同，比如 `Python311`、`Python312`。

修改 `PATH` 后，需要重新打开终端。

## Configure `.env`

你可以在项目目录里放 `.env`，也可以放全局配置文件。推荐全局方式，这样在任何目录执行 `askinfo` 都能自动读取。

推荐全局配置路径：

```text
C:\Users\<你的用户名>\AppData\Roaming\askinfo\.env
```

如果你想从项目模板复制，可以先执行：

```bash
copy .env.example %APPDATA%\askinfo\.env
```

`askinfo` 默认按下面顺序查找配置文件：

1. 当前目录的 `.env`
2. `%APPDATA%\askinfo\.env`
3. `~\.askinfo\.env`

你也可以显式指定：

```bash
askinfo --env-file C:\path\to\custom.env "你的任务文本"
```

常见配置示例：

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
OPENAI_TIMEOUT=60

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
- 平台密钥按需填写，没填的平台不会参与执行。
- `REQUEST_TIMEOUT`：平台请求超时，单位秒。
- `HTTP_PROXY` / `HTTPS_PROXY`：有代理时再填。

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

如果你不想安装命令，也可以在项目目录里继续用：

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
- 请不要把你的真实 `.env` 提交到仓库；版本控制中只保留 `.env.example`。
