## Functional identification

The 541-residue protein is **formimidoyltransferase–cyclodeaminase (FTCD)**, a bifunctional, folate-dependent enzyme. The identification is strong: the sequence is an exact match to a reviewed FTCD reference and contains the characteristic **FTCD_N**, **FTCD**, and **FTCD_C** domains.

- Length: 541 aa  
- Approximate mass: 59.2 kDa  
- EC activities: **EC 2.1.2.5** and **EC 4.3.1.4**  
- Cofactor/substrate: tetrahydrofolate derivatives  
- Catalytic residues reported in the reference: approximately **Ser/active-site position 82** for transferase activity and **position 412** for cyclodeaminase activity  
- Likely oligomer: homo-octamer

## Catalytic reactions

FTCD performs two sequential reactions that transfer the formimino group from histidine degradation into folate metabolism.

### 1. Glutamate formimidoyltransferase activity

In the physiological histidine-degradation direction:

\[
\text{N-formimidoyl-L-glutamate} + \text{tetrahydrofolate}
\rightarrow
\text{L-glutamate} + \text{5-formimidoyltetrahydrofolate}
\]

The database also represents the reverse direction:

\[
\text{5-formimidoyltetrahydrofolate} + \text{L-glutamate}
\rightarrow
\text{N-formimidoyl-L-glutamate} + \text{tetrahydrofolate}
\]

This activity is mapped to **Rhea RHEA:15097** and **EC 2.1.2.5**.

### 2. Formimidoyltetrahydrofolate cyclodeaminase activity

\[
\text{5-formimidoyltetrahydrofolate} + 2\text{H}^+
\rightarrow
\text{5,10-methenyltetrahydrofolate} + \text{NH}_4^+
\]

This activity is mapped to **Rhea RHEA:22736** and **EC 4.3.1.4**.

## Overall biological role

The enzyme channels the formimino group generated during **L-histidine catabolism** into the folate pool. It converts **N-formiminoglutamate (FIGLU)** into **L-glutamate**, while generating **5,10-methenyltetrahydrofolate**, a one-carbon folate metabolite.

Thus, the protein is best described as a **bifunctional histidine-catabolism and one-carbon-metabolism enzyme**, rather than a single-reaction catalyst.