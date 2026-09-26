"""Narrow client compatibility policies, separate from OAuth validation."""

# Muse redirects its callback to muse.ai. Some browsers enforce form-action
# across that redirect chain. Keys match the original registered URI exactly;
# do not broaden them to host patterns or client-supplied display names.
_EXTRA_FORM_ACTION_ORIGINS: dict[str, tuple[str, ...]] = {
    "https://agent.meta.ai/api/hatch/oauth/callback": ("https://muse.ai",),
}


def extra_form_action_origins(verified_redirect_uri: str) -> tuple[str, ...]:
    """Return static CSP exceptions for an already-validated callback URI.

    Callers must first validate the URI against the registered client's redirect
    URIs. This policy neither validates nor changes the OAuth redirect target.
    Unknown callbacks use the standard policy without additional origins.
    """
    return _EXTRA_FORM_ACTION_ORIGINS.get(verified_redirect_uri, ())
