class AppError(Exception):
    """Domain error carrying an HTTP status and a stable machine-readable code."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def unauthorized(message: str = "Not authenticated", code: str = "unauthorized") -> AppError:
    return AppError(401, code, message)


def forbidden(message: str = "You do not have permission to do this", code: str = "forbidden") -> AppError:
    return AppError(403, code, message)


def not_found(message: str = "Not found", code: str = "not_found") -> AppError:
    return AppError(404, code, message)


def conflict(message: str, code: str = "conflict") -> AppError:
    return AppError(409, code, message)