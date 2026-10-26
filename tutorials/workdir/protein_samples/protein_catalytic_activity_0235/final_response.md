### Functional identification

The 348-residue protein is most consistent with **RlmN, a radical-SAM RNA methyltransferase** (EC **2.1.1.192**), probably a **dual-specificity enzyme** acting on both rRNA and tRNA.

### Evidence

- Strong homology to curated RlmN proteins:
  - approximately **55–56% sequence identity**
  - **>90% sequence coverage**
  - E-values around **10⁻¹²⁴ to 10⁻¹³⁵**
- Conserved domain architecture:
  - **RlmN_N domain**
  - **Radical_SAM domain**
- Cysteine-rich region compatible with binding a catalytic **[4Fe–4S] cluster**
- Protein size and basic character are typical of a soluble RNA-binding enzyme.

### Catalytic activity

RlmN methylates the **C2 position of adenine** in structured RNA substrates:

1. **23S rRNA adenine 2503**
   
   \[
   \text{A2503 in 23S rRNA} \rightarrow \text{2-methyladenosine-2503}
   \]

2. **tRNA adenine 37**
   
   \[
   \text{A37 in tRNA} \rightarrow \text{2-methyladenosine-37}
   \]

The reaction uses **S-adenosyl-L-methionine (SAM)** and radical-SAM chemistry. A simplified representation is:

\[
\text{adenosine in RNA} + 2\,\text{SAM}
\rightarrow
\text{2-methyladenosine in RNA}
+ \text{5′-deoxyadenosine}
+ \text{S-adenosylhomocysteine}
+ \text{methionine}
\]

The complete biochemical cycle also requires reducing equivalents, represented in reaction databases by reduced iron–sulfur electron donors.

### Mechanistic interpretation

RlmN is unusual because it combines:

- a radical-SAM **[4Fe–4S] cluster**, which activates SAM to generate a **5′-deoxyadenosyl radical**;
- an **S-methylcysteine intermediate**, through which the methyl group is transferred to adenine.

Thus, this is not a conventional methyltransferase that simply transfers methyl directly from SAM to RNA. It performs radical-mediated methylation at the otherwise difficult **C2 carbon of adenine**.

### Functional summary

**Most likely function:** a cytoplasmic, [4Fe–4S]-dependent radical-SAM enzyme that methylates adenine at position 2503 of 23S rRNA and adenine 37 of tRNAs, producing 2-methyladenosine residues. The dual rRNA/tRNA specificity is strongly supported by close curated homologs, although it remains an inference for this exact sequence rather than a direct experimental demonstration.