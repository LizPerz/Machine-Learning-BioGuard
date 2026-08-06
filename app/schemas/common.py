from pydantic import ConfigDict


def to_camel(value: str) -> str:
    head, *rest = value.split("_")
    return head + "".join(part.capitalize() for part in rest)


ENTRADA_CFG = ConfigDict(
    alias_generator=to_camel,
    populate_by_name=True,
    extra="forbid",
)

SALIDA_CFG = ConfigDict(
    alias_generator=to_camel,
    populate_by_name=True,
)
