1. [✓] Analyze the amino-acid sequence for physicochemical properties, domains, homologs, and functional annotations.  
2. [✓] Compare the strongest evidence for catalytic activity and the specific chemical reaction.  
3. [✓] Store the key findings with provenance and review them in the evidence graph.  
4. [✓] Provide a concise functional summary, clearly separating supported annotation from inference.  

## Functional identification

The 288-residue protein is **YopJ, a serine/threonine-protein acetyltransferase** from *Yersinia pseudotuberculosis*. The sequence is an **exact match** to curated YopJ reference proteins, with 100% identity and coverage. It contains the characteristic **Acetyltransf_14 domain** (PF03421).

## Catalytic reaction

YopJ transfers an acetyl group from acetyl-CoA to serine or threonine residues in protein substrates:

\[
\text{Protein-Ser-OH} + \text{acetyl-CoA}
\rightarrow
\text{Protein-Ser-O-COCH}_3 + \text{CoA}
\]

\[
\text{Protein-Thr-OH} + \text{acetyl-CoA}
\rightarrow
\text{Protein-Thr-O-COCH}_3 + \text{CoA}
\]

Thus, it catalyzes **protein serine/threonine O-acetylation**, rather than phosphorylation.

## Biological role

YopJ is a type III secretion effector that acetylates host signaling kinases, including **MAP2K1, MAP2K6, TAK1/MAP3K7, IKKα, IKKβ, and RIPK2**. Acetylation of regulatory serine/threonine residues prevents their phosphorylation and activation, suppressing MAPK and NF-κB signaling and promoting host-cell death.

**1D-myo-Inositol hexakisphosphate (IP6; ChEBI:CHEBI:58130)** acts as an allosteric activator that promotes productive interaction with acetyl-CoA. It is best described here as an activating ligand rather than a consumed reaction substrate.

**Confidence: very high**, because the query sequence exactly matches reviewed YopJ proteins and the catalytic activity, active-site residues, domain, and reaction are curator-supported.