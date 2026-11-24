import Lean

/-!
Caller-protocol diagnosis for a fixed reference interpretation.

The enabled predicate restricts requests on a deterministic target graph.  The
protocol construction at the end uses nodes (target state, caller state), so
protocol-disabled transitions are not obligations.  Complete observation maps a
node to the entire reference state.  No reference state is included in the graph
whose finite enumeration supplies the witness bound.

The proofs below establish local/trace equivalence, existence and shortestness
of an admitted counterexample, and its bound by any finite list covering the
reachable product nodes.  With a duplicate-free exact reachable enumeration,
that list length is |R_A|.  In particular, the finite bound is proved here; a
BFS rank or a simple-path bound is not assumed.

A source function denotes one fixed binding throughout every word.  These
statements do not certify source extraction, a Python traversal, an application's
entry points, or that measured contexts cover all source executions.
-/
namespace AuthRefine.Protocol

def finish {Node Input Output : Type} (target : Node → Input → Output × Node) :
    Node → List Input → Node
  | node, [] => node
  | node, input :: rest => finish target (target node input).2 rest

def trace {Node Input Output State : Type}
    (target : Node → Input → Output × Node) (observe : Node → State) :
    Node → List Input → List (Output × State)
  | _, [] => []
  | node, input :: rest =>
      ((target node input).1, observe (target node input).2) ::
        trace target observe (target node input).2 rest

def admitted {Node Input Output : Type}
    (target : Node → Input → Output × Node) (enabled : Node → Input → Prop) :
    Node → List Input → Prop
  | _, [] => True
  | node, input :: rest => enabled node input ∧ admitted target enabled (target node input).2 rest

def visited {Node Input Output : Type} (target : Node → Input → Output × Node) :
    Node → List Input → List Node
  | node, [] => [node]
  | node, input :: rest => node :: visited target (target node input).2 rest

def distinct {A : Type} : List A → Prop
  | [] => True
  | item :: rest => item ∉ rest ∧ distinct rest

variable {Node Input Output State : Type}
variable (target : Node → Input → Output × Node)
variable (enabled : Node → Input → Prop)
variable (observe : Node → State)
variable (source : State → Input → Output × State)

theorem finish_append (node : Node) (first second : List Input) :
    finish target node (first ++ second) = finish target (finish target node first) second := by
  induction first generalizing node with
  | nil => rfl
  | cons input rest ih => simpa [finish] using ih (target node input).2

theorem trace_append (node : Node) (first second : List Input) :
    trace target observe node (first ++ second) = trace target observe node first ++
      trace target observe (finish target node first) second := by
  induction first generalizing node with
  | nil => rfl
  | cons input rest ih => simp [trace, finish, ih]

theorem admitted_append (node : Node) (first second : List Input) :
    admitted target enabled node (first ++ second) ↔
      admitted target enabled node first ∧
      admitted target enabled (finish target node first) second := by
  induction first generalizing node with
  | nil => simp [admitted, finish]
  | cons input rest ih => simp [admitted, finish, ih, and_assoc]

theorem visited_length (node : Node) (word : List Input) :
    (visited target node word).length = word.length + 1 := by
  induction word generalizing node with
  | nil => rfl
  | cons input rest ih => simp [visited, ih, Nat.add_assoc]

theorem visited_prefix (node : Node) (word : List Input) (member : Node)
    (present : member ∈ visited target node word) :
    ∃ before after, word = before ++ after ∧ finish target node before = member := by
  induction word generalizing node with
  | nil =>
      have equal : member = node := by simpa [visited] using present
      exact ⟨[], [], rfl, equal.symm⟩
  | cons input rest ih =>
      have cases : member = node ∨ member ∈ visited target (target node input).2 rest := by
        simpa [visited] using present
      cases cases with
      | inl equal => exact ⟨[], input :: rest, rfl, equal.symm⟩
      | inr later =>
          obtain ⟨before, after, split, endpoint⟩ := ih (target node input).2 later
          exact ⟨input :: before, after, by simp [split], by simpa [finish] using endpoint⟩

/- A finite-list pigeonhole argument, proved without an imported finite-set
   library or an assumed cardinality lemma. -/
theorem filter_length_le {A : Type} (predicate : A → Bool) (items : List A) :
    (items.filter predicate).length ≤ items.length := by
  induction items with
  | nil => simp
  | cons item rest ih =>
      cases hp : predicate item <;> simp [List.filter, hp] <;> omega

theorem filter_length_lt_of_removed {A : Type} (predicate : A → Bool)
    (items : List A) (item : A) (present : item ∈ items) (removed : predicate item = false) :
    (items.filter predicate).length < items.length := by
  induction items with
  | nil => simp at present
  | cons head rest ih =>
      have cases : item = head ∨ item ∈ rest := List.mem_cons.mp present
      cases cases with
      | inl equal =>
          subst head
          have bound := filter_length_le predicate rest
          simp [List.filter, removed]
          omega
      | inr later =>
          have bound := ih later
          cases hp : predicate head <;> simp [List.filter, hp] <;> omega

theorem distinct_length_le_cover {A : Type} (items cover : List A)
    (unique : distinct items) (covered : ∀ item, item ∈ items → item ∈ cover) :
    items.length ≤ cover.length := by
  let _ : DecidableEq A := Classical.typeDecidableEq A
  induction items generalizing cover with
  | nil => simp
  | cons item rest ih =>
      obtain ⟨absent, tail_unique⟩ := unique
      let remaining := cover.filter (fun other => decide (other ≠ item))
      have tail_covered : ∀ other, other ∈ rest → other ∈ remaining := by
        intro other present
        have unequal : other ≠ item := by
          intro equal
          subst other
          exact absent present
        have in_cover := covered other (List.mem_cons_of_mem item present)
        exact List.mem_filter.mpr ⟨in_cover, decide_eq_true unequal⟩
      have tail_bound := ih remaining tail_unique tail_covered
      have removed : (fun other => decide (other ≠ item)) item = false := by simp
      have strict := filter_length_lt_of_removed
        (fun other => decide (other ≠ item)) cover item
        (covered item (List.mem_cons_self item rest)) removed
      change (cover.filter (fun other => decide (other ≠ item))).length < cover.length at strict
      change rest.length ≤ (cover.filter (fun other => decide (other ≠ item))).length at tail_bound
      simp only [List.length_cons]
      omega

/- Deleting a repeated-node cycle preserves admissibility and the endpoint.
   Thus every shortest reaching word has pairwise distinct visited nodes. -/
theorem shortest_path_distinct (node : Node) (word : List Input)
    (accepted : admitted target enabled node word)
    (minimal : ∀ alternative, admitted target enabled node alternative →
      finish target node alternative = finish target node word → word.length ≤ alternative.length) :
    distinct (visited target node word) := by
  induction word generalizing node with
  | nil => simp [visited, distinct]
  | cons input rest ih =>
      obtain ⟨first_enabled, rest_accepted⟩ := accepted
      constructor
      · intro repeated
        obtain ⟨before, after, split, returns⟩ :=
          visited_prefix target (target node input).2 rest node repeated
        have admitted_split :=
          (admitted_append target enabled (target node input).2 before after).mp
            (by simpa [split] using rest_accepted)
        have after_accepted : admitted target enabled node after := by
          simpa [returns] using admitted_split.2
        have same_endpoint : finish target node after = finish target node (input :: rest) := by
          simp only [finish]
          rw [split, finish_append, returns]
        have impossible := minimal after after_accepted same_endpoint
        simp [split] at impossible
        omega
      · apply ih (target node input).2 rest_accepted
        intro alternative alternative_accepted same_endpoint
        have accepted_alternative : admitted target enabled node (input :: alternative) :=
          ⟨first_enabled, alternative_accepted⟩
        have same_endpoint' : finish target node (input :: alternative) =
            finish target node (input :: rest) := by simpa [finish] using same_endpoint
        have shorter := minimal (input :: alternative) accepted_alternative same_endpoint'
        simpa using shorter

theorem shortest_path_finite_bound (initial : Node) (word : List Input)
    (accepted : admitted target enabled initial word)
    (minimal : ∀ alternative, admitted target enabled initial alternative →
      finish target initial alternative = finish target initial word → word.length ≤ alternative.length)
    (reachable_nodes : List Node)
    (covers : ∀ stem, admitted target enabled initial stem →
      finish target initial stem ∈ reachable_nodes) :
    word.length + 1 ≤ reachable_nodes.length := by
  have unique := shortest_path_distinct target enabled initial word accepted minimal
  have covered : ∀ node, node ∈ visited target initial word → node ∈ reachable_nodes := by
    intro node present
    obtain ⟨before, after, split, endpoint⟩ := visited_prefix target initial word node present
    have prefix_ok := ((admitted_append target enabled initial before after).mp
      (by simpa [split] using accepted)).1
    simpa [endpoint] using covers before prefix_ok
  simpa [visited_length] using distinct_length_le_cover (visited target initial word) reachable_nodes unique covered

/- Complete observations recover the reference state at the end of every
   agreeing stem.  This is where a decision-only observation would fail. -/
theorem finish_of_equal_trace (node : Node) (word : List Input)
    (equal_trace : trace source id (observe node) word = trace target observe node word) :
    finish source (observe node) word = observe (finish target node word) := by
  induction word generalizing node with
  | nil => rfl
  | cons input rest ih =>
      have parts :
          (source (observe node) input).1 = (target node input).1 ∧
          (source (observe node) input).2 = observe (target node input).2 ∧
          trace source id (source (observe node) input).2 rest =
            trace target observe (target node input).2 rest := by
        simpa [trace, and_assoc] using equal_trace
      have tail_equal : trace source id (observe (target node input).2) rest =
          trace target observe (target node input).2 rest := by simpa [parts.2.1] using parts.2.2
      simpa [finish, parts.2.1] using ih (target node input).2 tail_equal

def cell_agrees (node : Node) (input : Input) : Prop :=
    source (observe node) input = ((target node input).1, observe (target node input).2)

def reachable (initial node : Node) : Prop :=
    ∃ word, admitted target enabled initial word ∧ finish target initial word = node

theorem snoc_induction {A : Type} (P : List A → Prop) (base : P [])
    (step : ∀ items item, P items → P (items ++ [item])) : ∀ items, P items := by
  have extend : ∀ suffix stem, P stem → P (stem ++ suffix) := by
    intro suffix
    induction suffix with
    | nil => intro stem h; simpa using h
    | cons item rest ih =>
        intro stem h
        simpa [List.append_assoc] using ih (stem ++ [item]) (step stem item h)
  intro items
  simpa using extend items [] base

theorem matching_admitted_prefixes (initial : Node) (depth : Nat)
    (earlier_cells : ∀ stem, admitted target enabled initial stem → stem.length < depth →
      ∀ input, enabled (finish target initial stem) input →
        cell_agrees target observe source (finish target initial stem) input) :
    ∀ word, admitted target enabled initial word → word.length ≤ depth →
      finish source (observe initial) word = observe (finish target initial word) ∧
      trace source id (observe initial) word = trace target observe initial word := by
  apply snoc_induction
  · intro _ _; simp [finish, trace]
  · intro stem input ih accepted short
    have split := (admitted_append target enabled initial stem [input]).mp accepted
    have length_bound : stem.length < depth := by
      simp only [List.length_append, List.length_cons, List.length_nil] at short
      omega
    obtain ⟨state_equal, trace_equal⟩ := ih split.1 (by omega)
    have equation := earlier_cells stem split.1 length_bound input split.2.1
    unfold cell_agrees at equation
    constructor
    · simp [finish_append, finish, state_equal, equation]
    · simp [trace_append, trace, finish, state_equal, trace_equal, equation]

theorem local_iff_admitted_trace_equivalence (initial : Node) :
    (∀ node, reachable target enabled initial node → ∀ input, enabled node input →
      cell_agrees target observe source node input) ↔
    (∀ word, admitted target enabled initial word →
      trace source id (observe initial) word = trace target observe initial word) := by
  constructor
  · intro cells word accepted
    have earlier : ∀ stem, admitted target enabled initial stem → stem.length < word.length →
        ∀ input, enabled (finish target initial stem) input →
          cell_agrees target observe source (finish target initial stem) input := by
      intro stem prefix_ok _ input input_ok
      exact cells _ ⟨stem, prefix_ok, rfl⟩ input input_ok
    exact (matching_admitted_prefixes target enabled observe source initial word.length earlier
      word accepted (Nat.le_refl _)).2
  · intro equivalent node reached input input_ok
    obtain ⟨stem, accepted, endpoint⟩ := reached
    have prefix_equal := equivalent stem accepted
    have state_equal := finish_of_equal_trace target observe source initial stem prefix_equal
    have extended : admitted target enabled initial (stem ++ [input]) := by
      apply (admitted_append target enabled initial stem [input]).mpr
      exact ⟨accepted, by simpa [admitted, endpoint] using input_ok⟩
    have equal := equivalent (stem ++ [input]) extended
    rw [trace_append, trace_append, prefix_equal] at equal
    have tails := List.append_cancel_left equal
    have pair_equal : source (observe node) input = ((target node input).1, observe (target node input).2) := by
      have parts :
          (source (finish source (observe initial) stem) input).1 =
            (target (finish target initial stem) input).1 ∧
          (source (finish source (observe initial) stem) input).2 =
            observe (target (finish target initial stem) input).2 := by
        simpa [trace] using tails
      apply Prod.ext
      · simpa [state_equal, endpoint] using parts.1
      · simpa [state_equal, endpoint] using parts.2
    exact pair_equal


/- Natural-number minimality is derived from well-founded induction. -/
theorem exists_minimum (property : Nat → Prop) (present : ∃ n, property n) :
    ∃ n, property n ∧ ∀ m, property m → n ≤ m := by
  have select : ∀ n, property n → ∃ least, property least ∧ ∀ m, property m → least ≤ m := by
    intro n
    induction n using Nat.strongInductionOn with
    | ind n ih =>
        intro yes
        cases Classical.em (∃ m, m < n ∧ property m) with
        | inl earlier =>
            obtain ⟨m, smaller, yes_m⟩ := earlier
            exact ih m smaller yes_m
        | inr earliest =>
            refine ⟨n, yes, ?_⟩
            intro m yes_m
            exact Nat.le_of_not_gt (fun smaller => earliest ⟨m, smaller, yes_m⟩)
  obtain ⟨n, yes⟩ := present
  exact select n yes

theorem first_bad_cell_shortest (initial : Node) (stem : List Input)
    (accepted : admitted target enabled initial stem) (input : Input)
    (input_ok : enabled (finish target initial stem) input)
    (bad : ¬ cell_agrees target observe source (finish target initial stem) input)
    (earlier_cells : ∀ earlier, admitted target enabled initial earlier → earlier.length < stem.length →
      ∀ event, enabled (finish target initial earlier) event →
        cell_agrees target observe source (finish target initial earlier) event) :
    admitted target enabled initial (stem ++ [input]) ∧
    trace source id (observe initial) (stem ++ [input]) ≠
      trace target observe initial (stem ++ [input]) ∧
    ∀ shorter, admitted target enabled initial shorter → shorter.length < (stem ++ [input]).length →
      trace source id (observe initial) shorter = trace target observe initial shorter := by
  have same := matching_admitted_prefixes target enabled observe source initial stem.length earlier_cells
    stem accepted (Nat.le_refl _)
  constructor
  · exact (admitted_append target enabled initial stem [input]).mpr ⟨accepted, input_ok, trivial⟩
  constructor
  · intro equal
    rw [trace_append, trace_append, same.2] at equal
    have tails := List.append_cancel_left equal
    have parts :
        (source (finish source (observe initial) stem) input).1 =
          (target (finish target initial stem) input).1 ∧
        (source (finish source (observe initial) stem) input).2 =
          observe (target (finish target initial stem) input).2 := by
      simpa [trace] using tails
    apply bad
    apply Prod.ext
    · simpa [same.1] using parts.1
    · simpa [same.1] using parts.2
  · intro shorter shorter_ok length_bound
    have bounded : shorter.length ≤ stem.length := by
      simp only [List.length_append, List.length_cons, List.length_nil] at length_bound
      omega
    exact (matching_admitted_prefixes target enabled observe source initial stem.length earlier_cells
      shorter shorter_ok bounded).2

/- Main generic theorem.  The finite cover contains target/protocol nodes;
   neither reference states nor complete source/target products are counted. -/
theorem shortest_admitted_witness_bound (initial : Node) (reachable_nodes : List Node)
    (covers : ∀ word, admitted target enabled initial word →
      finish target initial word ∈ reachable_nodes)
    (disagrees : ¬ (∀ word, admitted target enabled initial word →
      trace source id (observe initial) word = trace target observe initial word)) :
    ∃ word, admitted target enabled initial word ∧ word.length ≤ reachable_nodes.length ∧
      trace source id (observe initial) word ≠ trace target observe initial word ∧
      ∀ shorter, admitted target enabled initial shorter → shorter.length < word.length →
        trace source id (observe initial) shorter = trace target observe initial shorter := by
  let property := fun n => ∃ stem, stem.length = n ∧ admitted target enabled initial stem ∧
    ∃ input, enabled (finish target initial stem) input ∧
      ¬ cell_agrees target observe source (finish target initial stem) input
  have present : ∃ n, property n := by
    apply Classical.byContradiction
    intro absent
    apply disagrees
    apply (local_iff_admitted_trace_equivalence target enabled observe source initial).mp
    intro node reached input input_ok
    apply Classical.byContradiction
    intro bad
    obtain ⟨stem, stem_ok, endpoint⟩ := reached
    exact absent ⟨stem.length, stem, rfl, stem_ok, input,
      by simpa [endpoint] using input_ok, by simpa [endpoint] using bad⟩
  obtain ⟨depth, ⟨stem, stem_length, stem_ok, input, input_ok, bad⟩, least⟩ :=
    exists_minimum property present
  have earlier_cells : ∀ earlier, admitted target enabled initial earlier → earlier.length < stem.length →
      ∀ event, enabled (finish target initial earlier) event →
        cell_agrees target observe source (finish target initial earlier) event := by
    intro earlier earlier_ok before event event_ok
    apply Classical.byContradiction
    intro bad_event
    have impossible := least earlier.length ⟨earlier, rfl, earlier_ok, event, event_ok, bad_event⟩
    omega
  have minimal : ∀ alternative, admitted target enabled initial alternative →
      finish target initial alternative = finish target initial stem → stem.length ≤ alternative.length := by
    intro alternative alternative_ok endpoint
    have smaller := least alternative.length ⟨alternative, rfl, alternative_ok, input,
      by simpa [endpoint] using input_ok, by simpa [endpoint] using bad⟩
    simpa [stem_length] using smaller
  have bound := shortest_path_finite_bound target enabled initial stem stem_ok minimal reachable_nodes covers
  obtain ⟨word_ok, word_bad, shortest⟩ :=
    first_bad_cell_shortest target enabled observe source initial stem stem_ok input input_ok bad earlier_cells
  exact ⟨stem ++ [input], word_ok, by simpa using bound, word_bad, shortest⟩

/- The concrete-to-table obligation only needs reachable concrete states.
   This strengthens the existing all-configurations lifting lemma's usability
   without claiming that a finite experimental sample proves the obligation. -/
theorem all_words_admitted (node : Node) (word : List Input) :
    admitted target (fun _ _ => True) node word := by
  induction word generalizing node with
  | nil => trivial
  | cons input rest ih => exact ⟨trivial, ih _⟩

theorem trace_decode {Observation : Type} (decode : State → Observation)
    (node : Node) (word : List Input) :
    trace target (fun current => decode (observe current)) node word =
      (trace target observe node word).map (fun row => (row.1, decode row.2)) := by
  induction word generalizing node with
  | nil => rfl
  | cons input rest ih => simp [trace, ih]

theorem reachable_correspondence_lifts_to_traces
    {Concrete Abstract Event Decision Observation : Type}
    (concrete : Concrete → Event → Decision × Concrete)
    (table : Abstract → Event → Decision × Abstract)
    (representation : Concrete → Abstract) (decode : Abstract → Observation)
    (concrete_initial : Concrete) (table_initial : Abstract)
    (initial_correspondence : representation concrete_initial = table_initial)
    (step_correspondence : ∀ stem event,
      table (representation (finish concrete concrete_initial stem)) event =
        ((concrete (finish concrete concrete_initial stem) event).1,
         representation (concrete (finish concrete concrete_initial stem) event).2))
    (word : List Event) :
    representation (finish concrete concrete_initial word) = finish table table_initial word ∧
    trace concrete (fun state => decode (representation state)) concrete_initial word =
      trace table decode table_initial word := by
  have earlier : ∀ stem, admitted concrete (fun _ _ => True) concrete_initial stem →
      stem.length < word.length → ∀ event, True →
      cell_agrees concrete representation table (finish concrete concrete_initial stem) event := by
    intro stem _ _ event _
    exact step_correspondence stem event
  have corresponding := matching_admitted_prefixes concrete (fun _ _ => True) representation table
    concrete_initial word.length earlier word (all_words_admitted concrete concrete_initial word) (Nat.le_refl _)
  constructor
  · simpa [initial_correspondence] using corresponding.1.symm
  · have mapped := congrArg (List.map (fun row : Decision × Abstract => (row.1, decode row.2)))
      corresponding.2.symm
    simpa [← trace_decode, initial_correspondence] using mapped

/- The observation before any request is part of the compared full behavior.
   It yields an empty witness independently of any graph traversal. -/
theorem initial_disagreement_empty_witness (initial : Node) (reference_initial : State)
    (different : reference_initial ≠ observe initial) :
    (reference_initial, trace source id reference_initial []) ≠
      (observe initial, trace target observe initial []) := by
  intro equal
  exact different (congrArg Prod.fst equal)

/- Instantiation for an explicitly partial caller protocol.  The totalized
   value on a disabled edge is irrelevant because admitted excludes that edge.
   A partially supplied target can be totalized in the same way only after all
   protocol-enabled reachable edges are supplied. -/
def product_target {Target Caller Event Decision : Type}
    (machine : Target → Event → Decision × Target) (protocol : Caller → Event → Option Caller)
    (node : Target × Caller) (event : Event) : Decision × (Target × Caller) :=
  ((machine node.1 event).1, ((machine node.1 event).2, (protocol node.2 event).getD node.2))

def protocol_enabled {Target Caller Event : Type} (protocol : Caller → Event → Option Caller)
    (node : Target × Caller) (event : Event) : Prop := ∃ next, protocol node.2 event = some next

def protocol_admitted {Caller Event : Type} (protocol : Caller → Event → Option Caller) :
    Caller → List Event → Prop
  | _, [] => True
  | caller, event :: rest => ∃ next, protocol caller event = some next ∧ protocol_admitted protocol next rest

theorem product_admitted_iff {Target Caller Event Decision : Type}
    (machine : Target → Event → Decision × Target) (protocol : Caller → Event → Option Caller)
    (node : Target × Caller) (word : List Event) :
    admitted (product_target machine protocol) (protocol_enabled protocol) node word ↔
      protocol_admitted protocol node.2 word := by
  induction word generalizing node with
  | nil => rfl
  | cons event rest ih =>
      cases hp : protocol node.2 event with
      | none => simp [admitted, protocol_enabled, protocol_admitted, hp]
      | some next => simp [admitted, protocol_enabled, protocol_admitted, product_target, hp, ih]

theorem product_trace {Target Caller Event Decision Observation : Type}
    (machine : Target → Event → Decision × Target) (protocol : Caller → Event → Option Caller)
    (decode : Target → Observation) (node : Target × Caller) (word : List Event) :
    trace (product_target machine protocol) (fun pair => decode pair.1) node word =
      trace machine decode node.1 word := by
  induction word generalizing node with
  | nil => rfl
  | cons event rest ih => simp [trace, product_target, ih]

/- This is the paper's caller-protocol witness statement. The covers premise
   refers only to product nodes reached by protocol-admitted words. -/
theorem caller_protocol_shortest_witness {Target Caller Event Decision Reference : Type}
    (machine : Target → Event → Decision × Target) (protocol : Caller → Event → Option Caller)
    (decode : Target → Reference) (reference : Reference → Event → Decision × Reference)
    (initial : Target × Caller) (reachable_products : List (Target × Caller))
    (covers : ∀ word, protocol_admitted protocol initial.2 word →
      finish (product_target machine protocol) initial word ∈ reachable_products)
    (disagrees : ¬ (∀ word, protocol_admitted protocol initial.2 word →
      trace reference id (decode initial.1) word = trace machine decode initial.1 word)) :
    ∃ word, protocol_admitted protocol initial.2 word ∧ word.length ≤ reachable_products.length ∧
      trace reference id (decode initial.1) word ≠ trace machine decode initial.1 word ∧
      ∀ shorter, protocol_admitted protocol initial.2 shorter → shorter.length < word.length →
        trace reference id (decode initial.1) shorter = trace machine decode initial.1 shorter := by
  have product_covers : ∀ word,
      admitted (product_target machine protocol) (protocol_enabled protocol) initial word →
      finish (product_target machine protocol) initial word ∈ reachable_products := by
    intro word accepted
    exact covers word ((product_admitted_iff machine protocol initial word).mp accepted)
  have product_disagrees : ¬ (∀ word,
      admitted (product_target machine protocol) (protocol_enabled protocol) initial word →
      trace reference id (decode initial.1) word =
        trace (product_target machine protocol) (fun pair => decode pair.1) initial word) := by
    intro all_equal
    apply disagrees
    intro word accepted
    simpa [product_trace] using all_equal word
      ((product_admitted_iff machine protocol initial word).mpr accepted)
  obtain ⟨word, accepted, bound, differs, shortest⟩ := shortest_admitted_witness_bound
    (product_target machine protocol) (protocol_enabled protocol) (fun pair => decode pair.1)
    reference initial reachable_products product_covers product_disagrees
  refine ⟨word, (product_admitted_iff machine protocol initial word).mp accepted,
    bound, by simpa [product_trace] using differs, ?_⟩
  intro shorter shorter_ok shorter_length
  simpa [product_trace] using shortest shorter
    ((product_admitted_iff machine protocol initial shorter).mpr shorter_ok) shorter_length

end AuthRefine.Protocol

#print axioms AuthRefine.Protocol.local_iff_admitted_trace_equivalence
#print axioms AuthRefine.Protocol.first_bad_cell_shortest
#print axioms AuthRefine.Protocol.shortest_path_distinct
#print axioms AuthRefine.Protocol.shortest_path_finite_bound
#print axioms AuthRefine.Protocol.shortest_admitted_witness_bound
#print axioms AuthRefine.Protocol.reachable_correspondence_lifts_to_traces
#print axioms AuthRefine.Protocol.initial_disagreement_empty_witness
#print axioms AuthRefine.Protocol.caller_protocol_shortest_witness
