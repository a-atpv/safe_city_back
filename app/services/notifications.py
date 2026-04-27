from typing import Any, Dict, List, Optional, Union
# from app.api.ws.manager import manager  # Moved inside methods to avoid circular import
from app.models import EmergencyCall, Guard, User
from firebase_admin import messaging
from app.core.firebase import init_firebase
import json
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Central hub for sending real-time notifications to users and guards via WebSockets and FCM.
    """

    async def _send_fcm_notification(
        self, 
        tokens: List[str], 
        title: str, 
        body: str, 
        data: Optional[Dict[str, str]] = None
    ):
        """Helper to send FCM notifications to a list of device tokens with high priority."""
        # Ensure Firebase is initialized
        init_firebase()
        
        if not tokens:
            return

        if data:
            # FCM data values must be strings
            data = {k: str(v) for k, v in data.items()}

        # Prepare platform-specific configs for high priority delivery
        android_config = messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                sound="default",
                click_action="FLUTTER_NOTIFICATION_CLICK",
            )
        )
        
        apns_config = messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    sound="default",
                    badge=1,
                    content_available=True,
                )
            )
        )

        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data,
            tokens=tokens,
            android=android_config,
            apns=apns_config,
        )

        try:
            response = messaging.send_multicast(message)
            logger.info(f"FCM: Successfully sent {response.success_count} messages; {response.failure_count} failed.")
            
            if response.failure_count > 0:
                for idx, resp in enumerate(response.responses):
                    if not resp.success:
                        logger.debug(f"FCM: Failed to send to token {tokens[idx]}: {resp.exception}")
        except Exception as e:
            logger.error(f"FCM: Error sending multicast message: {e}")

    async def notify_call_status_update(self, call: EmergencyCall):
        """Notify the user about a change in their call's status."""
        if not call.user_id:
            return

        payload = {
            "type": "call_status_update",
            "call_id": call.id,
            "status": call.status.value,
            "guard_id": call.guard_id,
            "eta_minutes": call.estimated_arrival_minutes,
        }

        # Include guard details if assigned
        if call.guard:
            payload["guard"] = {
                "id": call.guard.id,
                "full_name": call.guard.full_name,
                "phone": call.guard.phone,
                "image_url": call.guard.avatar_url,
            }

        # 1. Send via WebSocket
        from app.api.ws.manager import manager
        await manager.send_to_user(call.user_id, payload)
        logger.info(f"WS: Notification sent to user {call.user_id} for call {call.id}")

        # 2. Send via FCM
        if call.user and call.user.fcm_token:
            status_texts = {
                "OFFER_SENT": "Поиск ближайшего охранника...",
                "ACCEPTED": "Охранник принял вызов и выехал к вам.",
                "ARRIVED": "Охранник прибыл на место.",
                "COMPLETED": "Вызов успешно завершен.",
                "CANCELLED": "Ваш вызов был отменен.",
            }
            body = status_texts.get(call.status.value, f"Статус вызова обновлен: {call.status.value}")
            
            await self._send_fcm_notification(
                tokens=[call.user.fcm_token],
                title="Обновление статуса вызова",
                body=body,
                data={"call_id": str(call.id), "status": call.status.value}
            )

    async def broadcast_new_emergency(self, guards: List[Guard], call: EmergencyCall):
        """
        Broadcast a new emergency call to all available guards.
        Ensures they all see the call in their "Available Calls" list and get a push.
        """
        all_tokens = [guard.fcm_token for guard in guards if guard.fcm_token]
        
        if not all_tokens:
            logger.info(f"FCM: No active guard tokens found for broadcast of call {call.id}")
            return

        title = "🚨 Экстренный вызов!"
        body = f"Внимание! Новый вызов: {call.address or 'Алматы'}. Все доступные охранники, проверьте список вызовов."
        
        await self._send_fcm_notification(
            tokens=list(set(all_tokens)), # Unique tokens
            title=title,
            body=body,
            data={
                "call_id": str(call.id),
                "type": "new_emergency_broadcast",
                "latitude": str(call.latitude),
                "longitude": str(call.longitude)
            }
        )
        logger.info(f"FCM: Broadcasted emergency call {call.id} to guards.")

    async def notify_new_call_offer(self, guard: Guard, call: EmergencyCall, distance_km: float):
        """Notify a guard about a new incoming call offer."""
        payload = {
            "type": "call_offer",
            "call_id": call.id,
            "status": call.status.value,
            "latitude": call.latitude,
            "longitude": call.longitude,
            "address": call.address,
            "distance_km": round(distance_km, 2),
            "eta_minutes": call.estimated_arrival_minutes,
            "user": {
                "id": call.user.id,
                "full_name": call.user.full_name,
                "phone": call.user.phone,
                "image_url": call.user.avatar_url,
            } if call.user else None
        }

        # 1. Send via WebSocket
        from app.api.ws.manager import manager
        await manager.send_to_guard(guard.id, payload)
        logger.info(f"WS: New call offer notification sent to guard {guard.id}")

        # 2. Send via FCM
        if guard.fcm_token:
            await self._send_fcm_notification(
                tokens=[guard.fcm_token],
                title="Новый вызов!",
                body=f"Нужна ваша помощь! Расстояние: {round(distance_km, 1)} км",
                data={
                    "call_id": str(call.id),
                    "type": "call_offer",
                    "latitude": str(call.latitude),
                    "longitude": str(call.longitude)
                }
            )

    async def notify_call_cancelled(self, user_id: int, call_id: int, reason: str, tokens: List[str] = None):
        """Notify user that their call has been cancelled by the system."""
        payload = {
            "type": "call_cancelled",
            "call_id": call_id,
            "reason": reason,
        }
        
        # 1. Send via WebSocket
        from app.api.ws.manager import manager
        await manager.send_to_user(user_id, payload)
        
        # 2. Send via FCM (if tokens provided)
        if tokens:
            await self._send_fcm_notification(
                tokens=tokens,
                title="Вызов отменен",
                body=f"Ваш вызов был отменен системой. Причина: {reason}",
                data={"call_id": str(call_id), "type": "call_cancelled"}
            )


    async def send_notification(
        self, 
        recipient: Union[User, Guard], 
        title: str, 
        body: str, 
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Send a push notification to a specific user or guard.
        
        Args:
            recipient: The User or Guard model instance.
            title: Title of the notification.
            body: Body text of the notification.
            data: Optional dictionary of extra data strings.
        """
        if not recipient or not recipient.fcm_token:
            logger.warning(f"Notification: No FCM token for recipient {getattr(recipient, 'id', 'unknown')}")
            return

        # 1. Send via WebSocket if possible
        from app.api.ws.manager import manager
        ws_payload = {
            "type": "general_notification",
            "title": title,
            "body": body,
            "data": data or {}
        }
        
        if isinstance(recipient, User):
            await manager.send_to_user(recipient.id, ws_payload)
        elif isinstance(recipient, Guard):
            await manager.send_to_guard(recipient.id, ws_payload)

        # 2. Send via FCM
        await self._send_fcm_notification(
            tokens=[recipient.fcm_token],
            title=title,
            body=body,
            data=data
        )
        logger.info(f"Notification: Sent to {recipient.__class__.__name__} {recipient.id}: {title}")


notification_service = NotificationService()
