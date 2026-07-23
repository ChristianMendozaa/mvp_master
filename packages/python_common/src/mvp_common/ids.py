from typing import NewType
from uuid import UUID, uuid4

EntityId = NewType("EntityId", UUID)


def new_id() -> EntityId:
    return EntityId(uuid4())
