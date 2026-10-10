"""Read the existing quota session; billing and node access stay owned by Grace Access."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import GraceAccessSessionModel, Subscription
from app.external.remnawave_api import RemnaWaveAPIError
from app.services.grace_access_codec import _model_to_session
from app.services.grace_access_runtime import (
    RemnawaveGracePanelGateway,
    _build_policy,
    _subscription_to_billing,
    grace_access_runtime,
)
from app.services.grace_access_service import (
    GraceAccessMode,
    GraceReason,
    GraceSessionState,
    billing_is_eligible,
    build_incident_key,
    panel_matches_overlay,
)


async def get_free_access(db: AsyncSession, subscription: Subscription) -> dict:
    inactive = {'active': False, 'eligible': False, 'quota_bytes': 0, 'remaining_bytes': 0, 'subscription_url': None}
    if subscription.actual_status != 'expired':
        return inactive
    await db.refresh(subscription, ['user', 'tariff'])
    billing = _subscription_to_billing(subscription)
    if settings.GRACE_ACCESS_EXPIRED_UNTIL_QUOTA and grace_access_runtime.mode is GraceAccessMode.ACTIVE:
        try:
            inactive['eligible'] = billing_is_eligible(billing, GraceReason.EXPIRED, _build_policy())
        except ValueError:
            pass
    row = (
        await db.execute(
            select(GraceAccessSessionModel).where(
                GraceAccessSessionModel.subscription_id == subscription.id,
                GraceAccessSessionModel.state.in_(
                    (GraceSessionState.PENDING.value, GraceSessionState.ACTIVE.value, GraceSessionState.RESTORING.value)
                ),
                GraceAccessSessionModel.grace_until.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        previous = (
            await db.execute(
                select(GraceAccessSessionModel.completion_reason).where(
                    GraceAccessSessionModel.subscription_id == subscription.id,
                    GraceAccessSessionModel.incident_key == build_incident_key(billing, GraceReason.EXPIRED),
                    GraceAccessSessionModel.state == GraceSessionState.COMPLETED.value,
                    GraceAccessSessionModel.grace_until.is_(None),
                )
            )
        ).scalar_one_or_none()
        if previous is not None:
            return {**inactive, 'eligible': False, 'reason': previous}
        return inactive
    if row.state != GraceSessionState.ACTIVE.value:
        return {**inactive, 'eligible': False, 'reason': row.state}
    session = _model_to_session(row)
    quota = session.overlay.traffic_limit_bytes - session.panel_before.used_traffic_bytes
    try:
        snapshot = await RemnawaveGracePanelGateway(db=db, subscription_id=subscription.id).read_snapshot(
            session.remnawave_id
        )
    except RemnaWaveAPIError:
        return {**inactive, 'eligible': False, 'quota_bytes': quota, 'reason': 'unavailable'}
    if (
        snapshot is not None
        and snapshot.status.lower() != 'disabled'
        and snapshot.used_traffic_bytes >= session.overlay.traffic_limit_bytes
    ):
        return {**inactive, 'eligible': False, 'quota_bytes': quota, 'reason': 'quota_exhausted'}
    if (
        snapshot is None
        or snapshot.status.lower() != 'active'
        or not snapshot.host_available
        or not panel_matches_overlay(snapshot, session.overlay, now=datetime.now(UTC))
        or snapshot.used_traffic_bytes < session.panel_before.used_traffic_bytes
    ):
        return {**inactive, 'eligible': False, 'quota_bytes': quota, 'reason': 'unavailable'}
    remaining = max(0, session.overlay.traffic_limit_bytes - snapshot.used_traffic_bytes)
    return {
        'active': remaining > 0,
        'eligible': False,
        'quota_bytes': quota,
        'remaining_bytes': min(quota, remaining),
        'subscription_url': subscription.subscription_url if remaining > 0 else None,
        'reason': None if remaining > 0 else 'quota_exhausted',
    }
