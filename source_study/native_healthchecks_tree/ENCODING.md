# Exact encoding of the bounded native language

Let Σ = {get, pause, resume} and L contain every word of length at most three.
For each a in Σ, let L_a = {ε} ∪ {a u : |u| ≤ 2}. The union of the three L_a
is L; different branches intersect only at ε.

For an internal prefix w in L_a, let h(w) be its unique history label.
The next operation b is encoded by (h(w), b, capture). The caller at w enables
exactly those requests for which wb belongs to L_a. It advances to wb, or to
the terminal caller state at depth three. The target retains a separate node
q_w for every physical history, including every leaf; the corresponding edge
goes to q_wb.

Induction on length shows that every admitted core word erases to exactly one
native word in L_a, and every native word has exactly one encoding. Each core
event represents one HTTP request, so erasure preserves length. The common
terminal caller state has no outgoing edge; sharing it does not merge the
distinct physical target leaves.

For every nonempty word w, R(w) is the independently expected rich observation
at the last event and A(w) is the actual native observation. R is calculated
by repeatedly applying the reference from its specified initial state. An
incorrect actual parent is never substituted for an expected reference state.

Assign distinct positive codes to every distinct value in
{R(w), A(w) : w ∈ L_a \ {ε}}, reserving zero for the initial marker.
The rule for (h(w), b, capture) sets every state bit to the code of R(wb).
Target node q_wb exposes the code of A(wb). Core allow records capture
regardless of the API status inside that value.

Injectivity gives core equality at that event exactly when R(wb) = A(wb).
Applying this to every proper prefix gives the same core and native first
failure. Production shortestness in L_a therefore decodes to native
shortestness in L_a. The shortest failure over L is the minimum of the three
branch failures; if all branches match, all words in L match.

This is a finite observation encoding and caller-language decomposition.
It is not a quotient of physical application state: all 40 history checkpoints
remain distinct. Exact Flip clocks remain in their byte images; rich comparison
only projects their clock literals to presence and processing relationships.

Each L_a has 1 + 1 + 3 + 9 = 14 words and 13 edges, with five internal
prefixes. Its at most 26 distinct reference/actual outcomes and reserved zero
fit in five bits. Five history principals and three operation resources give
15 possible core requests. The caller enables the 13 actual edges only at
their correct prefixes.

Every reference rule contains one rule node, two guards and at most five
updates. Thirteen rules use at most 104 AST nodes. There are six caller states
and 14 target states. These bounds fit the existing 16-principal, seven-bit,
256-AST-node, 512-target-state and 16-caller-state envelopes even if all outcomes
differ. A production probe checks that worst case. An independent traversal
checks the admitted-word bijection and full union.

Complete native-tree admission precedes branch diagnosis. Missing or duplicated
evidence cannot be accepted. Replay admission instead checks exactly the
prefixes of its declared word. First-bad prefixes are computed from independent
structured outcomes, and each distinct negative word is physically rerun from
fresh native rows.
