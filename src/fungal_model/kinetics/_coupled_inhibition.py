"""Shared arithmetic kernel; callers validate values and convert units first."""


def coupled_inhibition_denominator(substrate, product, km, substrate_ki, product_ki):
    """Published combined inhibition denominator, with explicit optional omission.

    Source: https://doi.org/10.3390/catal12010080, supplementary Model 3.
    ``None`` omits substrate inhibition as a caller-declared hypothesis.
    This private numeric kernel supports scalars and arrays in consistent units.
    """
    inhibition = 0.0 if substrate_ki is None else substrate / substrate_ki
    return km * (1.0 + product / product_ki) ** 2 + substrate * (1.0 + inhibition)


def coupled_inhibition_denominator_gradient(substrate, product, km, substrate_ki, product_ki):
    """Partial derivatives ``(dD/dS, dD/dP)`` of :func:`coupled_inhibition_denominator`.

    ``D = K_m (1 + P / K_p)^2 + S (1 + S / K_i)`` gives ``dD/dS = 1 + 2 S / K_i``
    (``1`` when substrate inhibition is omitted) and
    ``dD/dP = 2 K_m (1 + P / K_p) / K_p``. Same unit contract as the denominator.
    """
    substrate_term = 1.0 if substrate_ki is None else 1.0 + 2.0 * substrate / substrate_ki
    product_term = 2.0 * km * (1.0 + product / product_ki) / product_ki
    return substrate_term, product_term
