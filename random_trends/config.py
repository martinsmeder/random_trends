from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode


@dataclass(frozen=True)
class BooliMarketConfig:
    name: str
    source: str
    area_ids: tuple[str, ...]
    object_type: str
    max_rooms: int
    sort: str
    ascending: bool

    @property
    def search_url(self) -> str:
        query = urlencode(
            {
                "areaIds": ",".join(self.area_ids),
                "maxRooms": self.max_rooms,
                "objectType": self.object_type,
                "sort": self.sort,
                "ascending": int(self.ascending),
            }
        )
        return f"https://www.booli.se/sok/slutpriser?{query}"


KALIX_CENTRUM_1ROK = BooliMarketConfig(
    name="kalix_centrum_1rok",
    source="booli",
    area_ids=(
        "83953",
        "813757",
        "84052",
        "410631",
        "84014",
        "191823",
        "384715",
        "256034",
        "310171",
        "277786",
        "813788",
        "84028",
    ),
    object_type="Lägenhet",
    max_rooms=1,
    sort="soldDate",
    ascending=True,
)


MARKETS = {
    KALIX_CENTRUM_1ROK.name: KALIX_CENTRUM_1ROK,
}

