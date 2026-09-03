import uuid
from datetime import UTC, datetime

import pytest

from jinc_social_engine.domain.entities.version import (
    ContentVersion,
    ContentVersionStatus,
)
from jinc_social_engine.domain.exceptions import StateTransitionRejected


def test_content_version_valid_transition():
    version = ContentVersion(
        id=uuid.uuid4(),
        brief_id=uuid.uuid4(),
        platform="twitter",
        content="Hello world",
        status=ContentVersionStatus.GENERATED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        version=1,
    )

    version.transition_status(ContentVersionStatus.VALIDATED)
    assert version.status == ContentVersionStatus.VALIDATED
    assert version.version == 2


def test_content_version_invalid_transition():
    version = ContentVersion(
        id=uuid.uuid4(),
        brief_id=uuid.uuid4(),
        platform="twitter",
        content="Hello world",
        status=ContentVersionStatus.GENERATED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        version=1,
    )

    with pytest.raises(StateTransitionRejected):
        version.transition_status(ContentVersionStatus.APPROVED)
