# astrbot_plugin_esports_score

一个 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 插件，通过 [PandaScore](https://pandascore.co) 的免费接口，让机器人能查 **CS2、英雄联盟、无畏契约、Dota 2** 的比分、赛程、战队阵容和赛事信息。

插件以 LLM 工具（函数调用）的形式提供，不需要记指令：群友直接问"NAVI 下一场什么时候""现在有什么 CS 比赛在打"，模型会自己调用工具查询，再用人设的口吻回答。

## 功能

| 工具 | 用途 | 示例问题 |
|---|---|---|
| `get_esports_matches` | 正在进行 / 最近结束 / 即将开始的比赛，含大比分、BO 数、开赛时间、胜者，可按队伍筛选 | "T1 昨天赢了吗" "现在几比几了" |
| `get_esports_team` | 战队资料和当前阵容（选手 ID、真名、国籍） | "Vitality 现在谁在打" |
| `get_esports_tournaments` | 赛事的时间、级别、奖金、参赛队伍、冠军，可按关键词筛选 | "IEM 什么时候开始" "最近有什么 CS 大赛" |

时间统一换算成北京时间。

## 能查和不能查

PandaScore 免费套餐只提供赛程、结果和阵容，以下内容 **查不到**（需要付费套餐）：

- 每张图（每一局）分别的胜负，只有整场的大比分，例如 2:1
- 正在进行的这张图的回合比分，例如 9:7
- 选手和队伍的数据，例如 Rating、KDA、ACS
- 赛后时间线、击杀记录等比赛细节

Valorant 在 PandaScore 没有任何实时数据套餐。

## 安装

1. 在 AstrBot WebUI 的插件页面，用本仓库链接安装，或下载 zip 上传。
2. 到 [PandaScore](https://app.pandascore.co/signup) 注册免费账号，在控制台复制 access token。
3. 打开插件配置，填入 Token，保存并重载插件。

### 配置项

| 配置 | 说明 | 默认 |
|---|---|---|
| `pandascore_token` | PandaScore API Token | 空 |
| `max_results` | 每次最多返回给模型的比赛或赛事条数，越多越费 token | 5 |

免费套餐每小时 1000 次请求，聊天使用绰绰有余。

## 人设提示词建议

工具描述已经写明了用途，但在人设里加一句会让模型更稳定地调用，例如：

```
有人问电竞比赛的比分、赛程时，优先用 get_esports_matches 工具查；问某支战队的阵容时，用 get_esports_team；问某个赛事的时间、参赛队伍、冠军时，用 get_esports_tournaments。查到了就直接说结果；对方问正在打的这张图几比几而查不到时，告诉对方去 HLTV 或直播看。
```

## 许可证

MIT
