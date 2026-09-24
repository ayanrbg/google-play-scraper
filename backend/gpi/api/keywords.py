"""Search-demand niches."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from gpi.api.deps import Ctx, feature, get_db
from gpi.catalog import GENRE_NAMES_RU
from gpi.models import App, GameMetrics, Keyword, KeywordRank

router = APIRouter(prefix="/api")

SORTS = {
    "opportunity": Keyword.opportunity, "demand": Keyword.demand, "competition": Keyword.competition,
    "young_share": Keyword.young_share, "young_best_installs": Keyword.young_best_installs,
    "top_median_installs": Keyword.top_median_installs, "term": Keyword.term, "first_seen": Keyword.first_seen,
}


def kw_payload(k: Keyword) -> dict:
    return {
        "id": k.id, "term": k.term, "lang": k.lang, "country": k.country, "seed": k.seed,
        "demand": k.demand, "competition": k.competition, "opportunity": k.opportunity,
        "top_median_installs": k.top_median_installs, "top_avg_rating": k.top_avg_rating,
        "young_share": k.young_share, "young_best_installs": k.young_best_installs,
        "brand_share": k.brand_share, "title_match_share": k.title_match_share,
        "suggest_prefix_len": k.suggest_prefix_len, "analyzed_at": k.analyzed_at, "first_seen": k.first_seen,
    }


@router.get("/keywords")
def list_keywords(
    q: str | None = None, country: str | None = None,
    min_demand: float | None = None, max_competition: float | None = None,
    min_opportunity: float | None = None, min_young_share: float | None = None,
    max_brand_share: float | None = None, analyzed: bool = True,
    sort: str = "opportunity", dir: str = "desc", page: int = 1, page_size: int = Query(50, le=200),
    ctx: Ctx = Depends(feature("keywords")), db: Session = Depends(get_db),
):
    conds = []
    if q:
        conds.append(func.lower(Keyword.term).like(f"%{q.lower()}%"))
    if country:
        conds.append(Keyword.country == country)
    if min_demand is not None:
        conds.append(Keyword.demand >= min_demand)
    if max_competition is not None:
        conds.append(Keyword.competition <= max_competition)
    if min_opportunity is not None:
        conds.append(Keyword.opportunity >= min_opportunity)
    if min_young_share is not None:
        conds.append(Keyword.young_share >= min_young_share)
    if max_brand_share is not None:
        conds.append(Keyword.brand_share <= max_brand_share)
    if analyzed:
        conds.append(Keyword.analyzed_at.is_not(None))
    col = SORTS.get(sort, Keyword.opportunity)
    stmt = select(Keyword).where(*conds)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = desc(col) if dir == "desc" else asc(col)
    rows = db.scalars(stmt.order_by(order.nulls_last(), Keyword.id)
                      .offset((max(page, 1) - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [kw_payload(k) for k in rows]}


@router.get("/keywords/{keyword_id}")
def keyword_detail(keyword_id: int, ctx: Ctx = Depends(feature("keywords")), db: Session = Depends(get_db)):
    k = db.get(Keyword, keyword_id)
    if not k:
        raise HTTPException(404, "not_found")
    rows = db.execute(
        select(KeywordRank.rank, App, GameMetrics.trend_score, GameMetrics.brand_flags)
        .join(App, App.app_id == KeywordRank.app_id)
        .outerjoin(GameMetrics, GameMetrics.app_id == App.app_id)
        .where(KeywordRank.keyword_id == keyword_id).order_by(KeywordRank.rank)
    ).all()
    related = db.scalars(select(Keyword).where(Keyword.seed == k.seed, Keyword.id != k.id, Keyword.country == k.country)
                         .order_by(Keyword.demand.desc()).limit(20)).all() if k.seed else []
    return {
        "keyword": kw_payload(k),
        "results": [{
            "rank": rank, "app_id": a.app_id, "title": a.title, "developer": a.developer, "icon_url": a.icon_url,
            "genre": GENRE_NAMES_RU.get(a.genre_id or "", a.genre_id), "released": a.released,
            "installs": a.real_installs, "rating": a.score, "trend_score": ts, "brand_flags": flags or [],
        } for rank, a, ts, flags in rows],
        "related": [kw_payload(r) for r in related],
    }
