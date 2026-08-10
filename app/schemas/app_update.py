from typing import Optional

from pydantic import BaseModel


class AppUpdateResponse(BaseModel):
    """Ответ на вопрос приложения «я не устарел?»."""

    current_version: str
    latest_version: str
    # Есть версия свежее — предложить обновиться, но дать закрыть диалог.
    update_available: bool
    # Версия ниже минимально поддерживаемой — работать дальше нельзя.
    update_required: bool
    # Куда вести по кнопке «Обновить».
    store_url: str
    message: Optional[str] = None
