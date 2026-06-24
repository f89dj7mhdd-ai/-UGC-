"""観光地名の多言語表記をWikidataから自動取得する（要件「任意の観光地」対応）.

内蔵辞書はカバー範囲が限られるため、辞書に無い地名はWikidataの多言語ラベルを
取得して検索・照合に使う。標準ライブラリ(urllib)のみ。取得失敗時は静かに空を返し、
内蔵辞書／地名そのものにフォールバックする。

一度取得した結果は data/alias_cache.json にキャッシュし、再実行やオフラインでも
再利用できる（デモの再現性のため）。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

_API = "https://www.wikidata.org/w/api.php"
_CACHE = Path(__file__).resolve().parent.parent / "data" / "alias_cache.json"

# 取得対象言語（狙う市場）。zh は繁体・簡体も拾う。
_TARGET_LANGS = ["ja", "en", "zh", "zh-hant", "zh-hans", "ko", "th"]

_HEADERS = {"User-Agent": "tourism-ugc-mvp/0.3 (interview prototype)"}


def _has_cjk(s: str) -> bool:
    return any("぀" <= c <= "鿿" or "가" <= c <= "힣" for c in s)


def _load_cache() -> dict:
    try:
        return json.loads(_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(d: dict) -> None:
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


_WIKI_JA = "https://ja.wikipedia.org/w/api.php"
# Wikipedia言語間リンクで辿る対象言語版（その言語でのタイトル＝地名表記）
_WIKI_LANGS = ("en", "zh", "ko", "th")


def _get_url(base: str, params: dict) -> dict:
    url = f"{base}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))


def _get(params: dict) -> dict:
    return _get_url(_API, params)


# ---- Wikipedia 言語間リンク（主経路） --------------------------------------
def _wiki_search_titles(place: str, limit: int = 5) -> list[str]:
    data = _get_url(_WIKI_JA, {
        "action": "query", "list": "search", "srsearch": place,
        "srlimit": limit, "format": "json",
    })
    return [it["title"] for it in data.get("query", {}).get("search", [])]


def _wiki_langlinks(titles: list[str]) -> dict[str, dict]:
    """記事タイトル → {言語: その言語版タイトル} を返す（リダイレクト追従）。"""
    data = _get_url(_WIKI_JA, {
        "action": "query", "titles": "|".join(titles), "prop": "langlinks",
        "lllimit": "500", "redirects": "1", "format": "json",
    })
    out: dict[str, dict] = {}
    for p in data.get("query", {}).get("pages", {}).values():
        out[p.get("title", "")] = {x["lang"]: x.get("*", "") for x in p.get("langlinks", [])}
    return out


def _wiki_aliases(place: str) -> list[str]:
    """日本語版Wikipediaの検索＋言語間リンクで多言語地名を得る。

    候補記事のうち、対象言語版（en/zh/ko/th）のリンクが最も揃っている記事を選ぶ。
    都市・観光地の記事は多言語版が揃いやすく、姓などの曖昧項目を避けられる。
    """
    titles = _wiki_search_titles(place)
    if not titles:
        return []
    pages = _wiki_langlinks(titles)
    best_title, best_score, best_ll = None, -1, {}
    for t in titles:  # 検索順を同点時の優先に
        ll = pages.get(t, {})
        score = sum(1 for lg in _WIKI_LANGS if lg in ll)
        if score > best_score:
            best_title, best_score, best_ll = t, score, ll
    if best_title is None:
        return []
    values = [best_title] + [best_ll[lg] for lg in _WIKI_LANGS if lg in best_ll]
    return _normalize(values)


# 狙う市場の言語（この言語のラベルが揃っている項目を優先する）
_FOREIGN_LANGS = ("zh", "zh-hant", "zh-hans", "ko", "th")


def _search_entities(place: str, limit: int = 5) -> list[str]:
    lang = "ja" if _has_cjk(place) else "en"
    data = _get({
        "action": "wbsearchentities", "search": place, "language": lang,
        "uselang": lang, "format": "json", "type": "item", "limit": limit,
    })
    return [it["id"] for it in data.get("search", []) if it.get("id")]


def _fetch_entities(qids: list[str]) -> dict:
    """複数項目のラベルをまとめて取得（ids はパイプ区切りで一括）。"""
    data = _get({
        "action": "wbgetentities", "ids": "|".join(qids), "props": "labels",
        "languages": "|".join(_TARGET_LANGS), "format": "json",
    })
    return data.get("entities", {})


def _score(labels: dict) -> tuple[int, int]:
    """項目の優先度。狙う言語(中韓タイ)のラベル数を最優先、次に総ラベル数。"""
    foreign = sum(1 for lg in _FOREIGN_LANGS if lg in labels)
    return (foreign, len(labels))


def _select_best_labels(entities: dict, order: list[str]) -> dict:
    """候補の中から、狙う言語ラベルが最も揃っている項目のラベル辞書を返す。

    検索順(order)を同点時の優先に使う。ネット非依存で単体テスト可能。
    """
    best: dict = {}
    best_score = (-1, -1)
    for qid in order:
        labels = entities.get(qid, {}).get("labels", {})
        if not labels:
            continue
        sc = _score(labels)
        if sc > best_score:
            best_score, best = sc, labels
    return best


def _label_values(labels: dict) -> list[str]:
    return [v["value"] for v in labels.values() if v.get("value")]


# 行政区分の接尾辞などを除いた「検索に使いやすい核」も併せて作る。
# 例: "Toyama Prefecture" → "Toyama" / "富山県" → "富山"
_SUFFIX_EN = re.compile(r"\s+(Prefecture|Province|City|Region)\b", re.IGNORECASE)
_SUFFIX_JP = re.compile(r"(県|府|市|区|町|村|郡)$")
_SUFFIX_KO = re.compile(r"(시|도|군|구|부)$")  # 韓国語版タイトルの市/道/郡/区/府
_PREFIX_TH = re.compile(r"^(จังหวัด|เมือง)\s*")  # タイ語の県/市の接頭辞
_PARENS = re.compile(r"\s*[\(（].*?[\)）]")


def _normalize(labels: list[str]) -> list[str]:
    out: list[str] = []
    for lb in labels:
        out.append(lb)
        # "Beppu, Ōita" のようなカンマ付き英語版タイトルは先頭部分を核にする
        core = lb.split(",")[0].strip()
        core = _PARENS.sub("", core).strip()
        core = _PREFIX_TH.sub("", core).strip()
        core = _SUFFIX_EN.sub("", core).strip()
        core = _SUFFIX_JP.sub("", core).strip()
        core = _SUFFIX_KO.sub("", core).strip()
        # ガード: 削った結果が短すぎる場合は採用しない。
        # 「別府」「甲府」など、接尾辞に見える文字が地名の一部のケースを壊さない
        #（例: 別府→別 を防ぐ。残り1文字は地名として不正なので捨てる）。
        if core and core != lb and len(core) >= 2:
            out.append(core)
    return list(dict.fromkeys(o for o in out if o))


def inspect(place: str) -> None:
    """診断用：Wikipedia候補記事と言語間リンク、最終結果を表示する。"""
    print(f"=== Wikipedia 候補記事（{place}）===")
    try:
        titles = _wiki_search_titles(place)
        pages = _wiki_langlinks(titles) if titles else {}
        for t in titles:
            ll = pages.get(t, {})
            langs = {lg: ll[lg] for lg in _WIKI_LANGS if lg in ll}
            print(f"  {t!r}  langs={langs}")
    except Exception as e:
        print("  Wikipedia取得エラー:", repr(e))
    print("=== 最終結果（fetch_aliases）===")
    print(" ", fetch_aliases(place, use_cache=False))


def _wikidata_aliases(place: str) -> list[str]:
    """Wikidataの曖昧検索による取得（フォールバック）。"""
    qids = _search_entities(place)
    if not qids:
        return []
    entities = _fetch_entities(qids)
    best = _select_best_labels(entities, qids)
    return _normalize(_label_values(best))


def fetch_aliases(place: str, use_cache: bool = True) -> list[str]:
    """多言語の地名表記を取得する（取得失敗時は []）。

    主経路：Wikipedia言語間リンク（都市・観光地の解決に強い）。
    補助：Wikidata曖昧検索。両者を統合して返す。
    """
    cache = _load_cache() if use_cache else {}
    if use_cache and place in cache:
        return cache[place]

    labels: list[str] = []
    try:
        labels = _wiki_aliases(place)
    except Exception:
        labels = []
    # Wikipediaで外国語版が得られなければWikidataで補う
    foreign = any(_has_cjk(x) or any("ก" <= c <= "๛" for c in x)
                  for x in labels if x.lower() != place.lower())
    if not labels or not foreign:
        try:
            labels = list(dict.fromkeys([*labels, *_wikidata_aliases(place)]))
        except Exception:
            pass

    if use_cache and labels:
        cache[place] = labels
        _save_cache(cache)
    return labels
