"""Preserve the resolved configuration used by fake-hardware mode."""


def derive_fake_config(text: str) -> str:
    """Return the exact resolved config; Compose selects simulation at runtime.

    Keeping every service, measurement, output and driver declaration intact
    guarantees that fake and real modes generate the same Home Assistant model.
    """

    return text
