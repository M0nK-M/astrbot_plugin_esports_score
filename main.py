from datetime import datetime, timedelta, timezone

import aiohttp

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

API_BASE = "https://api.pandascore.co"
GAME_SLUGS = {
    "cs": "csgo", "cs2": "csgo", "csgo": "csgo", "counter-strike": "csgo",
    "lol": "lol", "英雄联盟": "lol", "league": "lol",
    "valorant": "valorant", "无畏契约": "valorant", "瓦": "valorant",
    "dota": "dota2", "dota2": "dota2",
}
STATUS_TEXT = {
    "running": "进行中", "finished": "已结束", "not_started": "未开始",
    "canceled": "已取消", "postponed": "已推迟",
}
CST = timezone(timedelta(hours=8))


def _fmt_time(iso: str | None) -> str:
    if not iso:
        return "时间未定"
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return t.astimezone(CST).strftime("%m-%d %H:%M") + "（北京时间）"
    except ValueError:
        return iso


def _team_names(match: dict) -> list[str]:
    names = []
    for opp in match.get("opponents") or []:
        o = opp.get("opponent") or {}
        names.append(o.get("acronym") or o.get("name") or "?")
    return names


def _matches_team(match: dict, keyword: str) -> bool:
    kw = keyword.lower().strip()
    for opp in match.get("opponents") or []:
        o = opp.get("opponent") or {}
        for field in ("name", "acronym", "slug"):
            if kw in str(o.get(field) or "").lower():
                return True
    return kw in str(match.get("name") or "").lower()


def _describe(match: dict) -> str:
    teams = _team_names(match)
    id_to_name = {}
    for opp in match.get("opponents") or []:
        o = opp.get("opponent") or {}
        id_to_name[o.get("id")] = o.get("acronym") or o.get("name")
    scores = {r.get("team_id"): r.get("score", 0) for r in match.get("results") or []}
    vs = " vs ".join(teams) if teams else (match.get("name") or "未知对阵")
    if len(teams) == 2 and scores:
        ids = [(opp.get("opponent") or {}).get("id") for opp in match.get("opponents")]
        score = f"{scores.get(ids[0], 0)}:{scores.get(ids[1], 0)}"
    else:
        score = "暂无比分"
    league = (match.get("league") or {}).get("name") or ""
    serie = (match.get("serie") or {}).get("full_name") or ""
    tournament = (match.get("tournament") or {}).get("name") or ""
    event = " ".join(x for x in (league, serie, tournament) if x)
    status = STATUS_TEXT.get(match.get("status"), match.get("status") or "")
    bo = match.get("number_of_games")
    bo_text = f"BO{bo}" if bo else ""
    winner = id_to_name.get(match.get("winner_id"))
    when = _fmt_time(match.get("begin_at") or match.get("scheduled_at"))
    parts = [event, vs, status, f"大比分 {score}", bo_text, when]
    if winner and match.get("status") == "finished":
        parts.append(f"胜者 {winner}")
    return " | ".join(p for p in parts if p)


async def _api_get(token: str, path: str, params: dict) -> tuple[object | None, str]:
    """返回 (数据, 错误提示)。成功时错误提示为空字符串。"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_BASE}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(f"[esports_score] {path} HTTP {resp.status}: {text[:200]}")
                    return None, f"电竞数据接口暂时查不到（HTTP {resp.status}）。"
                return await resp.json(), ""
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[esports_score] {path} 请求失败: {e}")
        return None, "电竞数据接口暂时连不上。"


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "未定"
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return t.astimezone(CST).strftime("%Y-%m-%d")
    except ValueError:
        return iso


def _describe_team(team: dict) -> str:
    name = team.get("name") or "?"
    acronym = team.get("acronym")
    title = f"{name}（{acronym}）" if acronym and acronym != name else name
    parts = [title]
    if team.get("location"):
        parts.append(f"地区 {team['location']}")
    players = []
    for p in team.get("players") or []:
        nick = p.get("name") or "?"
        extra = []
        real = " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
        if real:
            extra.append(real)
        if p.get("nationality"):
            extra.append(p["nationality"])
        if p.get("role"):
            extra.append(p["role"])
        players.append(f"{nick}（{'，'.join(extra)}）" if extra else nick)
    parts.append("选手：" + ("、".join(players) if players else "暂无阵容数据"))
    return " | ".join(parts)


def _describe_tournament(t: dict) -> str:
    league = (t.get("league") or {}).get("name") or ""
    serie = (t.get("serie") or {}).get("full_name") or ""
    stage = t.get("name") or ""
    event = " ".join(x for x in (league, serie, stage) if x) or "未知赛事"
    parts = [event, f"{_fmt_date(t.get('begin_at'))} 至 {_fmt_date(t.get('end_at'))}（北京时间）"]
    if t.get("tier"):
        parts.append(f"级别 {str(t['tier']).upper()}")
    if t.get("prizepool"):
        parts.append(f"奖金 {t['prizepool']}")
    teams = [x.get("acronym") or x.get("name") for x in (t.get("teams") or [])]
    teams = [x for x in teams if x]
    if teams:
        shown = "、".join(teams[:16])
        if len(teams) > 16:
            shown += f" 等 {len(teams)} 支"
        parts.append("参赛队伍：" + shown)
    winner_id = t.get("winner_id")
    if winner_id:
        for x in t.get("teams") or []:
            if x.get("id") == winner_id:
                parts.append(f"冠军 {x.get('acronym') or x.get('name')}")
                break
    return " | ".join(parts)


def _matches_tournament(t: dict, keyword: str) -> bool:
    kw = keyword.lower().strip()
    fields = [
        t.get("name"), t.get("slug"),
        (t.get("league") or {}).get("name"), (t.get("league") or {}).get("slug"),
        (t.get("serie") or {}).get("full_name"), (t.get("serie") or {}).get("slug"),
    ]
    return any(kw in str(f or "").lower() for f in fields)


@register("astrbot_plugin_esports_score", "M0nK", "通过 PandaScore 查询电竞比分、战队阵容和赛事信息", "1.1.0")
class EsportsScore(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    @filter.llm_tool(name="get_esports_matches")
    async def get_esports_matches(
        self, event: AstrMessageEvent, game: str, status: str, team: str = ""
    ) -> str:
        """查询电竞比赛的比分和赛程（数据来自 PandaScore）。有人问电竞比赛的比分、结果、赛程时使用。返回的是每支队伍赢下的地图数（大比分），不是每回合的实时比分。

        Args:
            game(string): 游戏，可选 cs、lol、valorant、dota2
            status(string): running 表示正在进行，past 表示最近结束，upcoming 表示即将开始
            team(string): 可选，队伍名或缩写，用来筛选某支队伍的比赛，比如 NAVI、Vitality、T1；不需要筛选时留空
        """
        token = (self.config.get("pandascore_token") or "").strip()
        if not token:
            return "比分查询插件还没有配置 PandaScore Token。"
        slug = GAME_SLUGS.get((game or "").lower().strip(), "csgo")
        status = (status or "running").lower().strip()
        if status not in ("running", "past", "upcoming"):
            status = "running"
        params = {"per_page": 50 if team else 10}
        if status == "past":
            params["sort"] = "-end_at"
        elif status == "upcoming":
            params["sort"] = "begin_at"
        data, err = await _api_get(token, f"/{slug}/matches/{status}", params)
        if err:
            return err
        if not isinstance(data, list):
            return "比分接口返回的数据格式不对。"
        if team:
            data = [m for m in data if _matches_team(m, team)]
        limit = int(self.config.get("max_results") or 5)
        data = data[:limit]
        if not data:
            label = {"running": "正在进行的", "past": "最近结束的", "upcoming": "即将开始的"}[status]
            who = f"{team} 的" if team else ""
            return f"没有查到{who}{label}比赛。"
        return "\n".join(_describe(m) for m in data)

    @filter.llm_tool(name="get_esports_team")
    async def get_esports_team(self, event: AstrMessageEvent, game: str, team: str) -> str:
        """查询电竞战队的资料和当前阵容（数据来自 PandaScore）。有人问某支战队现在有哪些选手、阵容是谁时使用。

        Args:
            game(string): 游戏，可选 cs、lol、valorant、dota2
            team(string): 队伍名或缩写，比如 NAVI、Vitality、T1、Fnatic
        """
        token = (self.config.get("pandascore_token") or "").strip()
        if not token:
            return "电竞查询插件还没有配置 PandaScore Token。"
        team = (team or "").strip()
        if not team:
            return "需要告诉我要查哪支队伍。"
        slug = GAME_SLUGS.get((game or "").lower().strip(), "csgo")
        found: dict[int, dict] = {}
        for field in ("acronym", "name"):
            data, err = await _api_get(
                token, f"/{slug}/teams", {f"search[{field}]": team, "per_page": 10}
            )
            if err:
                return err
            for t in data if isinstance(data, list) else []:
                found.setdefault(t.get("id"), t)
        if not found:
            return f"没有查到叫 {team} 的队伍。"
        kw = team.lower()

        def rank(t: dict) -> tuple:
            exact = kw in (str(t.get("acronym") or "").lower(), str(t.get("name") or "").lower())
            return (not exact, not t.get("players"), len(str(t.get("name") or "")))

        teams = sorted(found.values(), key=rank)[:3]
        return "\n".join(_describe_team(t) for t in teams)

    @filter.llm_tool(name="get_esports_tournaments")
    async def get_esports_tournaments(
        self, event: AstrMessageEvent, game: str, status: str, keyword: str = ""
    ) -> str:
        """查询电竞赛事的时间、级别、奖金和参赛队伍（数据来自 PandaScore）。有人问某个赛事什么时候开始、有哪些队参加、谁拿了冠军时使用。

        Args:
            game(string): 游戏，可选 cs、lol、valorant、dota2
            status(string): running 表示正在进行，upcoming 表示即将开始，past 表示已经结束
            keyword(string): 可选，赛事名关键词，比如 IEM、Major、BLAST、Worlds、VCT；不需要筛选时留空
        """
        token = (self.config.get("pandascore_token") or "").strip()
        if not token:
            return "电竞查询插件还没有配置 PandaScore Token。"
        slug = GAME_SLUGS.get((game or "").lower().strip(), "csgo")
        status = (status or "running").lower().strip()
        if status not in ("running", "past", "upcoming"):
            status = "running"
        params = {"per_page": 50 if keyword else 20}
        if status == "past":
            params["sort"] = "-end_at"
        elif status == "upcoming":
            params["sort"] = "begin_at"
        data, err = await _api_get(token, f"/{slug}/tournaments/{status}", params)
        if err:
            return err
        if not isinstance(data, list):
            return "赛事接口返回的数据格式不对。"
        if keyword:
            data = [t for t in data if _matches_tournament(t, keyword)]
        else:
            # 不指定赛事时，优先给高级别的比赛
            tier_rank = {"s": 0, "a": 1, "b": 2, "c": 3, "d": 4}
            data.sort(key=lambda t: tier_rank.get(str(t.get("tier") or "").lower(), 5))
        limit = int(self.config.get("max_results") or 5)
        data = data[:limit]
        if not data:
            label = {"running": "正在进行的", "past": "最近结束的", "upcoming": "即将开始的"}[status]
            what = f"和 {keyword} 有关的" if keyword else ""
            return f"没有查到{what}{label}赛事。"
        return "\n".join(_describe_tournament(t) for t in data)
