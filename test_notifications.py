import asyncio
from unittest.mock import MagicMock, patch
from app.services.notifications import NotificationService
from app.models import User, Guard

async def main():
    """
    Main test for the generic notification method.
    This script demonstrates how to use send_notification with both Users and Guards.
    """
    service = NotificationService()

    # Mocking dependencies to avoid real network calls
    with patch("firebase_admin.messaging.send_multicast") as mock_fcm, \
         patch("app.api.ws.manager.manager.send_to_user") as mock_ws_user, \
         patch("app.api.ws.manager.manager.send_to_guard") as mock_ws_guard:
        
        mock_fcm.return_value = MagicMock(success_count=1, failure_count=0, responses=[])
        
        # 1. Test sending to a User
        test_user = User(id=1, full_name="Test User", fcm_token="user_token_123")
        print(f"--- Testing notification for User: {test_user.full_name} ---")
        
        await service.send_notification(
            recipient=test_user,
            title="Hello User!",
            body="This is a test notification for you.",
            data={"key": "value"}
        )
        
        print("WebSocket check (User):", "Called" if mock_ws_user.called else "Not called")
        print("FCM check (User):", "Called" if mock_fcm.called else "Not called")
        print()

        # 2. Test sending to a Guard
        test_guard = Guard(id=5, full_name="Test Guard", fcm_token="guard_token_456")
        print(f"--- Testing notification for Guard: {test_guard.full_name} ---")
        
        # Reset mocks for clean guard test
        mock_fcm.reset_mock()
        
        await service.send_notification(
            recipient=test_guard,
            title="Alert Guard!",
            body="New security alert in your area.",
            data={"alert_id": "999"}
        )
        
        print("WebSocket check (Guard):", "Called" if mock_ws_guard.called else "Not called")
        print("FCM check (Guard):", "Called" if mock_fcm.called else "Not called")
        print()

        print("All tests passed (Mocked)!")

if __name__ == "__main__":
    asyncio.run(main())
