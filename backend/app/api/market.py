"""
CryptoAnalyzer — Market Management API
Manage news sources, symbols, and suggested coins.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import httpx

from app.core.database import get_db
from app.core.config import get_settings
from app.api.deps import require_admin, get_current_user
from app.models.user import User
from app.models.trade import SupportedSymbol, TrustedNewsSource
from app.schemas.market import (
    NewsSourceCreate, NewsSourceUpdate, NewsSourceResponse,
    SymbolCreate, SymbolUpdate, SymbolResponse, SuggestedCoin,
)

router = APIRouter(prefix="/api/market", tags=["Market"])
settings = get_settings()

# ===== News Sources =====

SUGGESTED_SOURCES = [
    {"name": "CoinDesk", "url": "https://coindesk.com"},
    {"name": "Reuters", "url": "https://reuters.com"},
    {"name": "Bloomberg", "url": "https://bloomberg.com"},
    {"name": "The Block", "url": "https://theblock.co"},
    {"name": "Decrypt", "url": "https://decrypt.co"},
    {"name": "CoinTelegraph", "url": "https://cointelegraph.com"},
    {"name": "CryptoSlate", "url": "https://cryptoslate.com"},
    {"name": "BeInCrypto", "url": "https://beincrypto.com"},
    {"name": "Blockworks", "url": "https://blockworks.co"},
    {"name": "DL News", "url": "https://dlnews.com"},
]


@router.get("/news-sources", response_model=List[NewsSourceResponse])
async def list_news_sources(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TrustedNewsSource).order_by(TrustedNewsSource.created_at.desc()))
    return result.scalars().all()


@router.get("/news-sources/suggestions")
async def get_suggested_sources(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get already added sources
    result = await db.execute(select(TrustedNewsSource.name))
    existing = {r for r in result.scalars().all()}
    return [s for s in SUGGESTED_SOURCES if s["name"] not in existing]


@router.post("/news-sources", response_model=NewsSourceResponse, status_code=status.HTTP_201_CREATED)
async def add_news_source(
    data: NewsSourceCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(TrustedNewsSource).where(TrustedNewsSource.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="المصدر موجود بالفعل")

    source = TrustedNewsSource(
        name=data.name,
        url=data.url,
        is_active=data.is_active,
        is_suggested=data.name in [s["name"] for s in SUGGESTED_SOURCES],
    )
    db.add(source)
    await db.flush()
    return source


@router.patch("/news-sources/{source_id}", response_model=NewsSourceResponse)
async def update_news_source(
    source_id: str,
    data: NewsSourceUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TrustedNewsSource).where(TrustedNewsSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="المصدر غير موجود")

    if data.name is not None: source.name = data.name
    if data.url is not None: source.url = data.url
    if data.is_active is not None: source.is_active = data.is_active

    await db.flush()
    return source


@router.delete("/news-sources/{source_id}")
async def delete_news_source(
    source_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TrustedNewsSource).where(TrustedNewsSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="المصدر غير موجود")
    await db.delete(source)
    await db.flush()
    return {"message": "تم حذف المصدر"}


# ===== Symbols =====

@router.get("/symbols", response_model=List[SymbolResponse])
async def list_symbols(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SupportedSymbol).order_by(SupportedSymbol.created_at.desc()))
    return result.scalars().all()


@router.post("/symbols", response_model=SymbolResponse, status_code=status.HTTP_201_CREATED)
async def add_symbol(
    data: SymbolCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(SupportedSymbol).where(SupportedSymbol.symbol == data.symbol))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="العملة موجودة بالفعل")

    symbol = SupportedSymbol(
        symbol=data.symbol,
        base_asset=data.base_asset,
        quote_asset=data.quote_asset,
        is_default=data.is_default,
        is_active=data.is_active,
        min_trade_amount=data.min_trade_amount,
    )
    db.add(symbol)
    await db.flush()
    return symbol


@router.patch("/symbols/{symbol_id}", response_model=SymbolResponse)
async def update_symbol(
    symbol_id: str,
    data: SymbolUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SupportedSymbol).where(SupportedSymbol.id == symbol_id))
    sym = result.scalar_one_or_none()
    if not sym:
        raise HTTPException(status_code=404, detail="العملة غير موجودة")

    if data.is_active is not None: sym.is_active = data.is_active
    if data.is_default is not None: sym.is_default = data.is_default
    if data.min_trade_amount is not None: sym.min_trade_amount = data.min_trade_amount

    await db.flush()
    return sym


@router.delete("/symbols/{symbol_id}")
async def delete_symbol(
    symbol_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SupportedSymbol).where(SupportedSymbol.id == symbol_id))
    sym = result.scalar_one_or_none()
    if not sym:
        raise HTTPException(status_code=404, detail="العملة غير موجودة")
    await db.delete(sym)
    await db.flush()
    return {"message": "تم حذف العملة"}


# ===== Suggested Coins (from CoinGecko) =====

@router.get("/suggested-coins", response_model=List[SuggestedCoin])
async def get_suggested_coins(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get top coins from CoinGecko as suggestions."""
    # Get existing symbols to exclude
    result = await db.execute(select(SupportedSymbol.base_asset))
    existing_bases = {r.upper() for r in result.scalars().all()}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.COINGECKO_BASE_URL}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": 30,
                    "page": 1,
                },
                timeout=15,
            )
            resp.raise_for_status()
            coins = resp.json()

        suggestions = []
        for coin in coins:
            sym = coin.get("symbol", "").upper()
            if sym not in existing_bases:
                suggestions.append(SuggestedCoin(
                    symbol=f"{sym}USDT",
                    name=coin.get("name", ""),
                    current_price=coin.get("current_price", 0) or 0,
                    market_cap=coin.get("market_cap", 0) or 0,
                    price_change_24h=coin.get("price_change_percentage_24h", 0) or 0,
                    volume_24h=coin.get("total_volume", 0) or 0,
                ))
        return suggestions[:15]
    except Exception:
        return []
