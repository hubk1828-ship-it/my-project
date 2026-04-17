from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.core.database import get_db
from app.core.security import encrypt_api_key, decrypt_api_key
from app.api.deps import get_current_user, verify_own_resource
from app.models.user import User
from app.models.wallet import Wallet, WalletBalance
from app.schemas.wallet import WalletConnect, WalletResponse, WalletBalanceResponse, BalanceItem
from app.services.binance_client import BinanceClient, verify_api_key, get_prices_batch

router = APIRouter(prefix="/api/wallets", tags=["Wallets"])


@router.post("/connect", response_model=WalletResponse, status_code=status.HTTP_201_CREATED)
async def connect_wallet(
    data: WalletConnect,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Connect exchange wallet. Validates API key before saving."""
    # Verify API key is valid
    is_valid = await verify_api_key(data.api_key, data.api_secret)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="مفتاح API غير صالح — تحقق من الصلاحيات")

    # Check for existing wallet on same exchange
    existing = await db.execute(
        select(Wallet).where(Wallet.user_id == user.id, Wallet.exchange == data.exchange)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"لديك محفظة {data.exchange} مربوطة بالفعل")

    # Encrypt and save
    wallet = Wallet(
        user_id=user.id,
        exchange=data.exchange,
        api_key_encrypted=encrypt_api_key(data.api_key),
        api_secret_encrypted=encrypt_api_key(data.api_secret),
        label=data.label,
    )
    db.add(wallet)
    await db.flush()
    return wallet


@router.delete("/disconnect/{wallet_id}")
async def disconnect_wallet(
    wallet_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect (delete) a wallet."""
    result = await db.execute(select(Wallet).where(Wallet.id == wallet_id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="المحفظة غير موجودة")
    verify_own_resource(wallet.user_id, user)

    await db.delete(wallet)
    await db.flush()
    return {"message": "تم فصل المحفظة بنجاح"}


@router.get("/balance", response_model=List[WalletBalanceResponse])
async def get_balance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all wallet balances for current user."""
    result = await db.execute(
        select(Wallet).where(Wallet.user_id == user.id, Wallet.is_active == True)
    )
    wallets = result.scalars().all()

    responses = []
    for wallet in wallets:
        try:
            api_key = decrypt_api_key(wallet.api_key_encrypted)
            api_secret = decrypt_api_key(wallet.api_secret_encrypted)
            client = BinanceClient(api_key, api_secret)
            raw_balances = await client.get_balances()

            # Get USD prices
            symbols = [f"{b['asset']}USDT" for b in raw_balances if b["asset"] != "USDT"]
            prices = await get_prices_batch(symbols) if symbols else {}

            assets = []
            total_usd = 0.0
            for b in raw_balances:
                free = float(b["free"])
                locked = float(b["locked"])
                if b["asset"] == "USDT":
                    usd_val = free + locked
                else:
                    price = prices.get(f"{b['asset']}USDT", 0)
                    usd_val = (free + locked) * price

                total_usd += usd_val
                assets.append(BalanceItem(
                    asset=b["asset"],
                    free_balance=free,
                    locked_balance=locked,
                    usd_value=round(usd_val, 2),
                ))

            # Update DB balances
            for asset_item in assets:
                existing = await db.execute(
                    select(WalletBalance).where(
                        WalletBalance.wallet_id == wallet.id,
                        WalletBalance.asset == asset_item.asset,
                    )
                )
                balance_record = existing.scalar_one_or_none()
                if balance_record:
                    balance_record.free_balance = asset_item.free_balance
                    balance_record.locked_balance = asset_item.locked_balance
                else:
                    db.add(WalletBalance(
                        wallet_id=wallet.id,
                        asset=asset_item.asset,
                        free_balance=asset_item.free_balance,
                        locked_balance=asset_item.locked_balance,
                    ))

            responses.append(WalletBalanceResponse(
                wallet_id=wallet.id,
                exchange=wallet.exchange,
                total_usd=round(total_usd, 2),
                assets=assets,
            ))
        except Exception as e:
            responses.append(WalletBalanceResponse(
                wallet_id=wallet.id,
                exchange=wallet.exchange,
                total_usd=0,
                assets=[],
            ))

    await db.flush()
    return responses


@router.get("/", response_model=List[WalletResponse])
async def list_wallets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's connected wallets (without API keys)."""
    result = await db.execute(
        select(Wallet).where(Wallet.user_id == user.id).order_by(Wallet.created_at.desc())
    )
    return result.scalars().all()
