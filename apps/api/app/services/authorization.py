"""Central ownership checks for player and multi-athlete report resources."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.models.tables import Player, PlayerCoach, ReportUpload


def can_access_player(session: Session, actor_id: UUID, player: Player) -> bool:
    if player.owner_user_id == actor_id and player.archived_at is None:
        return True
    if player.archived_at is not None:
        return False
    return (
        session.scalar(
            select(PlayerCoach.player_id).where(
                PlayerCoach.player_id == player.id,
                PlayerCoach.coach_user_id == actor_id,
                PlayerCoach.revoked_at.is_(None),
            )
        )
        is not None
    )


def can_manage_player(session: Session, actor_id: UUID, player: Player) -> bool:
    # Phase 2 only promotes a row to the uploader's own player profile. Coach
    # write access needs separate consent and linked-source read policies.
    return player.owner_user_id == actor_id and player.archived_at is None


def require_player(session: Session, actor_id: UUID, player_id: UUID, *, manage: bool = False) -> Player:
    player = session.get(Player, player_id)
    if player is None or not (
        can_manage_player(session, actor_id, player) if manage else can_access_player(session, actor_id, player)
    ):
        raise AppError("player_not_found", "Player not found", 404)
    return player


def can_access_upload(actor_id: UUID, upload: ReportUpload) -> bool:
    return upload.uploaded_by_user_id == actor_id and upload.status != "deleted"


def require_upload(session: Session, actor_id: UUID, upload_id: UUID) -> ReportUpload:
    upload = session.get(ReportUpload, upload_id)
    if upload is None or not can_access_upload(actor_id, upload):
        raise AppError("upload_not_found", "Upload not found", 404)
    return upload
