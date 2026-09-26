import pytest
from pydantic import ValidationError

from app.schemas.conversation import MessageCreate


@pytest.mark.parametrize("content", ["", "   ", "\n\t"])
def test_message_contract_rejects_blank_content(content):
    with pytest.raises(ValidationError):
        MessageCreate(content=content)
