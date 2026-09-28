"""Shared arithmetic kernel; callers validate values and convert units first."""


def coupled_inhibition_denominator(substrate, product, km, substrate_ki, product_ki):
    """Published combined inhibition denominator, with explicit optional omission.

    Source: https://doi.org/10.3390/catal12010080, supplementary Model 3.
    ``None`` omits substrate inhibition as a caller-declared hypothesis.
    This private numeric kernel supports scalars and arrays in consistent units.
    """
    inhibition = 0.0 if substrate_ki is None else substrate / substrate_ki
    return km * (1.0 + product / product_ki) ** 2 + substrate * (1.0 + inhibition)
