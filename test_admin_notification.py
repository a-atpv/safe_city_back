import asyncio
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from app.api.routes.admin import send_admin_notification
from app.schemas.admin import NotificationSendRequest
from app.models import CompanyAdmin, User, Guard

async def test_admin_notification_logic():
    print("--- Testing Admin Notification Logic ---")
    
    # Setup mocks
    mock_db = MagicMock()
    mock_admin = CompanyAdmin(id=1, security_company_id=10)
    
    # 1. Test sending to a Guard (success)
    mock_guard = Guard(id=5, security_company_id=10, fcm_token="guard_token")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_guard
    mock_db.execute = MagicMock(return_value=asyncio.Future())
    mock_db.execute.default_value = mock_result
    
    # Use a side_effect to return the mock_result for the await
    async def mock_execute(*args, **kwargs):
        return mock_result
    mock_db.execute.side_effect = mock_execute

    request_data = NotificationSendRequest(
        recipient_type="guard",
        recipient_id=5,
        title="Test Title",
        body="Test Body"
    )

    with patch("app.services.notifications.notification_service.send_notification") as mock_send:
        response = await send_admin_notification(request_data, mock_admin, mock_db)
        print("Success Case (Guard):", response.message)
        mock_send.assert_called_once()

    # 2. Test sending to a Guard from another company (failure)
    mock_guard_wrong_company = Guard(id=6, security_company_id=11, fcm_token="token")
    
    async def mock_execute_wrong_company(*args, **kwargs):
        return MagicMock(scalar_one_or_none=lambda: mock_guard_wrong_company)
    mock_db.execute.side_effect = mock_execute_wrong_company

    try:
        await send_admin_notification(request_data, mock_admin, mock_db)
    except HTTPException as e:
        print("Failure Case (Wrong Company):", e.detail)
        assert e.status_code == 403

    # 3. Test recipient not found
    async def mock_execute_not_found(*args, **kwargs):
        return MagicMock(scalar_one_or_none=lambda: None)
    mock_db.execute.side_effect = mock_execute_not_found

    try:
        await send_admin_notification(request_data, mock_admin, mock_db)
    except HTTPException as e:
        print("Failure Case (Not Found):", e.detail)
        assert e.status_code == 404

    print("\nLogic tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_admin_notification_logic())
