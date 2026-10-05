<!-- Provenance: produced on 2026-10-05 by an AI-assisted literature search run
from this project's development session. The session's network policy blocked
every publisher and data-repository domain, so every statement carries the
verification tag the report defines. Nothing in this file is registry evidence;
it is a candidate review to be confirmed by a person with normal web access. -->

# Cross-study transfer dataset survey for FungMod (2026-10-05)

Purpose: find a second public dataset to predict, without refitting, after calibrating on
Gelain et al. 2020 (T. harzianum P49P11, glycerol growth + cellulose induction, Mendeley Data
10.17632/shd3wcczsr.2).

## Verification caveat (read first)

Everything below was verified only at abstract / search-snippet level. In this environment the
egress proxy blocks direct reads of: data.mendeley.com, zenodo.org, api.figshare.com,
springernature.figshare.com, datadryad.org, www.ebi.ac.uk (BioModels), api.crossref.org,
api.semanticscholar.org, pubmed/pmc.ncbi.nlm.nih.gov, sciencedirect.com, link.springer.com,
biomedcentral.com, academic.oup.com, onlinelibrary.wiley.com, mdpi.com, frontiersin.org,
biorxiv.org, arxiv.org, repository.tudelft.nl, etd.ohiolink.edu, and docs.nrel.gov (DNS failure).
The GitHub connector is restricted to felixlaga/fungmod, so the PEtab benchmark repository could
not be listed. Items marked UNVERIFIED must be checked by someone with normal web access before
any number from them enters the registry. No DOI or number below was invented; where a DOI was
not surfaced by a search result it is marked "DOI not verified".

Verification levels used: [V-abstract] = citation and abstract-level facts confirmed by at least
one search result; [UNVERIFIED] = stated by the task brief or inferred, not confirmed.

## Baseline (for reference)

Gelain L. et al. 2020, Chemical Engineering Science: X, "Mathematical modelling for the
optimization of cellulase production using glycerol for cell growth and cellulose as the inducer
substrate" (ScienceDirect PII S2590140020300319). Data: Mendeley Data, "Mathematical modelling
for the optimization of cellulase production", v2, 15 Aug 2020, DOI 10.17632/shd3wcczsr.2,
contributor Lucas Gelain [V-abstract]. Licence of the deposit: not verifiable from here (Mendeley
blocked); Mendeley deposits default to CC BY 4.0 but confirm on the record page [UNVERIFIED].

## Candidate-by-candidate findings

### 1. Sáez et al. 2002 (NREL) + companion Schell et al. 2002  -- same genus, different lab
- Citation: Sáez J.C., Schell D.J., Tholudur A., Farmer J., Hamilton J., Colucci J.A.,
  McMillan J.D. (2002) "Carbon Mass Balance Evaluation of Cellulase Production on Soluble and
  Insoluble Substrates", Biotechnol. Prog. 18:1400-1407, DOI 10.1021/bp0200292, PMID 12467477
  [V-abstract]. Companion: Schell D.J., Sáez J.C., Hamilton J., Tholudur A., McMillan J.D. (2002)
  "Use of Measurement Uncertainty Analysis to Assess Accuracy of Carbon Mass Balance Closure for a
  Cellulase Production Process", Appl. Biochem. Biotechnol. 98-100 (NREL PDF at
  docs.nrel.gov/docs/gen/fy02/30224.pdf; also Springer chapter 10.1007/978-1-4612-0119-9_42)
  [V-abstract].
- Organism: Trichoderma reesei; strain NOT verified (NREL historically used L27/RL-P37-type
  strains; do not assume) [UNVERIFIED].
- Substrate/conditions: aerobic batch in 7-L fermentors on pure cellulose (Solka-floc), glucose,
  or lactose; cultivation to 168 h on Solka-floc; T, pH, agitation, inoculum not captured
  [V-abstract for substrates/volume/duration; conditions UNVERIFIED].
- Observables: cell mass, cellulose, soluble protein, adsorbed protein, sugars, CO2 (mass
  spectrometer off-gas) vs time; mass-balance closure 90-100 % to 48 h, 101-135 % from 72-168 h
  [V-abstract]. FPU/CMCase: not confirmed (protein is the product measure) [UNVERIFIED].
- Time points / replicates: at least 48, 72 ... 168 h sampling implied; exact count and n/SD
  UNVERIFIED.
- Raw data: no repository deposit found. Figures only -> digitization-only. The NREL PDF of the
  companion paper may contain tabulated balances [UNVERIFIED].
- Licence: Biotechnol. Prog. (Wiley/AIChE) closed; NREL report is a US-government document
  (typically public domain) [UNVERIFIED].
- Suitability: best observable match found for FungMod's core outputs on an insoluble cellulose
  (substrate loss + biomass + secreted protein, with carbon closure). Same genus, different lab.
  Weakness: digitization only, strain and replicate structure unknown, product measured as
  protein rather than FPU.

### 2. Velkovska, Marten & Ollis 1997  -- same genus, different lab
- Citation: Velkovska S., Marten M.R., Ollis D.F. (1997) "Kinetic model for batch cellulase
  production by Trichoderma reesei RUT C30", J. Biotechnol. 54:83-94,
  DOI 10.1016/S0168-1656(97)01669-6, PMID 9195752 [V-abstract].
- Organism: T. reesei RUT-C30 [V-abstract].
- Substrate/conditions: batch on particulate cellulose (search snippets indicate Solka Floc in
  Mandels medium; grade and concentration UNVERIFIED); T, pH, reactor UNVERIFIED.
- Observables: laboratory batch data of biomass (particulate), substrate (particulate
  cellulose), cellulase enzyme and reducing sugar vs time; model built "from literature concepts
  and laboratory data", fitted by simultaneous nonlinear regression [V-abstract].
- Time points / replicates: UNVERIFIED.
- Raw data: figures only (1997, closed Elsevier). Note: Hardoul A. & Mghazli Z. (2024) arXiv
  2404.03839 "A Complete Mathematical Model For Trichoderma Fungi Kinetics" state they used
  Velkovska et al. 1997 cellulose/biomass/cellulase data for parameter estimation and validation
  [V-abstract]; that preprint may contain the digitized values (UNVERIFIED; arXiv blocked here).
- Licence: closed journal; arXiv preprint licence unknown.
- Suitability: strong on observables (biomass + cellulose + enzyme + sugar on insoluble
  cellulose), same genus, different lab; weak on access (digitization) and on reported
  conditions/replicates.

### 3. Delabona et al. 2016  -- same strain, same lab (CTBE), different protocol
- Citation: Delabona P.S., Lima D.J., Robl D., Rabelo S.C., Farinas C.S., Pradella J.G.C.
  (2016) "Enhanced cellulase production by Trichoderma harzianum by cultivation on glycerol
  followed by induction on cellulosic substrates", J. Ind. Microbiol. Biotechnol. 43(5):617-626,
  DOI 10.1007/s10295-016-1744-8, PMID 26883662 [V-abstract].
- Organism: T. harzianum P49P11 (same strain as the baseline) [V-abstract].
- Substrate/conditions: glycerol for high-cell-density growth, then induction with a cellulosic
  material (abstract names pretreated sugarcane bagasse; whether pure cellulose was also used is
  UNVERIFIED); bioreactor; T/pH/agitation UNVERIFIED.
- Observables: FPase, xylanase, beta-glucosidase (max 2.27 +/- 0.37 FPU/mL, 106.40 +/- 8.87
  IU/mL, 9.04 +/- 0.39 IU/mL) [V-abstract]; biomass and residual substrate UNVERIFIED.
- Replicates: SD reported, so replicates exist; n UNVERIFIED.
- Raw data: no deposit found; figures only.
- Licence: closed (OUP/Springer JIMB).
- Suitability: closest protocol to the baseline and same strain, so it is a same-organism
  cross-protocol test rather than a cross-lab test. Substrate is lignocellulose, not cellulose.

### 4. de Castro et al. 2010  -- same species, different strain and lab
- Citation: de Castro A.M., Pedro K.C.N.R., da Cruz J.C., Ferreira M.C., Leite S.G.F.,
  Pereira N. Jr. (2010) "High-Yield Endoglucanase Production by Trichoderma harzianum IOC-3844
  Cultivated in Pretreated Sugarcane Mill Byproduct", Enzyme Research 2010:854526,
  DOI 10.4061/2010/854526, PMC2962913, PMID 21048871 [V-abstract].
- Organism: T. harzianum IOC-3844 (UFRJ) [V-abstract].
- Substrate/conditions: submerged, pretreated sugarcane bagasse (cellulignin), conical flasks,
  30 C, 200 rpm, 72 h main run (FPase maximum 72-96 h); aliquots withdrawn at periodic
  intervals, sonicated for enzyme desorption [V-abstract]. Initial substrate concentration,
  inoculum UNVERIFIED.
- Observables: endoglucanase 6358 U/L, beta-glucosidase 742 U/L, FPase 445 U/L at 72 h; time
  courses of these activities [V-abstract]. Biomass / residual substrate: not reported in the
  abstract; likely absent [UNVERIFIED].
- Replicates: UNVERIFIED.
- Raw data: figures only. Licence: Enzyme Research (Hindawi) is open access (CC BY typical)
  [UNVERIFIED for this article].
- Suitability: same species and different lab, open access, but enzymes-only on lignocellulose;
  no biomass or substrate-loss observable. Useful as a secondary enzyme-only check.

### 5. Myeong, Lee & Yun 2025  -- same genus (T. longibrachiatum), Avicel, open access
- Citation: "Optimization and Bioreactor Scale-Up of Cellulase Production in Trichoderma sp.
  KMF006 for Higher Yield and Performance", Int. J. Mol. Sci. 26(8):3731, 15 Apr 2025,
  DOI 10.3390/ijms26083731, PMC12027645 [V-abstract].
- Organism: Trichoderma longibrachiatum KMF006 (KCTC13500BP) per a search snippet [V-abstract].
- Substrate/conditions: flask experiments with Avicel:cellulose ratios 4:0 to 0:4, 150-210 rpm,
  baffled vs non-baffled; optimized conditions applied to a 10-L bioreactor [V-abstract].
  Concentrations, T, pH, inoculum UNVERIFIED.
- Observables: EG, BGL, CBH activities and FPU over time; EG peak at 12 d (A3C1) vs 18 d
  (control), BGL peak 15 d vs 18 d [V-abstract]. Biomass / residual cellulose UNVERIFIED.
- Replicates and supplementary data: UNVERIFIED (MDPI blocked).
- Raw data: likely figures + possible supplementary tables [UNVERIFIED]. Licence: MDPI CC BY.
- Suitability: same genus, pure Avicel, long multi-week time course, open licence; different
  species from both T. harzianum and T. reesei; biomass unknown.

### 6. Rohr et al. 2024  -- only deposited raw T. reesei time-course data found, but soluble sugars
- Citation: Rohr K. et al. (2024) "Optimizing microbioreactor cultivation strategies for
  Trichoderma reesei: from batch to fed-batch operations", Microb. Cell Fact. 23:112,
  DOI 10.1186/s12934-024-02371-8, PMID 38622596, PMC11334512 [V-abstract].
- Organism: T. reesei wild type, RutC30, RutC30 TR3158 [V-abstract].
- Substrate/conditions: BioLector microbioreactor, round well plate, 1000 rpm; batch on glucose
  (2.5 g/L) then lactose feed 0.3-0.75 g/(L h) [V-abstract]. No insoluble cellulose.
- Observables: scattered light (biomass proxy, correlated with CDW), offline cellobiohydrolase
  and beta-glucosidase activities [V-abstract]; replicate reproducibility discussed.
- Raw data: Springer Nature Figshare collection 7182789 and "Additional file 1" (figshare item
  25608693) [V-abstract that they exist; contents UNVERIFIED].
- Licence: BMC articles are CC BY; figshare items usually CC BY [UNVERIFIED].
- Suitability: low for a cellulose-degradation transfer (soluble substrate, microtiter scale);
  possibly useful for a growth/induction sub-model on soluble carbon only.

### 7. Ahamed & Vermette 2008  -- same genus, different lab, fed-batch
- Citation: Ahamed A., Vermette P. (2008) "Culture-based strategies to enhance cellulase enzyme
  production from Trichoderma reesei RUT-C30 in bioreactor culture conditions", Biochem. Eng. J.
  40:399-407 [V-abstract]; DOI not verified.
- Conditions: fed-batch, 7-L stirred tank, four media; cellulose-yeast extract medium gave
  FPase 5.02 U/mL, CMCase 4.2 U/mL, biomass 14.7 g/L, 69.8 U/(L h) [V-abstract]. Cellulose
  type (Solka Floc?) and concentration UNVERIFIED.
- Observables: biomass vs time (biphasic: yeast extract then cellulose hydrolysis), FPase,
  CMCase, protein [V-abstract]. Residual cellulose UNVERIFIED.
- Raw data: figures only; closed. Replicates UNVERIFIED.
- Suitability: moderate; fed-batch feeding complicates a no-refit prediction.

### 8. Peciulyte et al. 2014  -- RUT-C30 on Avicel, protein/secretome focus
- Citation: Peciulyte A., Anasontzis G.E., Karlström K., Larsson P.T., Olsson L. (2014)
  "Morphology and enzyme production of Trichoderma reesei Rut C-30 are affected by the physical
  and structural characteristics of cellulosic substrates", Fungal Genet. Biol. 72:64-72
  (ScienceDirect PII S1087184514001340) [V-abstract]; DOI not verified.
- Conditions: submerged cultures on Avicel and four cellulosic pulps; proteins detected from
  30 h with continuous increase [V-abstract]. Biomass, residual cellulose, FPU time courses
  UNVERIFIED.
- Raw data: figures only; closed. Suitability: moderate-low pending full-text check.

### 9. Pakula et al. 2005  -- chemostat on lactose; not a cellulose time course
- Citation: Pakula T.M., Salonen K., Uusitalo J., Penttilä M. (2005) "The effect of specific
  growth rate on protein synthesis and secretion in the filamentous fungus Trichoderma reesei",
  Microbiology 151:135-143, DOI 10.1099/mic.0.27458-0 [V-abstract].
- Content: chemostat cultures on lactose; secreted protein most efficient at mu 0.022-0.033
  h-1; max specific protein production 4.1 mg/(g h) at mu 0.031 h-1; biomass yield ~0.6 g/g
  [V-abstract]. Strain not captured [UNVERIFIED].
- Suitability: unsuitable as a transfer time course (steady-state, soluble substrate). Could
  serve as an independent steady-state constraint on specific production rate vs growth rate.

### 10. Ma et al. 2013  -- contents not verifiable
- Citation: Ma L., Li C., Yang Z., Jia W., Zhang D., Chen S. (2013) "Kinetic studies on batch
  cultivation of Trichoderma reesei and application to enhance cellulase production by fed-batch
  fermentation", J. Biotechnol. 166(4):192-197 [V-abstract]; DOI not verified.
- Content confirmed only at the level of: kinetic models for cell growth, substrate consumption
  and cellulase production in batch; modified Luedeking-Piret; fed-batch application.
  Strain, substrate (cellulose vs lactose), observables, replicates: UNVERIFIED. The title
  given in the brief ("Determination of ... growth on cellulose") did not match any result.
- Raw data: none found; figures only.

### 11. Lo et al. 2010  -- continuous culture on acid hydrolysate, not cellulose
- Citation: Lo C.-M., Zhang Q., Callow N.V., Ju L.-K. (2010) "Cellulase production by continuous
  culture of Trichoderma reesei Rut C30 using acid hydrolysate prepared to retain more
  oligosaccharides for induction", Bioresour. Technol. 101(2):717-723,
  DOI 10.1016/j.biortech.2009.08.056, PMID 19775887 [V-abstract].
- Content: continuous culture on a soluble sawdust acid hydrolysate; not an insoluble-cellulose
  batch. The brief's description "RUT-C30 on cellulose" does not match this paper. Lo's Akron
  dissertation (OhioLINK accession akron1205776927, "Cellulase production by Trichoderma reesei
  Rut C30") may hold cellulose batch data [UNVERIFIED; blocked].

### 12. Bader et al. 1993  -- potato pulp, figures only
- Citation: Bader J., Klingspohn U., Bellgardt K.-H., Schügerl K. (1993) "Modelling and
  simulation of the growth and enzyme production of Trichoderma reesei Rut C30", J. Biotechnol.
  29:121-135 (ScienceDirect PII 0168-1656(93)90045-O; DOI derived from PII, not independently
  verified) [V-abstract].
- Content: growth on cellulosic materials, especially potato pulp, batch and fed-batch; model
  of substrate uptake, maintenance, enzyme synthesis and enzymatic hydrolysis [V-abstract].
- Suitability: low (potato pulp, 1993 figures, closed).
- "Bischoff": no dataset or modelling paper matching this name was found. The only related hit
  is the review Bischof R.H., Ramoni J., Seiboth B. (2016) Microb. Cell Fact. 15:106 ("Cellulases
  and beyond..."), which contains no primary time-course data. Treat the brief's "Bischoff" as
  unresolved.

### 13. Gelain's other outputs (same lab)
- Gelain L. et al. (2015) "Mathematical modeling of enzyme production using Trichoderma
  harzianum P49P11 and sugarcane bagasse as carbon source", Bioresour. Technol. 198:101-107,
  DOI 10.1016/j.biortech.2015.08.148 (as given by a search snippet), PMID 26378961 [V-abstract].
  Pretreated sugarcane bagasse at 5, 10, 20, 30, 40 g/L; model for cell growth, substrate,
  cellulases, beta-glucosidase, xylanase [V-abstract]. How biomass was measured on insoluble
  bagasse, time points, replicates: UNVERIFIED. No deposit found; figures only. Same strain,
  same lab; lignocellulose, not cellulose.
- Gelain L. (2020) PhD thesis, TU Delft, "Mathematical modelling of cellulase production and
  continuous production of enzymes under carbon-limited conditions by Trichoderma harzianum
  P49P11", DOI 10.4233/uuid:cf8840b6-c075-4e3e-af43-2b9fbc7ff0a1 (PDF on pure.tudelft.nl)
  [V-abstract]. Chemostats on glucose, sucrose, fructose/glucose, CMC, CMC/glucose; PNPGase
  productivity. Not a cellulose time course. Related: "Continuous production of enzymes under
  carbon-limited conditions by T. harzianum P49P11" (ScienceDirect PII S1878614620301604,
  journal not verified) and "Analysis of the proteins secreted by T. harzianum P49P11 under
  carbon-limited conditions" (J. Proteomics 2020, PII S1874391920302906, PMID 32736135).
- bioRxiv 2022.06.19.496725 "An insight into cellulolytic capacity of the Trichoderma harzianum
  P49P11 revealed by omics approaches": batch on crystalline cellulose, 5-day time course of
  beta-glucosidase and xylanase activity plus secretome [V-abstract]; raw activity data likely
  figures/supplement; proteomics deposit UNVERIFIED.

### 14. Other same-genus / other-genus candidates (lower priority)
- Novy V., Schmid M., Eibinger M., Petrasek Z., Nidetzky B. (2016) Biotechnol. Biofuels 9:169,
  DOI 10.1186/s13068-016-0584-0, CC BY. T. reesei QM9414 and delta-cre1 on lactose and wheat
  straw; 0.69-2.31 FPU/mL in 8 d; micromorphology, protein [V-abstract]. Lignocellulose; biomass
  via imaging; figures.
- Antonov E. et al. (2016) Microb. Cell Fact. 15:164, DOI 10.1186/s12934-016-0567-7, CC BY.
  RUT-C30 in RAMOS online-monitored shake flasks on commercial cellulosic substrates; respiration
  (OTR) time courses correlate with crystallinity; two-phase behaviour [V-abstract]. Observable is
  respiration, which FungMod does not currently emit.
- T. harzianum HBA03 (domestic-wastewater paper, ScienceDirect PII S1359511316309540, journal
  and DOI not verified): microcrystalline cellulose inducer, bubble column; FPase 5.6/5.0 U/mL,
  CMCase 12.0/14.4 U/mL; productivities 10.2 and 64.6 U/(L h) [V-abstract]. Figures only.
- Carvalho M.L.A. et al. (2014) Enzyme Research 2014:703291, DOI 10.1155/2014/703291, CC BY.
  Penicillium funiculosum ATCC 11797, stirred tank, Avicel 10 g/L, 220 rpm, 0.6 vvm; FPase 508,
  EG 9204, BGL 2395 U/L [V-abstract]. RSM design; time-course and biomass UNVERIFIED.
- Ritter C.E.T., Camassola M., Zampieri D., Silveira M.M., Dillon A.J.P. (2013) Enzyme Research
  2013:240219, DOI 10.1155/2013/240219, CC BY. P. echinulatum 9A02S1, cellulose + sorbitol;
  FPA 1.95 +/- 0.04 IU/mL at day 7 (SD reported) [V-abstract]. Different genus; figures.
- Aspergillus niger: no Avicel submerged time course with biomass + residual cellulose located.
  The only deposited A. niger / T. reesei item found is a proteomics dataset (Data in Brief 2016,
  USDA Ag Data Commons / figshare 24852612), not kinetics.

### 15. PEtab benchmark collection and BioModels
- PEtab (Benchmarking-Initiative/Benchmark-Models-PEtab): repository could not be listed from
  this session (GitHub access restricted to felixlaga/fungmod; gh api returned 403). Search
  results describe the README table (Boehm_JProteomeRes2014, Fujita_SciSignal2010,
  Lucarelli_CellSystems2018, ...). No search surfaced any fungal, Trichoderma, Aspergillus, or
  cellulase model in the collection; to my knowledge the collection has none [UNVERIFIED
  exhaustively].
- BioModels: API blocked. Search results show only the CoReCo genome-scale (constraint-based)
  models of Castillo et al. 2016 (Biotechnol. Biofuels 9:252, DOI 10.1186/s13068-016-0665-0),
  e.g. MODEL1604280005 (C. globosum) and MODEL1604280023 (R. oryzae); the T. reesei model ID was
  not captured. These carry no time-course data and are not kinetic. No kinetic cellulase
  production model with data was found in BioModels.

### 16. Repository sweeps
- Zenodo, Figshare, Dryad, Mendeley Data: APIs and pages blocked; web searches for Trichoderma
  / cellulase / Avicel time-course deposits returned nothing except the Rohr 2024 figshare
  collection (soluble sugars) and the JGI/OSTI resequencing dataset 1487565 (genomics, not
  kinetics). A manual search on those platforms by someone with access is still recommended.

## Ranking (top 3) and recommendation

1. Sáez et al. 2002 / Schell et al. 2002 (NREL): T. reesei on Solka-floc, 7-L batch, cell mass
   + residual cellulose + soluble/adsorbed protein + sugars + CO2 to 168 h, different lab.
   Best match to FungMod's substrate-loss / biomass / product outputs. Digitization-only; strain,
   replicates and conditions must be read from the full text and the NREL report.
2. Velkovska et al. 1997: T. reesei RUT-C30 batch on particulate cellulose with biomass,
   cellulose, cellulase and reducing sugar vs time, different lab. Digitization-only; check
   whether Hardoul & Mghazli 2024 (arXiv 2404.03839) tabulated the digitized values.
3. Delabona et al. 2016: same strain (P49P11), glycerol growth then cellulosic induction, SD
   reported for FPase/xylanase/BGL. Closest protocol to the baseline but same lab and
   lignocellulose substrate, so it tests cross-protocol rather than cross-lab transfer.
   Runner-ups: de Castro 2010 (same species, different lab, open access, enzymes only) and
   Myeong et al. 2025 (Trichoderma longibrachiatum on Avicel, CC BY, multi-week FPU/EG/BGL/CBH).

Honest bottom line: no open, replicate-annotated, raw-data deposit of a submerged
T. harzianum / T. reesei cellulose batch with biomass + substrate + enzyme time courses other
than Gelain 2020 was found. Every suitable candidate is digitization-only, so the transfer test
should be labelled "digitized-figure validation" in provenance, with digitization uncertainty
carried explicitly. The only raw-data deposit found (Rohr 2024) is on glucose/lactose.

## Suggested next step

Have a person with normal web access (a) read Sáez 2002 and Schell 2002 full texts to confirm
strain, conditions, sampling times and replicate structure and to check for tabulated data,
(b) download Velkovska 1997 and the Hardoul & Mghazli 2024 preprint to see whether digitized
tables exist, and (c) open the Mendeley record for shd3wcczsr/2 to confirm its licence. Only
then register one of them as a digitization-only transfer dataset with explicit uncertainty.
