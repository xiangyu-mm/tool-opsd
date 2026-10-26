## Functional identification

The 640-residue protein is **1-deoxy-D-xylulose-5-phosphate synthase (DXS)**, also called **DXP synthase**.

The assignment is highly confident because the sequence is an **exact match to the curated Swiss-Prot protein Q0C154** and has the characteristic DXS domain architecture:

- DXP_synthase_N domain
- E1/thiamine-enzyme region
- Transketolase-pyrimidine-binding region
- Transketolase C-terminal region

**Classification:** EC **2.2.1.7**  
**Likely oligomeric state:** Homodimer  
**Required cofactors:** **Thiamine diphosphate (ThDP/TPP)** and **Mg²⁺**

## Catalytic reaction

DXS catalyzes a **ThDP-dependent acyloin condensation** between pyruvate and D-glyceraldehyde 3-phosphate:

\[
\text{D-glyceraldehyde 3-phosphate} + \text{pyruvate}
\rightarrow
\text{1-deoxy-D-xylulose 5-phosphate} + CO_2
\]

The Rhea representation includes proton balance:

\[
\text{D-glyceraldehyde 3-phosphate} + \text{pyruvate} + H^+
\rightarrow
\text{1-deoxy-D-xylulose 5-phosphate} + CO_2
\]

Mechanistically, the enzyme uses ThDP to activate pyruvate, facilitates its decarboxylation, and then transfers the resulting two-carbon fragment onto glyceraldehyde 3-phosphate. The product is **1-deoxy-D-xylulose 5-phosphate (DXP)**.

This is the first enzymatic step of the **methylerythritol 4-phosphate (MEP) pathway**, which produces the precursors for isoprenoid and terpenoid biosynthesis.

**Evidence:** exact curated sequence match; EC 2.2.1.7; Rhea **RHEA:12605**.