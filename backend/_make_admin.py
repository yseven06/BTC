import asyncio
from sqlalchemy import text, select
from app.database import async_session_factory, engine
from app.models.user import User

async def main():
    # 1) Sutunu ekle (yoksa)
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            print("is_admin sutunu eklendi/zaten vardi")
        except Exception as e:
            print(f"ALTER hata: {e}")

    # 2) dev@trademinds.io kullaniciyi admin yap
    async with async_session_factory() as db:
        res = await db.execute(select(User).where(User.email == "dev@trademinds.io"))
        u = res.scalar_one_or_none()
        if u is None:
            print("dev@trademinds.io bulunamadi")
            return
        u.is_admin = True
        await db.commit()
        print(f"BASARILI: {u.email} artik admin (is_admin=True)")

asyncio.run(main())
