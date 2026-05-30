from __future__ import annotations

# Compatibility facade for the v1.2 repository split. New code should import
# from core.repositories.<domain>; old callers can keep using core.store.
from core.repositories.annotations import *
from core.repositories.datasets import *
from core.repositories.focus_regions import *
from core.repositories.labels import *
from core.repositories.media import *
from core.repositories.packages import *
from core.repositories.projects import *
from core.repositories.training import *
