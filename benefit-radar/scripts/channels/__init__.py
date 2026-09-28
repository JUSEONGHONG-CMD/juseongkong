"""알림 채널 어댑터.

각 채널 모듈은 `send(message: dict, dry_run: bool) -> None` 을 구현한다.
message 형식: {"to": [...], "subject": str, "text": str, "html": str}
새 채널(앱 푸시, 카카오 알림톡 등)은 모듈을 추가하고 CHANNELS 에 등록한다.
"""
from . import email_smtp

CHANNELS = {
    "email": email_smtp,
}
