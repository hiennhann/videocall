from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.errors import AuthError, ErrorCode

AUTH_ERRORS = {
    ErrorCode.ROOM_NOT_FOUND: (404, "Không tìm thấy phòng."),
    ErrorCode.ROOM_CLOSED: (409, "Phòng đã đóng."),
    ErrorCode.ROOM_FULL: (409, "Phòng đã đầy."),
    ErrorCode.ROOM_LIMIT_REACHED: (409, "Đã đạt số phòng đang mở tối đa."),
    ErrorCode.MODE_NOT_SUPPORTED: (400, "Chế độ phòng chưa được hỗ trợ."),
    ErrorCode.BANNED: (403, "Bạn không thể vào lại phòng này."),
    ErrorCode.ALREADY_IN_ROOM: (409, "Kết nối đã ở một phòng khác."),
    ErrorCode.NOT_IN_ROOM: (403, "Bạn chưa vào phòng."),
    ErrorCode.NOT_ROOM_HOST: (403, "Thao tác này cần quyền host."),
    ErrorCode.CHAT_DISABLED: (403, "Chat trong phòng đang tắt."),
    ErrorCode.SCREEN_SHARE_DISABLED: (403, "Chia sẻ màn hình đang tắt."),
    ErrorCode.PEER_NOT_FOUND: (404, "Không tìm thấy người tham gia trong phòng."),
    ErrorCode.INVALID_PAYLOAD: (422, "Dữ liệu sự kiện không hợp lệ."),
    ErrorCode.ACCOUNT_DISABLED: (403, "Tài khoản đã bị khóa."),
    ErrorCode.PASSWORD_CHANGE_REQUIRED: (403, "Bạn cần đổi mật khẩu trước."),
    ErrorCode.FORBIDDEN: (403, "Bạn không có quyền thực hiện yêu cầu này."),
    ErrorCode.LAST_ADMIN: (409, "Hệ thống cần ít nhất một admin đang hoạt động."),
    ErrorCode.CANNOT_MODIFY_SELF: (409, "Không thể tự đổi quyền, trạng thái hoặc xóa tài khoản."),
    ErrorCode.USER_NOT_FOUND: (404, "Không tìm thấy người dùng."),
    ErrorCode.VALIDATION_ERROR: (422, "Dữ liệu không hợp lệ."),
    ErrorCode.UNKNOWN_SETTING: (422, "Khóa cấu hình không tồn tại."),
    ErrorCode.RATE_LIMITED: (429, "Bạn đã gửi quá nhiều yêu cầu."),
    ErrorCode.REGISTRATION_DISABLED: (403, "Tính năng đăng ký đang tắt."),
    ErrorCode.EMAIL_TAKEN: (409, "Email đã được sử dụng."),
    ErrorCode.INVALID_CREDENTIALS: (401, "Email hoặc mật khẩu không đúng."),
    ErrorCode.INVALID_REFRESH_TOKEN: (401, "Refresh token không hợp lệ."),
    ErrorCode.LOGIN_LOCKED: (429, "Bạn đã thử đăng nhập quá nhiều lần."),
    ErrorCode.GUEST_DISABLED: (403, "Tính năng đăng nhập khách đang tắt."),
    ErrorCode.MAINTENANCE_MODE: (503, "Hệ thống đang bảo trì."),
    ErrorCode.UNAUTHENTICATED: (401, "Bạn cần đăng nhập."),
    ErrorCode.TOKEN_EXPIRED: (401, "Access token đã hết hạn."),
    ErrorCode.TOKEN_INVALID: (401, "Access token không hợp lệ."),
    ErrorCode.GUEST_NOT_ALLOWED: (403, "Tính năng này cần tài khoản đã đăng ký."),
    ErrorCode.WRONG_PASSWORD: (400, "Mật khẩu hiện tại không đúng."),
    ErrorCode.PASSWORD_UNCHANGED: (400, "Mật khẩu mới phải khác mật khẩu hiện tại."),
}


def error_response(
    status: int,
    code: str,
    message: str,
    *,
    details: dict[str, str | dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
        status_code=status,
        headers=headers,
    )


async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    status, message = AUTH_ERRORS[exc.code]
    headers = {}
    if exc.retry_after is not None:
        headers["Retry-After"] = str(exc.retry_after)
    if exc.code in {ErrorCode.UNAUTHENTICATED, ErrorCode.TOKEN_EXPIRED, ErrorCode.TOKEN_INVALID}:
        headers["WWW-Authenticate"] = "Bearer"
    details = {"fields": exc.fields} if exc.fields else None
    return error_response(status, exc.code, message, details=details, headers=headers)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = {}
    for error in exc.errors():
        location = error["loc"]
        name = (
            str(location[1])
            if len(location) > 1 and isinstance(location[1], str)
            else str(location[0])
        )
        fields[name] = "Trường bắt buộc." if error["type"] == "missing" else "Giá trị không hợp lệ."
    return error_response(
        422, "VALIDATION_ERROR", "Dữ liệu không hợp lệ.", details={"fields": fields}
    )


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.state.request_id
    return error_response(
        500,
        "INTERNAL_ERROR",
        "Có lỗi khi xử lý yêu cầu.",
        details={"request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


async def rate_limit_error_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    limit_response = _rate_limit_exceeded_handler(request, exc)
    headers = {
        key: value
        for key, value in limit_response.headers.items()
        if key not in {"content-type", "content-length"}
    }
    return error_response(429, "RATE_LIMITED", "Bạn đã gửi quá nhiều yêu cầu.", headers=headers)
