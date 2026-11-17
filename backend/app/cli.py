import argparse
import asyncio
from getpass import getpass

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import DEMO_ADMIN_EMAIL, Settings
from app.core.errors import AuthError
from app.schemas.auth import DisplayName, Email, Password
from app.services.account_events import AccountEvents
from app.services.auth_service import AuthService
from app.services.settings_service import SettingsService


async def create_admin(email: str, name: str, password: str) -> None:
    config = Settings()
    engine = create_async_engine(config.database_url.get_secret_value(), hide_parameters=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            service = AuthService(
                config.jwt_secret.get_secret_value(), "", SettingsService(), AccountEvents()
            )
            await service.create_account(db, email, name, password, role="admin")
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Quản lý tài khoản hệ thống.")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--display-name", default="Admin")
    commands.add_parser("create-demo-admin")
    args = parser.parse_args()
    try:
        if args.command == "create-demo-admin":
            if Settings().env != "dev":
                parser.error("Tài khoản demo chỉ được tạo ở môi trường dev.")
            asyncio.run(create_admin(DEMO_ADMIN_EMAIL, "Demo Admin", "admin123"))
            print("Đã tạo tài khoản quản trị demo admin.")
            return 0
        email = TypeAdapter(Email).validate_python(args.email)
        name = TypeAdapter(DisplayName).validate_python(args.display_name)
        password = getpass("Mật khẩu admin: ")
        if password != getpass("Nhập lại mật khẩu: "):
            parser.error("Hai mật khẩu phải khớp nhau.")
        TypeAdapter(Password).validate_python(password)
        asyncio.run(create_admin(email, name, password))
    except ValidationError:
        parser.error("Kiểm tra email, tên hiển thị, độ dài mật khẩu và biến môi trường.")
    except AuthError as exc:
        parser.error(str(exc.code))
    print(f"Đã tạo admin {email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
