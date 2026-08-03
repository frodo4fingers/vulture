from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from typing import TypeVar


ItemT = TypeVar("ItemT")


def choose_from_shuffle_bag(
    items: Sequence[ItemT],
    *,
    item_id: Callable[[ItemT], str],
    remaining_ids: Sequence[str],
    last_id: str | None,
    random_source: random.Random,
) -> tuple[ItemT, list[str]]:
    """Choose randomly without replacement and avoid cycle-boundary repeats."""
    items_by_id: dict[str, ItemT] = {}
    for item in items:
        identifier = item_id(item)
        if identifier in items_by_id:
            raise ValueError(f"duplicate shuffle item identifier: {identifier}")
        items_by_id[identifier] = item
    if not items_by_id:
        raise ValueError("cannot choose from an empty shuffle bag")

    seen: set[str] = set()
    bag: list[str] = []
    for identifier in remaining_ids:
        if identifier in items_by_id and identifier not in seen:
            bag.append(identifier)
            seen.add(identifier)
    if not bag:
        bag = list(items_by_id)
        random_source.shuffle(bag)

    if (
        last_id is not None
        and bag[-1] == last_id
        and len(items_by_id) > 1
    ):
        alternative_index = next(
            (
                index
                for index, identifier in enumerate(bag[:-1])
                if identifier != last_id
            ),
            None,
        )
        if alternative_index is not None:
            bag[alternative_index], bag[-1] = (
                bag[-1],
                bag[alternative_index],
            )

    selected_id = bag.pop()
    return items_by_id[selected_id], bag
