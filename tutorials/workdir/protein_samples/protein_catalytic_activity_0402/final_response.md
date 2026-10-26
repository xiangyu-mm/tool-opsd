Plan update:
1. [✓] Analyze the sequence for length, composition, domains, and homologous proteins.
2. [✓] Retrieve curated functional annotations, catalytic activity, cofactors, and pathway context.
3. [✓] Review the stored evidence in the knowledge graph.
4. [✓] Synthesize the functional summary and chemical reaction.

## Functional identification

The 761-residue protein is **phosphoribosylformylglycinamidine synthase subunit PurL**, also called the **large/long-form PurL subunit** of FGAM synthase.

This assignment is highly confident because the sequence is an **exact sequence match** to the reviewed UniProt PurL protein Q8DIA7, with full-length coverage. It also contains the expected domain organization:

- FGAR-AT linker domain
- Tandem AIRS/AIRS-C domain architecture characteristic of long-form PurL proteins
- Conserved ATP/substrate-binding regions

The protein is predicted to be a soluble cytoplasmic enzyme of approximately **81.4 kDa**, with a calculated pI of approximately **4.87**.

## Catalytic activity

PurL catalyzes the **ATP-dependent amidation of formylglycinamide ribonucleotide (FGAR)** to produce **formylglycinamidine ribonucleotide (FGAM)** during de novo purine biosynthesis.

The overall reaction performed by the FGAM synthase complex is:

\[
\text{FGAR} + \text{L-glutamine} + \text{ATP} + \text{H}_2\text{O}
\rightarrow
\text{FGAM} + \text{L-glutamate} + \text{ADP} + \text{P}_{i} + \text{H}^{+}
\]

More explicitly:

\[
\text{N(2)-formyl-N(1)-(5-phospho-}\beta\text{-D-ribosyl)glycinamide}
+ \text{L-glutamine} + \text{ATP} + \text{H}_2\text{O}
\]

\[
\rightarrow
\text{2-formamido-N(1)-(5-O-phospho-}\beta\text{-D-ribosyl)acetamidine}
+ \text{L-glutamate} + \text{ADP} + \text{phosphate} + \text{H}^{+}
\]

**EC number:** EC 6.3.5.3  
**Rhea:** RHEA:17129

## Mechanistic role within the complex

PurL is one component of a three-subunit FGAM synthase system:

- **PurQ** hydrolyzes glutamine to glutamate and generates ammonia.
- **PurL** activates FGAR using ATP and incorporates the transferred ammonia into FGAR, forming FGAM.
- **PurS** assists ammonia transfer between PurQ and PurL.

Thus, although glutamine appears in the overall reaction, the direct chemical transformation carried out by PurL is the **ATP-dependent transfer of ammonia onto FGAR**. The complex is generally composed of **one PurL, one PurQ, and two PurS subunits**.

## Biological context

The reaction is an early committed amidation step in **de novo purine biosynthesis**, leading toward IMP and subsequently ATP and GTP production.

**Summary:** This sequence encodes the large PurL subunit of glutamine-dependent FGAM synthase, an ATP- and magnesium-dependent enzyme complex that converts FGAR into FGAM during de novo purine biosynthesis.