"""Non-biological 1:1 benchmark for the shared exploratory integration contract."""
import numpy as np
import pytest
from fungal_model.core.units import Q_
from fungal_model.research.inhibited_progress import simulate_inhibited_progress


def arguments():
    return dict(times=Q_(np.linspace(0, 10, 11), 'second'), initial_substrate=Q_(10, 'millimolar'),
        initial_product=Q_(1, 'millimolar'), vmax=Q_(0.2, 'millimolar/second'), km=Q_(2, 'millimolar'),
        product_ki=Q_(20, 'millimolar'), substrate_ki=None, decay_rate=Q_(0.01, '1/second'),
        product_stoichiometry=1., source='Artificial 1:1 conservation test', hypothesis_source='Test only')


def test_shared_progress_conserves_one_to_one_and_respects_equivalent_units():
    kwargs = arguments()
    result = simulate_inhibited_progress(**kwargs)
    np.testing.assert_allclose((result.substrate + result.product).magnitude, 11, atol=1e-9)
    kwargs.update(times=kwargs['times'].to('minute'), vmax=kwargs['vmax'].to('molar/minute'),
                  km=kwargs['km'].to('molar'), decay_rate=kwargs['decay_rate'].to('1/minute'))
    converted = simulate_inhibited_progress(**kwargs)
    np.testing.assert_allclose(result.substrate.magnitude, converted.substrate.magnitude, atol=1e-8)
    assert result.maturity == 'exploratory_software_tested'


@pytest.mark.parametrize('change', [dict(source=''), dict(hypothesis_source=''),
    dict(times=Q_([1, 0], 'second')), dict(decay_rate=Q_(-1, '1/second')),
    dict(product_stoichiometry=0), dict(substrate_ki=Q_(0, 'millimolar'))])
def test_shared_progress_rejects_unsupported_inputs(change):
    with pytest.raises(ValueError):
        simulate_inhibited_progress(**(arguments() | change))
