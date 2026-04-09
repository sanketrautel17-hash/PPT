class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class TemplateParseError(AppError):
    pass


class ValidationError(AppError):
    pass


class RenderError(AppError):
    pass
