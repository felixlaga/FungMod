THIS IS OLD INFORMATION. DO NOT USE, DO NOT READ.




## Mission

FungMod must become a modular, physically constrained simulator for fungal degradation processes.

Long-term target:

> Given any fungus, substrate, environment, geometry, and sourced parameters, FungMod can assemble the appropriate physical processes, run the model, validate the result, generate interpretable outputs, and honestly fail when mechanisms or parameters are missing.

This does **not** mean FungMod should magically simulate every fungus and every substrate without data.

It means:

- mechanisms are modular;
- parameters are sourced;
- missing mechanisms are explicit;
- unknown parameters remain unknown;
- assumptions are recorded;
- validators check physical consistency;
- examples and notebooks demonstrate real usage;
- PET, cellulose, lignin, chitin, starch, etc. are plugins/examples, not hard-coded identities of the framework.

PET may be the first serious integration case, but PET must not become the architecture.

---

## Non-Negotiable Scientific Rules

Codex must follow these rules throughout the refactor.

1. **Never fake generality.**
   - A generic class is only generic if it works for more than one substrate/fungus/process in tests.
   - Do not rename `PETSurfaceHydrolysisRateLaw` to `SurfaceHydrolysisRateLaw` unless the implementation no longer depends on PET-specific internals.

2. **Never hard-code PET into core machinery.**
   - PET-specific data belongs in `substrates/pet.py` or a PET plugin/config.
   - Generic machinery belongs in process, solver, validation, geometry, environment, or output modules.

3. **Never invent missing physical parameters.**
   - Missing values must remain explicit unknowns.
   - Scientific simulations must fail if required sourced parameters are unavailable.
   - Test-only escape hatches must remain clearly named and isolated.

4. **Never hide assumptions.**
   - Every rate law, process, modifier, geometry, and validator must expose its assumptions and limitations.

5. **Never confuse metadata with a model.**
   - A `Substrate` object may say what bonds/products/enzyme classes are relevant.
   - It must not imply that a valid kinetic model exists unless a process module actually implements one.

6. **Never produce only raw arrays.**
   - Simulations must produce structured results: state trajectories, diagnostics, validation reports, assumptions, parameter tables, plots, and serialized records.

7. **Never let examples pass without tests.**
   - Every new public model, process, output object, and notebook utility must have unit tests or integration tests.

8. **Never claim biological realism before validation.**
   - A mechanistic implementation can exist before calibration.
   - But outputs must clearly label whether they are toy, benchmark, calibrated, literature-reproducing, or experimental.

---

## Desired User-Level API

The eventual public API should feel like a scientific modeling package, not a collection of scripts.

Example target:

```python
from fungal_model import (
    Fungus,
    Substrate,
    Environment,
    Geometry,
    ProcessLibrary,
    ModelBuilder,
    SolverSettings,
)

fungus = Fungus.from_yaml("data/fungi/pleurotus_ostreatus.yml")
substrate = Substrate.from_yaml("data/substrates/pet_film.yml")
environment = Environment.from_yaml("data/environments/lab_30C_pH7.yml")
geometry = Geometry.from_yaml("data/geometries/pet_film_1d.yml")

library = ProcessLibrary.default()

model = ModelBuilder(
    fungus=fungus,
    substrates=[substrate],
    environment=environment,
    geometry=geometry,
    process_library=library,
).assemble()

result = model.run(
    duration="30 day",
    solver_settings=SolverSettings.default(),
)

result.validate()
result.plot_all()
result.save("outputs/run_001/")
```

The same architecture should eventually allow:

```python
fungus = Fungus.from_yaml("data/fungi/aspergillus_tubingensis.yml")
substrate = Substrate.from_yaml("data/substrates/cellulose_powder.yml")
environment = Environment.from_yaml("data/environments/compost_high_humidity.yml")
geometry = Geometry.well_mixed(volume="100 mL")

model = ModelBuilder(...).assemble()
result = model.run(duration="14 day")
```

If required mechanisms or parameters are missing, the correct behavior is not to guess. The correct behavior is a clear failure report:

```text
Model assembly failed.

Missing process:
    No validated process found for:
        substrate: lignin
        bond type: aryl ether
        enzyme class: laccase
        environment: aerobic aqueous

Missing parameters:
    k_cat_laccase_aryl_ether
    redox_mediator_concentration
    oxygen_half_saturation_constant

Suggested next steps:
    - provide a process implementation;
    - provide sourced parameters;
    - mark the run as a toy model if deliberately testing structure only.
```

---

## Architectural Principle

FungMod should model **processes**, not named substrates.

Wrong long-term design:

```text
PETSurfaceHydrolysisRateLaw
CelluloseHydrolysisRateLaw
ChitinHydrolysisRateLaw
LigninOxidationRateLaw
```

This becomes hard-coded and unmaintainable.

Better design:

```text
AdsorptionModel
SurfaceCatalysisModel
BondCleavageProcess
OxidativeCleavageProcess
DiffusionProcess
EnzymeSecretionProcess
EnzymeDecayProcess
ProductUptakeProcess
BiomassGrowthProcess
MaintenanceProcess
OxygenConsumptionProcess
EnvironmentalModifier
```

Then PET, cellulose, lignin, chitin, starch, etc. supply different:

- bond types;
- accessible bond pools;
- enzyme classes;
- morphology/accessibility models;
- product maps;
- parameter sets;
- thermodynamic metadata;
- validity ranges.

---

## Target Package Structure

Refactor gradually toward this structure.

```text
fungal_model/
    core/
        units.py
        parameters.py
        assumptions.py
        provenance.py
        simulation_record.py
        errors.py

    state/
        variables.py
        state_vector.py
        species.py
        conserved_quantities.py

    entities/
        fungus.py
        substrate.py
        enzyme.py
        product.py
        environment.py
        geometry.py

    processes/
        base.py
        registry.py
        assembly.py

        enzyme_secretion.py
        enzyme_decay.py
        enzyme_inactivation.py

        adsorption.py
        desorption.py
        surface_catalysis.py
        homogeneous_catalysis.py
        bond_cleavage.py
        product_release.py

        diffusion.py
        advection.py

        uptake.py
        biomass_growth.py
        maintenance.py
        oxygen_consumption.py
        toxicity.py
        inhibition.py

    modifiers/
        temperature.py
        ph.py
        water_activity.py
        oxygen.py
        product_inhibition.py

    substrates/
        base.py
        pet.py
        cellulose.py
        lignin.py
        chitin.py
        starch.py
        mixed.py

    fungi/
        base.py
        enzyme_profile.py
        secretion_program.py
        uptake_profile.py
        species/
            pleurotus_ostreatus.yml
            aspergillus_tubingensis.yml

    geometry/
        base.py
        well_mixed.py
        film_1d.py
        particle.py
        porous_medium.py

    solvers/
        ode.py
        reaction_diffusion_1d.py
        solver_settings.py

    validation/
        base.py
        non_negativity.py
        mass_balance.py
        carbon_balance.py
        oxygen_balance.py
        thermodynamic_feasibility.py
        yield_bounds.py
        limiting_cases.py
        model_assembly.py

    calibration/
        residuals.py
        least_squares.py
        parameter_estimation.py
        train_validation_split.py

    uncertainty/
        monte_carlo.py
        local_sensitivity.py
        global_sensitivity.py

    results/
        result.py
        diagnostics.py
        plots.py
        reports.py
        export.py

    io/
        yaml_loader.py
        json_export.py
        schema.py

    examples/
        process_examples/
        system_examples/

notebooks/
    00_quickstart.ipynb
    01_process_library_demo.ipynb
    02_surface_hydrolysis_demo.ipynb
    03_fungus_on_pet_demo.ipynb
    04_reaction_diffusion_demo.ipynb
    05_calibration_and_uncertainty_demo.ipynb

tests/
    ...
```

Important: the `/notebooks` folder is required. It should work like in Atmodeller-style scientific codebases: core machinery lives in Python modules, while notebooks import those modules and demonstrate real workflows, plots, diagnostics, and model exploration. Notebooks must not contain the core implementation.

---

## Required `/notebooks` Folder

Create a top-level folder:

```text
notebooks/
```

Purpose:

- demonstrate user-facing scientific workflows;
- call public functions from `src/fungal_model`;
- show how to assemble models;
- generate plots and diagnostics;
- test that the package feels usable interactively;
- avoid hiding core logic inside notebooks.

Initial notebooks:

### `notebooks/00_quickstart.ipynb`

Must show:

- import FungMod;
- create/load a fungus;
- create/load a substrate;
- create/load environment and geometry;
- assemble a small model;
- run;
- validate;
- plot;
- save outputs.

### `notebooks/01_process_library_demo.ipynb`

Must show:

- available process types;
- required inputs for each process;
- how process matching works;
- what happens when a process is missing.

### `notebooks/02_surface_hydrolysis_demo.ipynb`

Must show:

- generic surface hydrolysis;
- not PET-specific;
- at least two substrate definitions using the same generic process in toy mode.

### `notebooks/03_fungus_on_pet_demo.ipynb`

Must show:

- PET as a plugin/example;
- fungal enzyme secretion;
- enzyme decay;
- adsorption;
- surface cleavage;
- product release;
- optional uptake/growth;
- validation reports.

### `notebooks/04_reaction_diffusion_demo.ipynb`

Must show:

- 1D geometry;
- diffusion;
- boundary conditions;
- spatial concentration plots;
- comparison to well-mixed limit.

### `notebooks/05_calibration_and_uncertainty_demo.ipynb`

Must show:

- synthetic or real dataset loading;
- fitting parameters;
- train/validation residuals;
- uncertainty propagation;
- sensitivity analysis.

Notebook rules:

- notebooks must import from the installed package;
- no duplicated model code inside notebooks;
- no hidden constants without provenance;
- generated plots must be reproducible;
- each notebook must have a corresponding lightweight smoke test or execution test where practical.

---

## Core Refactor Goal

Current concern:

Some concrete functions are useful but too specific. For example, PET-specific surface hydrolysis should be refactored so the core process is generic.

Current style:

```python
PETSurfaceHydrolysisRateLaw(...)
```

Target style:

```python
SurfaceHydrolysisProcess(
    substrate_state="substrate_mass",
    enzyme_state="free_enzyme",
    accessible_site_model=AccessibleSurfaceAreaModel(...),
    adsorption_model=LangmuirAdsorptionModel(...),
    catalytic_model=SurfaceCatalysisModel(...),
    product_map=ProductReleaseMap(...),
    modifiers=[TemperatureModifier(...), PHModifier(...)],
)
```

PET-specific code should become:

```python
PETSubstrate(...)
PETProductMap(...)
PETAccessibilityModel(...)
PETParameterSet(...)
```

The generic process must not import `PETSubstrate`.

Test requirement:

- There must be a test that imports `SurfaceHydrolysisProcess` and uses it with a non-PET dummy substrate.
- There must be a test that confirms the generic process module contains no PET-specific imports.
- There must be a test that PET uses the generic process through configuration/composition.

---

## Process-Centered Architecture

### `Process`

Create a generic process interface.

Suggested design:

```python
class Process:
    name: str
    required_state_variables: tuple[StateVariableSpec, ...]
    required_parameters: tuple[ParameterSpec, ...]
    assumptions: tuple[Assumption, ...]
    validity: ValidityDomain

    def rate(self, state, time, parameters, environment, geometry):
        ...

    def contributions(self, rate):
        ...
```

A process must specify:

- what state variables it reads;
- what state variables it changes;
- what parameters it requires;
- units of all rates;
- assumptions;
- validity range;
- failure modes.

### `ProcessRegistry`

Create a registry that can match processes to a proposed model.

Responsibilities:

- store available process classes/instances;
- check whether a process applies to a fungus/substrate/environment/geometry;
- return candidate processes;
- fail clearly if no process exists;
- report missing parameters separately from missing mechanisms.

Example:

```python
registry.find_processes(
    fungus=fungus,
    substrate=substrate,
    environment=environment,
    geometry=geometry,
)
```

### `ModelBuilder`

Create a builder that assembles a model from entities.

Responsibilities:

- collect fungus, substrate(s), environment, geometry;
- query process registry;
- build state variables;
- build reactions/processes;
- validate required parameters;
- validate units;
- produce an `AssembledModel`;
- fail honestly if incomplete.

---

## Entity Modules

### Fungus

A fungus should not be only a name. It should encode available biological capabilities.

Required fields:

- name;
- taxonomy;
- biomass state definition;
- enzyme profile;
- secretion program;
- uptake capabilities;
- growth/yield model;
- maintenance model;
- oxygen dependence;
- pH/temperature tolerance metadata;
- assumptions;
- sources.

Do not assume that a fungus can assimilate a degradation product merely because it can degrade the substrate.

### Enzyme

Create explicit enzyme entities.

Required fields:

- name;
- enzyme class;
- target bond types;
- target substrate classes;
- catalytic parameters;
- adsorption parameters if relevant;
- pH profile;
- temperature profile;
- deactivation/inactivation parameters;
- source/provenance;
- validity range.

This avoids hiding enzyme behavior inside substrate-specific rate laws.

### Substrate

Substrates should describe materials, not automatically imply kinetics.

Required fields:

- name;
- chemical class;
- physical state;
- bond types;
- accessible bonds;
- morphology;
- surface/volume/particle/film geometry metadata;
- degradation products;
- product stoichiometry if known;
- thermodynamic data;
- required or compatible enzyme classes;
- parameter set;
- assumptions;
- references;
- completeness level.

### Environment

Create a real environment object.

Required fields:

- temperature;
- pH;
- oxygen concentration or availability;
- water activity;
- nutrients;
- ionic strength where relevant;
- pressure if relevant;
- boundary conditions;
- validity labels.

Environment should be read by modifiers and processes, not passed around as loose parameters.

### Geometry

Create explicit geometry objects.

Initial geometries:

- well-mixed;
- 1D film;
- particle/sphere approximation;
- slab;
- porous medium placeholder.

Geometry must provide:

- volume;
- surface area;
- boundary conditions;
- spatial grid if applicable;
- area/volume coupling;
- units;
- assumptions.

---

## Core Process Library

Implement processes in stages. Each process must have tests, assumptions, required parameters, and failure modes.

### Stage P1: Generic homogeneous reaction process

Purpose:

- support dissolved substrate/product toy models;
- keep Michaelis-Menten generic;
- avoid tying homogeneous kinetics to PET.

Functions/classes:

- `HomogeneousMichaelisMentenProcess`
- `MassActionProcess`
- `FirstOrderDecayProcess`

Tests:

- low-substrate limit;
- high-substrate limit;
- zero enzyme;
- zero substrate;
- unit consistency;
- mass conservation where applicable.

### Stage P2: Generic adsorption process

Purpose:

- model enzyme binding to surfaces.

Functions/classes:

- `LangmuirAdsorptionModel`
- `DynamicAdsorptionDesorptionProcess`
- `EquilibriumSurfaceCoverageModel`

Tests:

- zero enzyme gives zero coverage;
- high enzyme saturates coverage;
- negative inputs fail;
- units of adsorption coefficient checked;
- coverage dimensionless and bounded between 0 and 1.

### Stage P3: Generic surface catalysis / bond cleavage

Purpose:

- cleave accessible bonds on a solid substrate surface.

Functions/classes:

- `AccessibleSitePool`
- `AccessibleSurfaceAreaModel`
- `SurfaceCatalysisProcess`
- `BondCleavageProcess`
- `ProductReleaseMap`

Tests:

- zero accessible surface gives zero rate;
- zero enzyme gives zero rate;
- zero substrate gives zero rate;
- increasing accessible surface increases rate;
- products conserve mass/carbon if stoichiometry is supplied;
- works with PET and a dummy non-PET substrate.

### Stage P4: Environmental modifiers

Purpose:

- modify rates by environmental conditions.

Functions/classes:

- `TemperatureModifier`
- `PHModifier`
- `WaterActivityModifier`
- `OxygenModifier`
- `ProductInhibitionModifier`

Tests:

- modifier equals 1 at reference/optimum where expected;
- out-of-range warnings;
- no silent extrapolation;
- modifiers are dimensionless;
- combined modifiers remain explicit in assumptions.

### Stage P5: Enzyme secretion, decay, and inactivation

Purpose:

- connect living fungal biomass to extracellular enzyme availability.

Functions/classes:

- `EnzymeSecretionProcess`
- `EnzymeDecayProcess`
- `ThermalEnzymeInactivationProcess`
- `EnzymeProductionCostProcess`

Tests:

- no active biomass gives no secretion;
- secretion costs biomass/energy if enabled;
- enzyme decays/inactivates over time;
- units consistent;
- assumptions recorded.

### Stage P6: Product uptake and biomass growth

Purpose:

- model fungal growth only from assimilable products.

Functions/classes:

- `ProductUptakeProcess`
- `BiomassGrowthProcess`
- `MaintenanceProcess`
- `YieldLimitValidator`

Tests:

- no product gives no growth;
- non-assimilable product gives no growth;
- growth cannot exceed yield bounds;
- maintenance reduces biomass when no substrate/product is available;
- carbon balance checked.

### Stage P7: Oxygen and redox constraints

Purpose:

- prevent aerobic growth/degradation from ignoring oxygen.

Functions/classes:

- `OxygenConsumptionProcess`
- `OxygenLimitationModifier`
- `RedoxBalanceValidator`

Tests:

- oxygen-limited rate decreases when oxygen is low;
- oxygen cannot become silently negative;
- aerobic process fails if oxygen is missing and required;
- oxygen demand report generated.

### Stage P8: Transport and spatial models

Purpose:

- support diffusion and geometry.

Functions/classes:

- `DiffusionProcess`
- `ReactionDiffusionModel1D`
- `BoundaryCondition`
- `WellMixedLimitValidator`

Tests:

- no-flux conservation;
- diffusion smooths gradients;
- high diffusion approaches well-mixed behavior;
- fixed boundary behaves correctly;
- spatial units checked.

---

## Model Assembly Behavior

Model assembly must be explicit.

### Successful assembly

A successful model assembly should produce:

```text
AssembledModel
    state variables
    processes
    parameters
    environment
    geometry
    assumptions
    validators
    solver settings
```

### Failed assembly

Failure must be structured, not a vague exception.

Create:

```python
ModelAssemblyError
MissingProcessError
MissingParameterError
IncompatibleUnitsError
InvalidMechanismError
```

Also create a human-readable report:

```text
Assembly report:
    matched processes:
        - enzyme secretion
        - enzyme decay
        - surface adsorption
        - surface catalysis
    missing processes:
        - product uptake for TPA
    missing parameters:
        - k_cat_surface
        - K_ads
    warnings:
        - pH outside sourced validity range
```

Tests:

- assembly succeeds when all processes and parameters are supplied;
- assembly fails when process missing;
- assembly fails when parameter missing;
- assembly fails when units incompatible;
- failure report names exact missing process/parameter;
- no fallback constants are inserted.

---

## Result and Output System

The output system must be a first-class part of FungMod.

Create `SimulationResult`.

Required contents:

- raw time array;
- state trajectories with units;
- derived quantities;
- parameter table;
- process rate trajectories;
- assumptions;
- validation report;
- warnings;
- solver metadata;
- model assembly report;
- uncertainty/sensitivity results when available.

Suggested API:

```python
result.state("PET_mass")
result.rate("surface_hydrolysis")
result.plot_state("PET_mass")
result.plot_rates()
result.plot_mass_balance()
result.plot_carbon_balance()
result.plot_spatial_profile(species="enzyme")
result.save("outputs/run_001/")
```

---

## Required Plots and Graph Outputs

Every serious example should be able to generate standard plots.

### Core plots

- state trajectories vs time;
- process rates vs time;
- substrate mass remaining;
- product release;
- enzyme concentration;
- active biomass;
- environmental modifiers vs time;
- mass balance residual;
- carbon balance residual;
- oxygen availability/consumption;
- solver diagnostics.

### Spatial plots

For spatial models:

- concentration profile vs position at selected times;
- heatmap of concentration over space and time;
- surface reaction rate profile;
- comparison to well-mixed limit.

### Calibration plots

- observed vs predicted;
- residuals vs time;
- train/validation split residuals;
- fitted parameter table;
- confidence/uncertainty intervals;
- parameter correlation/covariance where available.

### Uncertainty/sensitivity plots

- uncertainty bands on trajectories;
- Monte Carlo ensemble;
- local sensitivity bar chart;
- ranked parameter influence;
- tornado plot.

Output rules:

- plots must be generated from `SimulationResult`, not from duplicated notebook code;
- every plot must label units;
- every plot must record assumptions and input file paths in metadata where possible;
- plots must save to `outputs/<run_name>/figures/`.

---

## Output Folder Structure

A model run should save:

```text
outputs/run_name/
    record.json
    model_assembly_report.json
    assumptions.json
    parameters.csv
    validation_report.json
    solver_report.json
    state_trajectories.csv
    process_rates.csv
    derived_quantities.csv

    figures/
        state_trajectories.png
        process_rates.png
        substrate_mass.png
        product_release.png
        mass_balance.png
        carbon_balance.png
        oxygen_balance.png
        spatial_profiles.png
        uncertainty_bands.png

    logs/
        warnings.txt
        provenance_report.md
```

Tests:

- result save creates expected files;
- JSON files are valid;
- CSV files include units or unit metadata;
- plots are created by result methods;
- failed validation still saves report.

---

## Data and Configuration Files

Create structured data folders:

```text
data/
    fungi/
    substrates/
    enzymes/
    environments/
    geometries/
    parameters/
    experiments/
```

Use YAML or JSON for human-readable configuration.

Example:

```text
data/substrates/pet_film.yml
data/substrates/cellulose_powder.yml
data/fungi/pleurotus_ostreatus.yml
data/enzymes/petase_like.yml
data/environments/lab_30C_pH7.yml
data/geometries/pet_film_1d.yml
```

Every data file must include provenance fields.

Required provenance fields:

- source;
- measurement method if known;
- confidence level;
- notes;
- validity range;
- units.

Tests:

- schema validation passes for valid configs;
- schema validation fails for missing provenance;
- unit parsing works;
- unknown values remain unknown.

---

## Refactoring PET Correctly

PET should become an integration case built from generic pieces.

### PET-specific modules may contain:

- PET identity;
- polymer class;
- ester bond metadata;
- product map: MHET/BHET/TPA/EG/oligomers;
- crystallinity metadata;
- amorphous fraction;
- accessible surface model;
- default parameter symbols;
- literature references.

### PET-specific modules must not contain:

- generic Langmuir adsorption implementation;
- generic surface catalysis implementation;
- generic pH/temperature modifier logic;
- generic ODE solver logic;
- generic plotting code;
- generic result serialization.

### Required PET integration tests

- PET can be assembled using generic surface hydrolysis;
- PET fails if accessible surface is missing;
- PET fails if enzyme lacks compatible target bond;
- PET product map conserves mass/carbon where stoichiometry is supplied;
- PET example produces expected output files and plots;
- PET module can be removed without breaking generic process tests.

---

## Adding New Substrates Correctly

For each new substrate, do not begin with kinetics. Begin with metadata.

Minimum substrate plugin requirements:

- name;
- chemical class;
- physical state;
- bond types;
- accessible bonds;
- likely enzyme classes;
- degradation products;
- unknown parameter set;
- assumptions;
- limitations;
- references;
- completeness level.

Only after this metadata exists may Codex add process compatibility.

Substrate maturity levels:

```text
placeholder:
    metadata only, no kinetic claims

partial:
    at least one process implemented, but not fully validated

benchmark:
    reproduces at least one known dataset or controlled synthetic benchmark

validated:
    calibrated and validated against independent experimental data
```

Tests:

- placeholder substrate cannot run a scientific kinetic model;
- partial substrate can run only implemented processes;
- missing product map blocks product-release modeling;
- no default degradation model is silently assumed.

---

## Adding New Fungi Correctly

For each new fungus, do not begin with a full organism simulation. Begin with capabilities.

Minimum fungus plugin requirements:

- name;
- taxonomy;
- enzyme capabilities;
- secretion assumptions;
- uptake capabilities;
- growth model if known;
- environmental tolerance metadata;
- oxygen dependence;
- references;
- unknown parameter set.

Fungus maturity levels:

```text
metadata_only:
    known capabilities only

enzyme_profile:
    enzymes and targets known

kinetic_profile:
    secretion/decay/growth parameters supplied

validated_profile:
    reproduces experimental growth/degradation data
```

Tests:

- fungus cannot degrade a substrate unless compatible enzyme/process exists;
- fungus cannot grow from non-assimilable products;
- missing secretion parameters block living-fungus simulations;
- isolated-enzyme simulations can run without full fungus object.

---

## Validation Philosophy

Validators must be modular and composable.

Required validators:

- non-negativity;
- dimensional consistency;
- mass balance;
- carbon balance;
- oxygen balance;
- yield bounds;
- thermodynamic feasibility where data exist;
- limiting cases;
- well-mixed limit for spatial models;
- monotonicity checks where physically expected;
- assembly completeness;
- parameter provenance.

Validation must produce structured results:

```python
ValidationResult(
    name="carbon_balance",
    passed=True,
    residual=...,
    units=...,
    severity="error" | "warning" | "info",
    message="..."
)
```

Rules:

- failed validation must not be hidden;
- warnings must be saved;
- validators must run automatically in examples;
- severe validation failures must be able to stop scientific simulations;
- toy examples may allow relaxed validation only with explicit labels.

---

## Calibration and Uncertainty

Calibration must remain generic.

Required features:

- fit selected parameters to data;
- unit-aware residuals;
- train/validation splits;
- residual reports;
- failed optimizer reports;
- parameter bounds with provenance;
- identifiability warnings;
- covariance diagnostics where valid;
- Monte Carlo uncertainty propagation;
- local sensitivity;
- eventually global sensitivity.

Tests:

- fitting recovers known synthetic parameters;
- bad units fail;
- missing data fail clearly;
- validation-data reuse warning appears;
- unidentifiable parameters produce warnings;
- uncertainty bands widen when input uncertainty widens.

---

## Minimal Staged Implementation Plan

This is not a one-shot project. Codex must work in small stages.

### Milestone 1: Process base classes

Deliverables:

- `Process`
- `ProcessRegistry`
- `ModelBuilder` skeleton
- structured assembly report
- tests for missing process and missing parameter behavior

Do not change existing examples yet except as needed to preserve tests.

Definition of done:

- all old tests pass;
- new process registry tests pass;
- assembly failure report is human-readable and machine-readable.

### Milestone 2: Generic result object

Deliverables:

- `SimulationResult`
- standard save/export methods
- standard plotting methods
- validation report integration

Definition of done:

- existing examples use `SimulationResult`;
- outputs folder has standardized structure;
- tests verify output files and plot creation.

### Milestone 3: Generic homogeneous kinetics

Deliverables:

- generic first-order/mass-action/Michaelis-Menten processes;
- old homogeneous examples migrated;
- tests for limiting cases.

Definition of done:

- no substrate-specific assumptions in homogeneous kinetics;
- toy substrate example works.

### Milestone 4: Generic surface process refactor

Deliverables:

- generic adsorption model;
- generic surface hydrolysis/catalysis process;
- accessible site/surface model;
- PET migrated to use generic process;
- dummy non-PET substrate test.

Definition of done:

- generic surface process imports no PET module;
- PET example still runs;
- non-PET dummy surface example also runs.

### Milestone 5: Environment object and modifiers

Deliverables:

- `Environment`;
- generic temperature/pH/water activity/oxygen modifiers;
- validity-range warnings;
- examples updated.

Definition of done:

- modifiers read from environment;
- parameters remain sourced;
- plots show modifier values over time where relevant.

### Milestone 6: Geometry abstraction

Deliverables:

- `Geometry`;
- well-mixed geometry;
- 1D film geometry;
- boundary condition objects;
- result plotting for spatial profiles.

Definition of done:

- well-mixed and 1D film examples both run through common model interface;
- high-diffusion well-mixed limit test passes.

### Milestone 7: Fungus/enzyme/process compatibility

Deliverables:

- explicit enzyme entities;
- compatibility matching between fungus, enzyme, substrate bond, and process;
- product uptake capabilities;
- clear failure when fungus lacks capability.

Definition of done:

- fungus with no compatible enzyme cannot degrade substrate;
- isolated enzyme system can run without fungus;
- living fungus model requires secretion/growth parameters.

### Milestone 8: Notebooks

Deliverables:

- create `/notebooks`;
- add quickstart and process demos;
- notebooks import package code only;
- no core logic inside notebooks.

Definition of done:

- notebooks execute at least in smoke-test mode or have equivalent tested scripts;
- plots generated from package result methods.

### Milestone 9: Data/config schemas

Deliverables:

- YAML/JSON loaders;
- schema validation;
- example configs for fungus, substrate, environment, geometry, enzyme.

Definition of done:

- missing provenance fails schema validation;
- unknown values are accepted only as explicit unknowns;
- configs can reproduce examples.

### Milestone 10: First full integration workflow

Deliverables:

- one fungus/enzyme/PET/environment/geometry workflow;
- not hard-coded;
- assembled through registry and model builder;
- full output folder;
- validation and plots.

Definition of done:

- changing substrate config changes model assembly;
- missing PET parameters fail honestly;
- process reports explain what was assembled.

---

## Anti-Cheating Test Checklist

Codex must add tests that prevent shallow implementation.

### Generality tests

- Generic surface hydrolysis must work with PET and a dummy non-PET substrate.
- Generic process modules must not import PET-specific modules.
- PET plugin must use generic processes.

### Failure tests

- missing process fails with `MissingProcessError`;
- missing parameter fails with `MissingParameterError`;
- missing provenance fails in scientific mode;
- incompatible units fail;
- incompatible fungus/substrate/enzyme pairing fails;
- non-assimilable product cannot cause biomass growth.

### Physical tests

- no negative concentrations/masses;
- zero enzyme gives zero enzyme-catalyzed degradation;
- zero accessible surface gives zero surface degradation;
- zero substrate gives zero product formation;
- carbon/mass balance passes when stoichiometry is supplied;
- oxygen cannot be consumed if oxygen process is absent or unavailable;
- high diffusion approaches well-mixed limit.

### Output tests

- simulation creates standardized result object;
- save creates expected output files;
- plots are generated from result object;
- validation reports are saved;
- assumptions are serialized;
- units appear in output metadata.

### Notebook tests

- notebooks import from `fungal_model`;
- notebooks do not define core rate laws/classes;
- quickstart notebook can execute or has a smoke-test script;
- notebook outputs are reproducible.

---

## Definition of Done for Any New Feature

A feature is not complete unless all are true:

1. Public API is documented.
2. Assumptions are explicit.
3. Required parameters are declared.
4. Units are checked.
5. Provenance is enforced.
6. Failure modes are tested.
7. At least one limiting case is tested.
8. Outputs are saved in structured form where relevant.
9. Plots are generated through result methods where relevant.
10. Existing tests still pass.
11. `progress.md` is updated.
12. The feature does not make PET, one fungus, or one environment hard-coded into the core.

---

## Final Long-Term Vision

The final FungMod engine should allow this conceptual workflow:

```text
Input:
    fungus
    substrate(s)
    environment
    geometry
    sourced parameters

ModelBuilder:
    finds compatible enzymes
    finds compatible substrate bonds
    finds available processes
    checks environment validity
    checks geometry support
    checks required parameters
    assembles ODE/PDE/reaction-diffusion system

Solver:
    runs model
    records solver settings
    records warnings

Validators:
    check non-negativity
    check mass/carbon/oxygen/yield constraints
    check limiting behavior
    check thermodynamic feasibility where possible

Result:
    state trajectories
    process rates
    diagnostics
    plots
    assumptions
    provenance
    validation report
    uncertainty/sensitivity reports
```

If all data and mechanisms exist, FungMod runs.

If not, FungMod fails honestly and tells the user exactly what is missing.

That is the scientific standard.
