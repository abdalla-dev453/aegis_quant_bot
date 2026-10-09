from decimal import Decimal
from uuid import uuid4

import pytest

from app.signals.provider import RuleBasedProvider, SignalGenerationUnavailable


@pytest.mark.asyncio
async def test_unqualified_provider_never_manufactures_an_order():
    provider = RuleBasedProvider()

    with pytest.raises(SignalGenerationUnavailable, match="no qualified market-data strategy"):
        await provider.generate_signal(
            device_id=uuid4(),
            user_id=uuid4(),
            symbol="EURUSD",
            current_price=Decimal("1.08500"),
            point_size=Decimal("0.00001"),
        )
